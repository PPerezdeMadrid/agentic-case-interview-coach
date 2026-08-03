"""Baseline golden-set evaluation dashboard data: reads results JSON written by
run_baseline_golden_set.py.

`turn_control` has no baseline counterpart golden set (see build_baseline_golden_sets.py),
so app.py never calls this module for it. Not recomputed on page load -- rerun via
`make baseline-eval BASELINE_GOLDEN_SET=<name>`.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from node_eval.judge_eval import weighted_readiness_score

SRC_DIR = Path(__file__).resolve().parents[3]
BASELINE_EVAL_DIR = SRC_DIR / "database" / "node_eval" / "baseline_eval"

_CACHE: dict[str, dict[str, Any]] = {}

# Read from the source CSV, not the results JSON cache -- same reasoning as interviewer_eval._load_csv_metadata.
_METADATA_COLUMNS = [
    "category",
    "turn_index",
    "expected_action",
    "expected_block_id",
    "expected_ready_for_judge",
    "expected_socratic_function",
    "must_contain",
    "must_not_contain",
    "forbidden_substrings",
    "notes",
    "baseline_input",
]


def _results_path(golden_set: str) -> Path:
    return BASELINE_EVAL_DIR / f"baseline_golden_set_{golden_set}_results.json"


def _csv_path(golden_set: str) -> Path:
    return BASELINE_EVAL_DIR / f"baseline_golden_set_{golden_set}.csv"


def _load_csv_metadata(golden_set: str) -> dict[str, dict[str, str]]:
    path = _csv_path(golden_set)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["conversation_id"]: {key: row.get(key, "") for key in _METADATA_COLUMNS}
            for row in csv.DictReader(handle)
        }


def list_baseline_golden_sets() -> list[str]:
    """Golden-set names (e.g. 'evidence_handling') that already have results computed."""
    if not BASELINE_EVAL_DIR.exists():
        return []
    names = []
    for entry in BASELINE_EVAL_DIR.glob("baseline_golden_set_*_results.json"):
        name = entry.stem.removeprefix("baseline_golden_set_").removesuffix("_results")
        names.append(name)
    return sorted(names)


def load_baseline_eval(golden_set: str, *, refresh: bool = False) -> dict[str, Any]:
    if not refresh and golden_set in _CACHE:
        return _CACHE[golden_set]

    path = _results_path(golden_set)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `make baseline-eval BASELINE_GOLDEN_SET={golden_set}` "
            f"(or `python main/studio/node_eval/baseline_eval/run_baseline_golden_set.py "
            f"--csv database/node_eval/baseline_eval/baseline_golden_set_{golden_set}.csv` "
            "from `src/`) first."
        )

    payload = json.loads(path.read_text())
    csv_metadata = _load_csv_metadata(golden_set)
    empty_metadata = {key: "" for key in _METADATA_COLUMNS}
    records = sorted(
        (
            {**row, **csv_metadata.get(row["conversation_id"], empty_metadata)}
            for row in payload.get("records", [])
        ),
        key=lambda row: row["conversation_id"],
    )
    result = {**payload, "records": records}
    _CACHE[golden_set] = result
    return result


def compute_readiness_confusion(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """TP/TN/FP/FN + precision/recall on readiness alone; meaningful only for `worldcup`,
    where readiness is the sole scored field. Returns None if no row has that label."""
    tp = tn = fp = fn = 0
    for row in records:
        expected_raw = str(row.get("expected_ready_for_judge", "")).strip()
        predicted = row.get("predicted")
        if not expected_raw or row.get("error") or not isinstance(predicted, dict):
            continue
        expected = expected_raw.lower() == "true"
        actual = bool(predicted.get("ready_for_evaluation"))
        if expected and actual:
            tp += 1
        elif not expected and not actual:
            tn += 1
        elif not expected and actual:
            fp += 1
        else:
            fn += 1

    n_scored = tp + tn + fp + fn
    if not n_scored:
        return None

    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None
    return {
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "accuracy": round((tp + tn) / n_scored, 4),
        "precision": precision,
        "recall": recall,
        "weighted_score": weighted_readiness_score(precision, recall),
    }


def build_agentic_vs_baseline_comparison(
    agentic_categories: list[dict[str, Any]] | None,
    baseline_categories: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Pairs agentic and baseline per-category accuracy by category name for side-by-side
    display, sorted by widest gap first."""
    agentic_by_category = {row["category"]: row for row in (agentic_categories or [])}
    baseline_by_category = {row["category"]: row for row in (baseline_categories or [])}
    all_categories = sorted(set(agentic_by_category) | set(baseline_by_category))

    comparison = []
    for category in all_categories:
        agentic_row = agentic_by_category.get(category)
        baseline_row = baseline_by_category.get(category)
        agentic_accuracy = agentic_row["accuracy"] if agentic_row else None
        baseline_accuracy = baseline_row["accuracy"] if baseline_row else None
        gap = (
            agentic_accuracy - baseline_accuracy
            if agentic_accuracy is not None and baseline_accuracy is not None
            else None
        )
        comparison.append(
            {
                "category": category,
                "agentic_accuracy": agentic_accuracy,
                "agentic_tier": agentic_row["tier"] if agentic_row else "none",
                "baseline_accuracy": baseline_accuracy,
                "baseline_tier": baseline_row["tier"] if baseline_row else "none",
                "gap": gap,
            }
        )

    comparison.sort(key=lambda row: (row["gap"] if row["gap"] is not None else -2), reverse=True)
    return comparison


__all__ = [
    "list_baseline_golden_sets",
    "load_baseline_eval",
    "compute_readiness_confusion",
    "build_agentic_vs_baseline_comparison",
]
