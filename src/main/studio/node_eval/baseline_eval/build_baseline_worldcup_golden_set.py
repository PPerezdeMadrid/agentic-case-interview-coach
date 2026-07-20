"""Build a baseline golden-set CSV that puts baseline through the exact same 70
World Cup transcripts as `judge_eval/build_judge_golden_set_worldcup.py`, so the
workbench's Agents > Judge page can show baseline's readiness call
(`ready_for_evaluation`) side by side with the real judge's `enough_evidence`
call on identical fixtures -- same transcripts, same categories, same expected
answer, just graded through baseline's fused single-call architecture instead
of a dedicated judge node.

Reuses `judge_eval.build_judge_golden_set_worldcup.ITEMS`/`build_case` (imported,
not copied) for the transcripts/category/expected labels, and
`baseline._build_baseline_messages` (the same pure prompt-assembly function
`baseline_node` itself calls) to render each row's `baseline_input`. Two fields
baseline_node would normally compute from live graph state have no equivalent
in the golden set and are derived instead:

  * `visible_blocks` -- comes from `case_data` alone (adapter.get_candidate_visible_blocks),
    which the judge golden set's `state` already carries, so no derivation needed.
  * `turn_index` -- baseline increments this by 1 per non-evaluate turn, i.e. it
    equals how many "Interviewer:"/"Interviewer reveal:" lines already exist in
    the transcript when baseline is asked to move next. Counted directly from
    each item's transcript.

`case_guide_context`/`profitability_context` are left empty (`[]`), matching how
`build_judge_golden_set_worldcup.capture_judge_prompt` mocks judge's own
case-guide scouting to empty -- one decision call per row, no RAG-scouting call.

Writes CSV columns matching the schema `run_baseline_golden_set.py` already
knows how to grade generically: only `expected_ready_for_judge` is populated
(from `expected_enough_evidence`), so that script's existing `_grade()` scores
purely on the readiness call with no changes needed -- run via:
    make baseline-eval BASELINE_GOLDEN_SET=worldcup

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
    """How many interviewer turns (question or reveal) already happened -- the
    same quantity baseline_node's own `turn_index` counts, one increment per
    non-evaluate baseline call."""
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
