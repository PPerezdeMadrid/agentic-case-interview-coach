"""Interviewer golden-set evaluation dashboard data: reads results JSON written by
run_interviewer_golden_set.py.

Reuses judge_eval.category_breakdown since it's a generic {category, correct, error}
aggregator, not judge-specific. Not recomputed on page load -- rerun via
`make interviewer-eval INTERVIEWER_GOLDEN_SET=<name>`.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from node_eval.judge_eval import category_breakdown

SRC_DIR = Path(__file__).resolve().parents[3]
INTERVIEWER_EVAL_DIR = SRC_DIR / "database" / "node_eval" / "interviewer_eval"

_CACHE: dict[str, dict[str, Any]] = {}

# Read from the source CSV, not the results JSON cache -- same reasoning as judge_eval._load_csv_metadata.
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
    "interviewer_input",
]


def _results_path(golden_set: str) -> Path:
    return INTERVIEWER_EVAL_DIR / f"interviewer_golden_set_{golden_set}_results.json"


def _csv_path(golden_set: str) -> Path:
    return INTERVIEWER_EVAL_DIR / f"interviewer_golden_set_{golden_set}.csv"


def _load_csv_metadata(golden_set: str) -> dict[str, dict[str, str]]:
    path = _csv_path(golden_set)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["conversation_id"]: {key: row.get(key, "") for key in _METADATA_COLUMNS}
            for row in csv.DictReader(handle)
        }


def list_interviewer_golden_sets() -> list[str]:
    """Golden-set names (e.g. 'evidence_handling') that already have results computed."""
    if not INTERVIEWER_EVAL_DIR.exists():
        return []
    names = []
    for entry in INTERVIEWER_EVAL_DIR.glob("interviewer_golden_set_*_results.json"):
        name = entry.stem.removeprefix("interviewer_golden_set_").removesuffix("_results")
        names.append(name)
    return sorted(names)


def load_interviewer_eval(golden_set: str, *, refresh: bool = False) -> dict[str, Any]:
    if not refresh and golden_set in _CACHE:
        return _CACHE[golden_set]

    path = _results_path(golden_set)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `make interviewer-eval INTERVIEWER_GOLDEN_SET={golden_set}` "
            f"(or `python main/studio/node_eval/interviewer_eval/run_interviewer_golden_set.py "
            f"--csv database/node_eval/interviewer_eval/interviewer_golden_set_{golden_set}.csv` "
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
