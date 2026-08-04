"""Replay a batch's stored transcripts through the judge eval nodes with RAG disabled,
and compare scores against the batch's original (with-RAG) run for the same transcript.


Usage (from src/, with the project venv active):
    python rag_ablation_eval.py --batch 20260713T104633Z_exp2
    python rag_ablation_eval.py --batch 20260713T104633Z_exp2 --limit 5
    python rag_ablation_eval.py --batch 20260713T104633Z_exp2 --restart

While a run is going (e.g. under sbatch), check progress from another shell without touching
anything:
    python rag_ablation_eval.py --batch 20260713T104633Z_exp2 --status
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parent
STUDIO_DIR = SRC_DIR / "main" / "studio"
BATCH_RUNS_DIR = SRC_DIR / "main" / "artifacts" / "batch_runs"

if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

import agentic  # noqa: E402
import baseline  # noqa: E402

CASE_PERFORMANCE_FIELDS = agentic.CASE_PERFORMANCE_FIELDS
QUALITY_DIALOG_FIELDS = agentic.QUALITY_DIALOG_FIELDS
POST_EVAL_TRANSCRIPT_PREFIXES = (
    "Eval Case Performance:",
    "Eval Dialog Quality:",
    "Give Feedback:",
)


def _load_batch(dir_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    batch_dir = BATCH_RUNS_DIR / dir_name
    summary_path = batch_dir / "summary.json"
    jsonl_path = batch_dir / "combined_results.jsonl"
    if not summary_path.exists() or not jsonl_path.exists():
        raise FileNotFoundError(f"Batch '{dir_name}' not found under {BATCH_RUNS_DIR}")

    summary = json.loads(summary_path.read_text())
    records: list[dict[str, Any]] = []
    with jsonl_path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return summary, records


CHECKPOINT_FILENAME = "rag_ablation_checkpoint.jsonl"


def _checkpoint_path(batch_dir: Path) -> Path:
    return batch_dir / CHECKPOINT_FILENAME


def _load_checkpoint(batch_dir: Path) -> dict[str, dict[str, Any]]:
    """Per-record results from a prior, interrupted run of this same batch, keyed by thread_id.
    A line left half-written by a hard crash/kill is skipped rather than failing the resume."""
    path = _checkpoint_path(batch_dir)
    if not path.exists():
        return {}
    done: dict[str, dict[str, Any]] = {}
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record_result = json.loads(line)
            except json.JSONDecodeError:
                continue
            thread_id = record_result.get("thread_id")
            if thread_id:
                done[thread_id] = record_result
    return done


def _append_checkpoint(batch_dir: Path, record_result: dict[str, Any]) -> None:
    path = _checkpoint_path(batch_dir)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record_result, ensure_ascii=False) + "\n")
        handle.flush()


def _transcript_before_eval(record: dict[str, Any]) -> list[str]:
    """Persisted runs include post-eval bookkeeping and final feedback appended to the
    transcript. RAG ablation must replay the transcript as it looked *before* the eval
    nodes ran, otherwise those extra lines can explode prompt length and also leak the
    original scoring pass back into the replay."""
    transcript = record.get("transcript", [])
    if not isinstance(transcript, list):
        return []

    cleaned: list[str] = []
    for line in transcript:
        if not isinstance(line, str):
            continue
        if line.startswith(POST_EVAL_TRANSCRIPT_PREFIXES):
            continue
        cleaned.append(line)
    return cleaned


def _rebuild_state(graph_name: str, record: dict[str, Any]) -> dict[str, Any]:
    """Rebuilds via scenario_ref (deterministic) plus the batch's actual transcript,
    so eval nodes see exactly what they saw the first time -- just without RAG."""
    scenario_ref = record.get("scenario_ref", "")
    if graph_name == "baseline":
        state = baseline.build_initial_baseline_state(scenario_ref=scenario_ref)
    else:
        state = agentic.build_initial_interview_state(scenario_ref=scenario_ref)
    state["transcript"] = _transcript_before_eval(record)
    state["thread_id"] = record.get("thread_id", state.get("thread_id", ""))
    return state


def _evaluate_without_rag(graph_name: str, state: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    if graph_name == "baseline":
        # Force the combined eval path regardless of the replayed transcript's own turn_index.
        state = dict(state)
        state["turn_index"] = baseline.MAX_BASELINE_TURNS
        with patch.multiple(
            baseline,
            get_pending_case_guide_context=lambda state, **kwargs: ([], {}),
            retrieve_profitability_guide_context=lambda *args, **kwargs: [],
        ):
            result = baseline.baseline_node(state)
        return result["case_performance"], result["quality_dialog"], result["llm_usage"]

    # Patch agentic's own retrieve_* names, not node.py's copies -- _sync_node_dependencies()
    # re-copies them into node.py before the node functions run.
    with patch.multiple(
        agentic,
        retrieve_case_guide_context=lambda *args, **kwargs: [],
        retrieve_profitability_guide_context=lambda *args, **kwargs: [],
    ):
        case_result = agentic.eval_case_performance_node(state)
        dialog_result = agentic.eval_dialog_quality_node(state)
    return (
        case_result["case_performance"],
        dialog_result["quality_dialog"],
        case_result["llm_usage"] + dialog_result["llm_usage"],
    )


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_of(payload: dict[str, Any], field: str) -> Any:
    entry = payload.get(field) if isinstance(payload, dict) else None
    return entry.get("score") if isinstance(entry, dict) else None


def _rationale_of(payload: dict[str, Any], field: str) -> str:
    entry = payload.get(field) if isinstance(payload, dict) else None
    return str(entry.get("rationale", "")) if isinstance(entry, dict) else ""


def _compare_field(field: str, with_rag: dict, without_rag: dict) -> dict[str, Any]:
    with_score = _score_of(with_rag, field)
    without_score = _score_of(without_rag, field)
    with_numeric = _numeric(with_score)
    without_numeric = _numeric(without_score)
    delta = (
        round(without_numeric - with_numeric, 3)
        if with_numeric is not None and without_numeric is not None
        else None
    )
    return {
        "dimension": field,
        "with_rag_score": with_score,
        "without_rag_score": without_score,
        "with_rag_rationale": _rationale_of(with_rag, field),
        "without_rag_rationale": _rationale_of(without_rag, field),
        "delta": delta,
    }


def _aggregate_by_dimension(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in results:
        graph_name = record["graph_name"]
        for section_key in ("case_performance", "quality_dialog"):
            for row in record[section_key]:
                buckets[(graph_name, section_key, row["dimension"])].append(row)

    aggregate = []
    for (graph_name, section, dimension), rows in sorted(buckets.items()):
        deltas = [row["delta"] for row in rows if row["delta"] is not None]
        with_scores = [v for v in (_numeric(row["with_rag_score"]) for row in rows) if v is not None]
        without_scores = [v for v in (_numeric(row["without_rag_score"]) for row in rows) if v is not None]
        aggregate.append(
            {
                "graph_name": graph_name,
                "section": section,
                "dimension": dimension,
                "n_total": len(rows),
                "n_comparable": len(deltas),
                "mean_with_rag": round(sum(with_scores) / len(with_scores), 3) if with_scores else None,
                "mean_without_rag": round(sum(without_scores) / len(without_scores), 3) if without_scores else None,
                "mean_delta": round(sum(deltas) / len(deltas), 3) if deltas else None,
                "mean_abs_delta": round(sum(abs(d) for d in deltas) / len(deltas), 3) if deltas else None,
                "n_differ": sum(1 for d in deltas if d != 0),
            }
        )
    return aggregate


def run_ablation(dir_name: str, *, limit: int | None = None, restart: bool = False) -> dict[str, Any]:
    summary, records = _load_batch(dir_name)
    ok_records = [record for record in records if record.get("status") == "ok"]
    if limit is not None:
        ok_records = ok_records[:limit]

    batch_dir = BATCH_RUNS_DIR / dir_name
    checkpoint_path = _checkpoint_path(batch_dir)
    if restart and checkpoint_path.exists():
        checkpoint_path.unlink()

    # Every record's comparison is appended to the checkpoint as soon as it's computed, so a
    # crash partway through (provider outage, OOM, job timeout, ...) only costs the in-flight
    # record -- rerunning the same command picks back up from here instead of redoing everything.
    done_results = {} if restart else _load_checkpoint(batch_dir)
    pending_records = [record for record in ok_records if record.get("thread_id", "") not in done_results]
    if done_results:
        print(
            f"Resuming from checkpoint: {len(done_results)} of {len(ok_records)} records already "
            f"scored, {len(pending_records)} remaining.",
            flush=True,
        )

    total_usage: list[dict[str, Any]] = []

    for index, record in enumerate(pending_records, start=1):
        graph_name = record.get("graph_name", "agentic")
        scenario_ref = record.get("scenario_ref", "")
        print(
            f"[{index}/{len(pending_records)}] {graph_name} {Path(scenario_ref).stem} "
            f"({record.get('thread_id', '')})",
            flush=True,
        )

        state = _rebuild_state(graph_name, record)
        without_case_performance, without_quality_dialog, usage_log = _evaluate_without_rag(graph_name, state)
        total_usage.extend(usage_log)

        with_case_performance = record.get("case_performance", {}) or {}
        with_quality_dialog = record.get("quality_dialog", {}) or {}

        record_result = {
            "thread_id": record.get("thread_id", ""),
            "graph_name": graph_name,
            "scenario_ref": scenario_ref,
            "repeat_index": record.get("repeat_index"),
            "checkpointed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "case_performance": [
                _compare_field(field, with_case_performance, without_case_performance)
                for field in CASE_PERFORMANCE_FIELDS
            ],
            "quality_dialog": [
                _compare_field(field, with_quality_dialog, without_quality_dialog)
                for field in QUALITY_DIALOG_FIELDS
            ],
        }
        done_results[record_result["thread_id"]] = record_result
        _append_checkpoint(batch_dir, record_result)

    # Reassemble in the batch's original order regardless of which records came from a prior
    # checkpoint vs. this run.
    results = [
        done_results[record["thread_id"]]
        for record in ok_records
        if record.get("thread_id", "") in done_results
    ]

    computed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total_tokens = sum((entry.get("usage") or {}).get("total_tokens") or 0 for entry in total_usage)

    output = {
        "batch_dir": dir_name,
        "batch_id": summary.get("batch_id", dir_name),
        "computed_at": computed_at,
        "n_records": len(results),
        "records": results,
        "aggregate_by_dimension": _aggregate_by_dimension(results),
    }

    json_path = batch_dir / "rag_ablation_results.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint_path.unlink(missing_ok=True)

    print(f"\n{len(results)} records evaluated, ~{total_tokens} total tokens for the without-RAG judge calls this run.")
    print(f"Wrote results to {json_path}")
    return output


def print_status(dir_name: str) -> None:
    """Read-only progress check: safe to run from a login-node shell while an sbatch job is
    still writing to the checkpoint. Reports records done so far and per-dimension MAE
    (mean_abs_delta) computed from whatever's been checkpointed -- same aggregation the final
    run uses, just over a partial sample."""
    _, records = _load_batch(dir_name)
    ok_records = [record for record in records if record.get("status") == "ok"]
    n_total = len(ok_records)

    batch_dir = BATCH_RUNS_DIR / dir_name
    done_results = _load_checkpoint(batch_dir)
    final_path = batch_dir / "rag_ablation_results.json"

    if not done_results and final_path.exists():
        final = json.loads(final_path.read_text())
        results = final.get("records", [])
        print(f"'{dir_name}': already completed -- {len(results)}/{n_total} records (reading {final_path.name}).\n")
    else:
        results = list(done_results.values())
        n_done = len(results)
        pct = (100 * n_done / n_total) if n_total else 0.0
        status_line = f"'{dir_name}': {n_done}/{n_total} records scored ({pct:.1f}%)"

        timestamps = sorted(
            datetime.fromisoformat(r["checkpointed_at"]) for r in results if r.get("checkpointed_at")
        )
        if len(timestamps) >= 2 and n_done < n_total:
            elapsed = (timestamps[-1] - timestamps[0]).total_seconds()
            rate = elapsed / (len(timestamps) - 1)
            eta_seconds = rate * (n_total - n_done)
            eta_at = timestamps[-1] + timedelta(seconds=eta_seconds)
            status_line += (
                f" -- ~{rate:.0f}s/record, ETA ~{eta_seconds / 3600:.1f}h "
                f"(around {eta_at.strftime('%Y-%m-%d %H:%M UTC')})"
            )
        print(status_line + "\n")

    if not results:
        print("No records scored yet.")
        return

    aggregate = _aggregate_by_dimension(results)
    header = f"{'graph':<10} {'section':<16} {'dimension':<26} {'n':>4} {'MAE':>7} {'bias':>7}"
    print(header)
    print("-" * len(header))
    for row in aggregate:
        mae = row["mean_abs_delta"]
        bias = row["mean_delta"]
        print(
            f"{row['graph_name']:<10} {row['section']:<16} {row['dimension']:<26} "
            f"{row['n_comparable']:>4} "
            f"{(f'{mae:.3f}' if mae is not None else '--'):>7} "
            f"{(f'{bias:+.3f}' if bias is not None else '--'):>7}"
        )

    dimension_maes = [row["mean_abs_delta"] for row in aggregate if row["mean_abs_delta"] is not None]
    if dimension_maes:
        print(
            f"\nRough pooled MAE across {len(dimension_maes)} dimensions (mean of the per-dimension "
            f"MAEs above): {sum(dimension_maes) / len(dimension_maes):.3f}"
        )
        print("Treat that pooled number as a quick pulse check only -- the per-dimension rows above are what matters.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a batch's stored transcripts through the judge eval nodes with RAG "
            "retrieval disabled, and compare eval_case/eval_dialog scores against the "
            "batch's original (with-RAG) scores for the same transcript."
        )
    )
    parser.add_argument(
        "--batch",
        required=True,
        help="Batch directory name under src/main/artifacts/batch_runs/",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N 'ok' records in the batch (default: all)",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help=(
            "Ignore any existing checkpoint for this batch and re-score every record from "
            "scratch (default: auto-resume from the checkpoint left by a prior interrupted run)"
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Print progress and per-dimension MAE from the checkpoint, then exit -- doesn't "
            "score anything. Safe to run from another shell while an sbatch job is still going."
        ),
    )
    args = parser.parse_args()

    if args.status:
        print_status(args.batch)
        return 0

    run_ablation(args.batch, limit=args.limit, restart=args.restart)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
