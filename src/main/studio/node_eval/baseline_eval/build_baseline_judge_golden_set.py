"""Build a baseline "enough evidence" golden-set CSV reusing the exact same
World Cup transcripts/categories/expected labels as
judge_eval/build_judge_golden_set_worldcup.py -- imported directly (not
copied), so the agentic judge and baseline's analogous readiness decision are
graded on literally the same fixtures. Mirrors how build_baseline_golden_sets.py
reuses the interviewer's fixtures for the other 4 golden-set files.

Because ITEMS is imported rather than copied, this script's output always
matches the judge builder's current item count -- but only once *re-run*. If
judge_eval/build_judge_golden_set_worldcup.py's ITEMS grows and this script
isn't re-run afterwards, the two CSVs silently drift apart (see
check_golden_set_sync.py, which catches exactly that).

Baseline has no separate judge node: `enough_evidence` in its graph state is
set directly from `ready_for_evaluation`, the boolean the single fused
interviewer/judge/eval node returns on every turn (see baseline_node in
baseline.py). This script renders `baseline._build_baseline_messages(...)`
for each of the judge golden set's transcripts and asks whether *baseline
itself* would consider the evidence complete -- baseline's direct analogue
of judge_node's enough_evidence call.

`turn_index` is fixed at 2 for every row (not the final turn, not over the
4-turn budget) so the decision reflects the model's own judgment rather than
the deterministic forced-evaluation override -- the same design choice the
judge golden set makes by fixing judge_round=0 on every row (baseline's
MAX_BASELINE_TURNS-driven force is baseline's analogue of judge's
MAX_JUDGE_ROUNDS override).

Output columns intentionally match run_baseline_golden_set.py's existing
generic grader (`expected_ready_for_judge` graded against the real
predicted["ready_for_evaluation"]), so no new runner is needed -- this reuses
the exact same script the other 4 baseline golden sets use.

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
