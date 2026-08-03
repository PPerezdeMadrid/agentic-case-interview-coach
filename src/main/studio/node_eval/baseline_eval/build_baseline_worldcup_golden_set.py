"""Puts baseline through judge_eval/build_judge_golden_set_worldcup.py's same 70 transcripts (ITEMS/build_case, imported not copied) so the workbench can show baseline's ready_for_evaluation next to judge's enough_evidence on identical fixtures.
visible_blocks and turn_index aren't in the golden set's state, so they're derived here: visible_blocks from case_data, turn_index by counting Interviewer:/Interviewer reveal: lines already in each transcript.
case_guide_context/profitability_context are left empty, matching how the judge builder mocks its own case-guide scouting call to empty.
CSV columns match run_baseline_golden_set.py's existing grader -- run via make baseline-eval BASELINE_GOLDEN_SET=worldcup.

Usage (from repo root, with the project venv active):
    python -m src.main.studio.node_eval.baseline_eval.build_baseline_worldcup_golden_set
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

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

OUTPUT_PATH = (
    Path(__file__).resolve().parents[4]
    / "database"
    / "node_eval"
    / "baseline_eval"
    / "baseline_golden_set_worldcup.csv"
)


def _turn_index(transcript: list[str]) -> int:
    """How many interviewer turns (question or reveal) already happened -- same quantity baseline_node's own turn_index counts."""
    return sum(
        1 for line in transcript if line.startswith("Interviewer:") or line.startswith("Interviewer reveal:")
    )


def main() -> None:
    case = build_case()
    rubric_data = loader.adapt_rubric(loader.load_rubric())
    case_data = case["case_data"]
    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []

    rows = []
    for item in ITEMS:
        transcript = item["transcript"]
        turn_index = _turn_index(transcript)
        messages = baseline._build_baseline_messages(
            case["case_prompt"],
            case_data,
            case["case_guidance"],
            case["case_recommendation"],
            rubric_data,
            transcript,
            visible_blocks,
            turn_index,
            [],
            [],
        )
        rows.append(
            {
                "conversation_id": item["id"],
                "category": item["category"],
                "turn_index": turn_index,
                "expected_ready_for_judge": item["expected_enough_evidence"],
                "baseline_input": messages[0].content,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["conversation_id", "category", "turn_index", "expected_ready_for_judge", "baseline_input"]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
