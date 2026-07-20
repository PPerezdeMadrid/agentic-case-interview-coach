"""Run a judge golden-set CSV (see build_judge_golden_set_worldcup.py) against the
real judge LLM and score how often it gets `enough_evidence` right against the CSV's
`expected_enough_evidence` column.

Each row's `judge_input` is the exact rendered SystemMessage judge_node would send,
run through the same `invoke_json_llm(..., schema=JudgeResponse)` helper judge_node uses.

This costs one real LLM call per row, so it's a deliberate offline/Makefile step, not
something the dashboard recomputes on page load. Writes a JSON cache (read by the
workbench's Agents > Judge page) and a flat CSV of per-row results.

Usage (from src/, with the project venv active):
    python main/studio/node_eval/judge_eval/run_judge_golden_set.py
    python main/studio/node_eval/judge_eval/run_judge_golden_set.py --limit 10
    python main/studio/node_eval/judge_eval/run_judge_golden_set.py --csv path/to/other_golden_set.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STUDIO_DIR = Path(__file__).resolve().parents[2]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from langchain_core.messages import SystemMessage  # noqa: E402

from llm_server import judge_llm_server  # noqa: E402
from state import JudgeResponse  # noqa: E402
from utils import invoke_json_llm, normalize_focus_areas  # noqa: E402

JUDGE_EVAL_DIR = Path(__file__).resolve().parents[4] / "database" / "node_eval" / "judge_eval"
DEFAULT_CSV_PATH = JUDGE_EVAL_DIR / "judge_golden_set_worldcup.csv"


def _golden_set_name(csv_path: Path) -> str:
    """'judge_golden_set_worldcup.csv' -> 'worldcup', so results land next to the
    source CSV as 'judge_golden_set_worldcup_results.json'."""
    stem = csv_path.stem
    return stem.removeprefix("judge_golden_set_") or stem


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _load_rows(csv_path: Path, *, limit: int | None) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit] if limit is not None else rows


def _judge_one(judge_input: str) -> tuple[bool, list[str], dict | None]:
    """Send judge_input through the real judge LLM. Returns
    (predicted_enough_evidence, predicted_focus_areas, error_dict_or_None)."""
    try:
        payload, _usage_log = invoke_json_llm(
            judge_llm_server,
            [SystemMessage(content=judge_input)],
            node="judge_golden_set_eval",
            schema=JudgeResponse,
        )
    except Exception as exc:  # real API calls can time out / rate-limit / error
        return False, [], {"message": str(exc)}

    if not payload:
        return False, [], {"message": "Judge LLM did not return a parseable JSON payload."}

    predicted = bool(payload.get("enough_evidence", False))
    focus_areas = normalize_focus_areas(payload.get("focus_areas", []))
    return predicted, focus_areas, None


def run(csv_path: Path, *, limit: int | None = None) -> dict[str, Any]:
    golden_set = _golden_set_name(csv_path)
    rows = _load_rows(csv_path, limit=limit)

    records: list[dict[str, Any]] = []
    tp = tn = fp = fn = 0
    n_errors = 0

    for index, row in enumerate(rows, start=1):
        conversation_id = row.get("conversation_id", f"row_{index}")
        expected = _parse_bool(row.get("expected_enough_evidence", "False"))
        print(f"[{index}/{len(rows)}] {conversation_id} (expected={expected})", flush=True)

        predicted, focus_areas, error = _judge_one(row.get("judge_input", ""))
        correct = error is None and predicted == expected
        if error is not None:
            n_errors += 1
        elif expected and predicted:
            tp += 1
        elif not expected and not predicted:
            tn += 1
        elif not expected and predicted:
            fp += 1
        else:
            fn += 1

        records.append(
            {
                "conversation_id": conversation_id,
                "expected_enough_evidence": expected,
                "predicted_enough_evidence": predicted,
                "correct": correct,
                "predicted_focus_areas": focus_areas,
                "error": error,
            }
        )

    n_scored = tp + tn + fp + fn
    n_correct = tp + tn
    accuracy = round(n_correct / n_scored, 4) if n_scored else None
    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None

    output = {
        "golden_set": golden_set,
        "csv_path": str(csv_path),
        "model": getattr(judge_llm_server, "model_name", ""),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_total": len(rows),
        "n_scored": n_scored,
        "n_errors": n_errors,
        "n_correct": n_correct,
        "accuracy": accuracy,
        "confusion": {"true_positive": tp, "true_negative": tn, "false_positive": fp, "false_negative": fn},
        "precision": precision,
        "recall": recall,
        "records": records,
    }

    JUDGE_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    json_path = JUDGE_EVAL_DIR / f"judge_golden_set_{golden_set}_results.json"
    json_path.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        f"\n{n_scored}/{len(rows)} rows scored ({n_errors} errored). "
        f"Accuracy: {accuracy if accuracy is not None else 'n/a'} "
        f"(TP={tp} TN={tn} FP={fp} FN={fn})."
    )
    print(f"Wrote results to {json_path}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a judge golden-set CSV against the real judge LLM and score enough_evidence accuracy."
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV_PATH),
        help=f"Path to the golden-set CSV (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N rows (default: all)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        parser.error(f"CSV not found: {csv_path}")

    run(csv_path, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
