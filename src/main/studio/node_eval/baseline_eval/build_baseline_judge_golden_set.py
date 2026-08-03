"""Builds a baseline "enough evidence" golden-set CSV reusing judge_eval/build_judge_golden_set_worldcup.py's ITEMS (imported, not copied) so judge and baseline are graded on identical fixtures -- re-run this after that file's ITEMS changes or the CSVs drift (see check_golden_set_sync.py).
Baseline has no separate judge node: enough_evidence comes directly from ready_for_evaluation, the fused node's per-turn readiness call (see baseline_node).
turn_index is fixed at 2 (not final, not over budget) so the decision reflects the model's own judgment, not the forced-evaluation override -- mirrors the judge golden set's judge_round=0.
Output columns match run_baseline_golden_set.py's existing grader, so no new runner is needed.

Usage (from repo root, with the project venv active):
    python -m src.main.studio.node_eval.baseline_eval.build_baseline_judge_golden_set
    make baseline-eval BASELINE_GOLDEN_SET=worldcup
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

STUDIO_DIR = Path(__file__).resolve().parents[2]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

JUDGE_EVAL_DIR = STUDIO_DIR / "node_eval" / "judge_eval"
if str(JUDGE_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(JUDGE_EVAL_DIR))

import loader  # noqa: E402
from adapter import get_candidate_visible_blocks  # noqa: E402

import baseline  # noqa: E402
from build_judge_golden_set_worldcup import ITEMS, build_case  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parents[4] / "database" / "node_eval" / "baseline_eval"
OUTPUT_PATH = OUTPUT_DIR / "baseline_golden_set_worldcup.csv"

TURN_INDEX = 2  # not final, not over budget -- see module docstring.


def render_baseline_input(case: dict[str, Any], transcript: list[str]) -> str:
    messages = baseline._build_baseline_messages(
        case["case_prompt"],
        case["case_data"],
        case["case_guidance"],
        case["case_recommendation"],
        case["rubric_data"],
        transcript,
        case["visible_blocks"],
        TURN_INDEX,
        [],  # case_guide_context -- forced empty, same reasoning as build_baseline_golden_sets.py.
        [],  # profitability_context -- forced empty, same reasoning.
    )
    return messages[0].content


def main() -> None:
    case = build_case()
    case["rubric_data"] = loader.adapt_rubric(loader.load_rubric())
    case["visible_blocks"] = get_candidate_visible_blocks(case["case_data"])

    rows = [
        {
            "conversation_id": item["id"],
            "category": item["category"],
            "turn_index": TURN_INDEX,
            "expected_action": "",
            "expected_ready_for_judge": item["expected_enough_evidence"],
            "must_contain": "",
            "baseline_input": render_baseline_input(case, item["transcript"]),
            "notes": item["rationale"],
        }
        for item in ITEMS
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "conversation_id",
        "category",
        "turn_index",
        "expected_action",
        "expected_ready_for_judge",
        "must_contain",
        "baseline_input",
        "notes",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    expected_true = sum(1 for item in ITEMS if item["expected_enough_evidence"])
    print(
        f"{len(rows)} rows -> {OUTPUT_PATH} "
        f"({expected_true} expected True / {len(rows) - expected_true} expected False)"
    )


if __name__ == "__main__":
    main()
