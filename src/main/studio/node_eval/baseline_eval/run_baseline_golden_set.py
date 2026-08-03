"""Runs a baseline golden-set CSV against the real baseline LLM and grades it generically -- a near-identical sibling of run_interviewer_golden_set.py, adapted for baseline's schema.
BaselineTurnOutput.action adds "evaluate" (baseline fuses interviewer+judge, so it can end the interview itself); expected_action never expects it within turns 1-3, since both graphs share the same 4-turn budget.
ready_for_evaluation is baseline's analogue of ready_for_judge, graded directly with no reinterpretation. require_evaluate is left False since whether the model chooses to evaluate on its own is exactly what expected_ready_for_judge checks.
Rows with expected_socratic_function reuse the interviewer eval's classifier (imported, not copied) so both node types are scored by the same taxonomy and judge model.
This costs 1-2 real LLM calls per row, so it's a deliberate offline/Makefile step -- writes a JSON cache read by the workbench's Agents > Baseline page.

Usage (from src/, with the project venv active):
    python main/studio/node_eval/baseline_eval/run_baseline_golden_set.py \\
        --csv database/node_eval/baseline_eval/baseline_golden_set_evidence_handling.csv
    make baseline-eval BASELINE_GOLDEN_SET=guardrail
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

INTERVIEWER_EVAL_DIR = STUDIO_DIR / "node_eval" / "interviewer_eval"
if str(INTERVIEWER_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERVIEWER_EVAL_DIR))

from langchain_core.messages import SystemMessage  # noqa: E402

import baseline  # noqa: E402
from run_interviewer_golden_set import SOCRATIC_JUDGE_LLM, _CASE_DATA, _classify_socratic_function  # noqa: E402
from state import BaselineTurnOutput  # noqa: E402
from utils import invoke_json_llm, resolve_reveal_content  # noqa: E402

BASELINE_EVAL_DIR = Path(__file__).resolve().parents[4] / "database" / "node_eval" / "baseline_eval"
DEFAULT_CSV_PATH = BASELINE_EVAL_DIR / "baseline_golden_set_evidence_handling.csv"


def _golden_set_name(csv_path: Path) -> str:
    stem = csv_path.stem
    return stem.removeprefix("baseline_golden_set_") or stem


def _load_rows(csv_path: Path, *, limit: int | None) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit] if limit is not None else rows


def _split_terms(value: str) -> list[str]:
    return [term.strip() for term in value.split("|") if term.strip()]


def _contains_all(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def _contains_none(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return not any(term.lower() in lowered for term in terms)


def _baseline_one(baseline_input: str, *, classify_function: bool) -> tuple[dict | None, dict | None]:
    """Send baseline_input through the real baseline LLM. Returns
    (predicted_dict_or_None, error_dict_or_None)."""
    try:
        payload, _usage_log = invoke_json_llm(
            baseline.baseline_llm,
            [SystemMessage(content=baseline_input)],
            node="baseline_golden_set_eval",
            schema=BaselineTurnOutput,
            accept=lambda candidate: baseline.parse_baseline_output(candidate) is not None,
            retries=baseline.MAX_BASELINE_JSON_RETRIES,
        )
    except Exception as exc:  # real API calls can time out / rate-limit / error
        return None, {"message": str(exc)}

    parsed = baseline.parse_baseline_output(payload)
    if parsed is None:
        return None, {"message": "Baseline LLM did not return a parseable JSON payload."}

    # Mirrors baseline_node's own downgrade step, so a reveal of a hidden/missing block is graded as the graph actually renders it.
    action, content = resolve_reveal_content(
        _CASE_DATA, parsed["action"], parsed["block_id"], parsed["content"]
    )
    predicted = {
        "action": action,
        "content": content,
        "block_id": parsed["block_id"],
        "ready_for_evaluation": parsed["ready_for_evaluation"],
        "socratic_function": "",
    }
    if classify_function and predicted["content"]:
        try:
            predicted["socratic_function"] = _classify_socratic_function(predicted["content"])
        except Exception as exc:
            return predicted, {"message": f"Socratic-function classification failed: {exc}"}
    return predicted, None


def _grade(row: dict[str, str], predicted: dict[str, Any]) -> tuple[bool, list[str]]:
    """Grades a row against whichever expected_*/must_contain columns it has. Returns (correct, failed_checks)."""
    failed: list[str] = []

    expected_action = row.get("expected_action", "").strip()
    if expected_action and predicted["action"] != expected_action:
        failed.append(f"action: expected '{expected_action}', got '{predicted['action']}'")

    expected_block_id = row.get("expected_block_id", "").strip()
    if expected_block_id and predicted["block_id"] != expected_block_id:
        failed.append(f"block_id: expected '{expected_block_id}', got '{predicted['block_id'] or '(empty)'}'")

    expected_ready = row.get("expected_ready_for_judge", "").strip()
    if expected_ready:
        expected_bool = expected_ready.lower() == "true"
        if predicted["ready_for_evaluation"] != expected_bool:
            failed.append(f"ready_for_evaluation: expected {expected_bool}, got {predicted['ready_for_evaluation']}")

    must_contain = _split_terms(row.get("must_contain", ""))
    if must_contain and not _contains_all(predicted["content"], must_contain):
        failed.append(f"must_contain: missing at least one of {must_contain}")

    must_not_contain = _split_terms(row.get("must_not_contain", "")) + _split_terms(row.get("forbidden_substrings", ""))
    if must_not_contain and not _contains_none(predicted["content"], must_not_contain):
        failed.append(f"must_not_contain: found a forbidden term from {must_not_contain}")

    expected_function = row.get("expected_socratic_function", "").strip()
    if expected_function and predicted["socratic_function"] != expected_function:
        failed.append(f"socratic_function: expected '{expected_function}', got '{predicted['socratic_function']}'")

    return (len(failed) == 0, failed)


def run(csv_path: Path, *, limit: int | None = None) -> dict[str, Any]:
    golden_set = _golden_set_name(csv_path)
    rows = _load_rows(csv_path, limit=limit)

    records: list[dict[str, Any]] = []
    n_correct = 0
    n_errors = 0

    for index, row in enumerate(rows, start=1):
        conversation_id = row.get("conversation_id", f"row_{index}")
        print(f"[{index}/{len(rows)}] {conversation_id} ({row.get('category', '')})", flush=True)

        classify_function = bool(row.get("expected_socratic_function", "").strip())
        predicted, error = _baseline_one(row.get("baseline_input", ""), classify_function=classify_function)

        if error is not None or predicted is None:
            n_errors += 1
            correct, failed_checks = False, []
        else:
            correct, failed_checks = _grade(row, predicted)
            if correct:
                n_correct += 1

        records.append(
            {
                "conversation_id": conversation_id,
                "predicted": predicted,
                "correct": correct,
                "failed_checks": failed_checks,
                "error": error,
            }
        )

    n_scored = len(rows) - n_errors
    accuracy = round(n_correct / n_scored, 4) if n_scored else None

    output = {
        "golden_set": golden_set,
        "csv_path": str(csv_path),
        "model": getattr(baseline.baseline_llm, "model_name", ""),
        "socratic_judge_model": getattr(SOCRATIC_JUDGE_LLM, "model_name", ""),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_total": len(rows),
        "n_scored": n_scored,
        "n_errors": n_errors,
        "n_correct": n_correct,
        "accuracy": accuracy,
        "records": records,
    }

    BASELINE_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    json_path = BASELINE_EVAL_DIR / f"baseline_golden_set_{golden_set}_results.json"
    json_path.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        f"\n{n_scored}/{len(rows)} rows scored ({n_errors} errored). "
        f"Accuracy: {accuracy if accuracy is not None else 'n/a'}."
    )
    print(f"Wrote results to {json_path}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a baseline golden-set CSV against the real baseline LLM and grade it."
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
