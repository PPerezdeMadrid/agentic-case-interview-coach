"""Judge golden-set evaluation dashboard data: reads results JSON written by
run_judge_golden_set.py.

Not recomputed on page load -- each row costs a real judge LLM call; rerun via
`make judge-eval` (same pattern as rag_ablation.py).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[3]
JUDGE_EVAL_DIR = SRC_DIR / "database" / "node_eval" / "judge_eval"

_CACHE: dict[str, dict[str, Any]] = {}


def _results_path(golden_set: str) -> Path:
    return JUDGE_EVAL_DIR / f"judge_golden_set_{golden_set}_results.json"


def _csv_path(golden_set: str) -> Path:
    return JUDGE_EVAL_DIR / f"judge_golden_set_{golden_set}.csv"


def _load_csv_metadata(golden_set: str) -> dict[str, dict[str, str]]:
    """Map conversation_id -> {category, judge_input} from the CSV, not the results JSON cache."""
    path = _csv_path(golden_set)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["conversation_id"]: {
                "category": row.get("category", ""),
                "judge_input": row.get("judge_input", ""),
            }
            for row in csv.DictReader(handle)
        }


def list_judge_golden_sets() -> list[str]:
    """Golden-set names (e.g. 'worldcup') that already have results computed."""
    if not JUDGE_EVAL_DIR.exists():
        return []
    names = []
    for entry in JUDGE_EVAL_DIR.glob("judge_golden_set_*_results.json"):
        name = entry.stem.removeprefix("judge_golden_set_").removesuffix("_results")
        names.append(name)
    return sorted(names)


def load_judge_eval(golden_set: str, *, refresh: bool = False) -> dict[str, Any]:
    if not refresh and golden_set in _CACHE:
        return _CACHE[golden_set]

    path = _results_path(golden_set)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `make judge-eval GOLDEN_SET={golden_set}` "
            f"(or `python main/studio/node_eval/judge_eval/run_judge_golden_set.py` from src/) first."
        )

    payload = json.loads(path.read_text())
    csv_metadata = _load_csv_metadata(golden_set)
    records = sorted(
        (
            {
                **row,
                **csv_metadata.get(row["conversation_id"], {"category": "", "judge_input": ""}),
            }
            for row in payload.get("records", [])
        ),
        key=lambda row: row["conversation_id"],
    )
    result = {**payload, "records": records}
    result["weighted_score"] = weighted_readiness_score(payload.get("precision"), payload.get("recall"))
    _CACHE[golden_set] = result
    return result


def weighted_readiness_score(precision: float | None, recall: float | None, *, beta: float = 0.5) -> float | None:
    """F-beta of precision vs. recall for the enough_evidence/ready_for_judge call, weighted
    toward precision (beta < 1): a false positive (declaring evidence sufficient too early,
    cutting the interview short on a real gap) is treated as costlier than a false negative
    (asking for one more turn). None if either input is missing (non-boolean golden sets)."""
    if precision is None or recall is None:
        return None
    beta_sq = beta**2
    denominator = beta_sq * precision + recall
    if denominator == 0:
        return 0.0
    return round((1 + beta_sq) * precision * recall / denominator, 4)


def category_breakdown(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate records into pass/fail counts by `category`, sorted worst-accuracy-first
    (see doc/evaluation/Dialog-evaluation.md)."""
    stats: dict[str, dict[str, int]] = {}
    for row in records:
        category = row.get("category") or "(uncategorized)"
        bucket = stats.setdefault(category, {"total": 0, "correct": 0, "errors": 0})
        bucket["total"] += 1
        if row.get("error"):
            bucket["errors"] += 1
        elif row.get("correct"):
            bucket["correct"] += 1

    breakdown = []
    for category, bucket in stats.items():
        scored = bucket["total"] - bucket["errors"]
        wrong = scored - bucket["correct"]
        accuracy = (bucket["correct"] / scored) if scored else None
        if accuracy is None:
            tier = "none"
        elif accuracy >= 0.9:
            tier = "good"
        elif accuracy >= 0.5:
            tier = "warn"
        else:
            tier = "bad"
        breakdown.append(
            {
                "category": category,
                "total": bucket["total"],
                "correct": bucket["correct"],
                "wrong": wrong,
                "errors": bucket["errors"],
                "accuracy": accuracy,
                "tier": tier,
            }
        )

    breakdown.sort(key=lambda b: (b["accuracy"] if b["accuracy"] is not None else -1, b["category"]))
    for index, row in enumerate(breakdown, start=1):
        row["index"] = index
    return breakdown
