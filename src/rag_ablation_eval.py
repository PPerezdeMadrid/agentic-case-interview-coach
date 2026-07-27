"""Replay a batch's stored transcripts through the judge's
eval nodes (`eval_case_performance` / `eval_dialog_quality`) with every RAG
retrieval call disabled, and compare the resulting `case_performance` /
`quality_dialog` scores against the batch's original (with-RAG) scores for
that exact same transcript.

Usage (from src/, with the project venv active):
    python rag_ablation_eval.py --batch 20260713T104633Z_exp2
    python rag_ablation_eval.py --batch 20260713T104633Z_exp2 --limit 5
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
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


def _rebuild_state(graph_name: str, record: dict[str, Any]) -> dict[str, Any]:
    """Reload the scenario bundle (case data/guidance/rubric are deterministic
    per scenario_ref) and drop in the batch's actual transcript, so the eval
    nodes see exactly what they saw the first time -- just without RAG."""
    scenario_ref = record.get("scenario_ref", "")
    if graph_name == "baseline":
        state = baseline.build_initial_baseline_state(scenario_ref=scenario_ref)
    else:
        state = agentic.build_initial_interview_state(scenario_ref=scenario_ref)
    state["transcript"] = record.get("transcript", [])
    state["thread_id"] = record.get("thread_id", state.get("thread_id", ""))
    return state


def _evaluate_without_rag(graph_name: str, state: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    if graph_name == "baseline":
        # baseline_node evaluates case_performance and quality_dialog together in a
        # single combined call; force it down that path regardless of the replayed
        # transcript's own turn_index.
        state = dict(state)
        state["turn_index"] = baseline.MAX_BASELINE_TURNS
        with patch.multiple(
            baseline,
            get_pending_case_guide_context=lambda state, **kwargs: ([], {}),
            retrieve_profitability_guide_context=lambda *args, **kwargs: [],
        ):
            result = baseline.baseline_node(state)
        return result["case_performance"], result["quality_dialog"], result["llm_usage"]

    # agentic.eval_case_performance_node/eval_dialog_quality_node call
    # _sync_node_dependencies() first, which copies agentic's own
    # retrieve_* names into node.py -- so patching them here (not node.py's
    # copies) is what actually reaches the node functions.
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


def run_ablation(dir_name: str, *, limit: int | None = None) -> dict[str, Any]:
    summary, records = _load_batch(dir_name)
    ok_records = [record for record in records if record.get("status") == "ok"]
    if limit is not None:
        ok_records = ok_records[:limit]

    results: list[dict[str, Any]] = []
    total_usage: list[dict[str, Any]] = []

    for index, record in enumerate(ok_records, start=1):
        graph_name = record.get("graph_name", "agentic")
        scenario_ref = record.get("scenario_ref", "")
        print(
            f"[{index}/{len(ok_records)}] {graph_name} {Path(scenario_ref).stem} "
            f"({record.get('thread_id', '')})",
            flush=True,
        )

        state = _rebuild_state(graph_name, record)
        without_case_performance, without_quality_dialog, usage_log = _evaluate_without_rag(graph_name, state)
        total_usage.extend(usage_log)

        with_case_performance = record.get("case_performance", {}) or {}
        with_quality_dialog = record.get("quality_dialog", {}) or {}

        results.append(
            {
                "thread_id": record.get("thread_id", ""),
                "graph_name": graph_name,
                "scenario_ref": scenario_ref,
                "repeat_index": record.get("repeat_index"),
                "case_performance": [
                    _compare_field(field, with_case_performance, without_case_performance)
                    for field in CASE_PERFORMANCE_FIELDS
                ],
                "quality_dialog": [
                    _compare_field(field, with_quality_dialog, without_quality_dialog)
                    for field in QUALITY_DIALOG_FIELDS
                ],
            }
        )

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

    batch_dir = BATCH_RUNS_DIR / dir_name
    json_path = batch_dir / "rag_ablation_results.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(results)} records evaluated, ~{total_tokens} total tokens for the without-RAG judge calls.")
    print(f"Wrote results to {json_path}")
    return output


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
    args = parser.parse_args()

    run_ablation(args.batch, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
