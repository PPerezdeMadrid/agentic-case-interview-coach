"""Build four baseline golden-set CSVs for the World Cup case (04-worldcup-test),
reusing the *exact same* transcripts/categories/expected answers as
build_interviewer_golden_sets.py -- imported directly from that module rather than
copied, so the two node types are graded on literally the same fixtures.

Why the same fixtures are a fair test for baseline too: baseline is a single node
that fuses the interviewer + judge + eval roles, but its own system prompt
(doc/prompts/baseline_graph_system_prompt.md) carries near-identical behavioural
rules to the interviewer's (doc/prompts/interviewer_graph_system_prompt.md) --
reveal visible blocks on request, state case-data/"provide upon request" facts
plainly, never leak hidden guidance or the expected recommendation, and force a
turn-3 wrap-up asking for the final recommendation -- and both graphs share the
same 4-turn budget (MAX_BASELINE_TURNS == MAX_INTERVIEWER_TURNS_BEFORE_JUDGE == 4),
so turn_index 1/2/3 fixtures line up exactly. The one asymmetry: baseline's prompt
never received the interviewer's Socratic question-style few-shots
(interviewer_question_style_few_shots.md), so the socratic_function file is
expected to be a much harder golden set for baseline -- that gap is itself the
point of running it, not a reason to skip the file.

`baseline_input` is produced by calling the real, side-effect-free
`baseline._build_baseline_messages(...)` -- the exact function `baseline_node`
calls before invoking the combined interviewer/judge/eval LLM -- with case-guide
and profitability RAG context forced empty. That RAG retrieval is a live,
non-deterministic side channel unrelated to every mechanism these golden sets
test, so forcing it empty here is the same scope decision
build_interviewer_golden_sets.py makes by leaving focus_areas empty, and the same
reasoning build_judge_golden_set_worldcup.py uses to force judge's own case-guide
scouting call empty (there it needed mocking since judge_node's prompt assembly
isn't factored into a pure function; here it doesn't, since _build_baseline_messages
already is one).

Usage (from repo root, with the project venv active):
    python -m src.main.studio.node_eval.baseline_eval.build_baseline_golden_sets
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

STUDIO_DIR = Path(__file__).resolve().parents[2]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

INTERVIEWER_EVAL_DIR = STUDIO_DIR / "node_eval" / "interviewer_eval"
if str(INTERVIEWER_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(INTERVIEWER_EVAL_DIR))

import loader  # noqa: E402
import utils  # noqa: E402
from adapter import get_candidate_visible_blocks  # noqa: E402

import baseline  # noqa: E402
from build_interviewer_golden_sets import (  # noqa: E402
    EVIDENCE_ITEMS,
    GUARDRAIL_ITEMS,
    SOCRATIC_ITEMS,
    TURN_CONTROL_ITEMS,
)

CASE_ID = "04-worldcup-test"
OUTPUT_DIR = Path(__file__).resolve().parents[4] / "database" / "node_eval" / "baseline_eval"


def build_case() -> dict[str, Any]:
    raw_case = loader.load_case(CASE_ID)
    case_data = loader.adapt_case(raw_case)
    return {
        "case_prompt": utils.extract_case_prompt(case_data),
        "case_guidance": utils.extract_case_guidance(case_data),
        "case_data": case_data,
        "case_recommendation": utils.extract_case_recommendation(case_data),
        "rubric_data": loader.adapt_rubric(loader.load_rubric()),
        "visible_blocks": get_candidate_visible_blocks(case_data),
    }


def render_baseline_input(case: dict[str, Any], transcript: list[str], turn_index: int) -> str:
    """Call the real, side-effect-free baseline._build_baseline_messages -- no
    mocking needed, same reasoning as build_interviewer_golden_sets.py's
    render_interviewer_input, since this function never calls an LLM or touches
    the vectorstore itself."""
    messages = baseline._build_baseline_messages(
        case["case_prompt"],
        case["case_data"],
        case["case_guidance"],
        case["case_recommendation"],
        case["rubric_data"],
        transcript,
        case["visible_blocks"],
        turn_index,
        [],  # case_guide_context -- forced empty, see module docstring.
        [],  # profitability_context -- forced empty, see module docstring.
    )
    return messages[0].content


def _assert_turn_index_matches(item: dict[str, Any]) -> None:
    interviewer_lines = sum(1 for line in item["transcript"] if line.startswith("Interviewer"))
    if interviewer_lines != item["turn_index"]:
        raise AssertionError(
            f"{item['id']}: turn_index={item['turn_index']} but transcript has "
            f"{interviewer_lines} Interviewer-prefixed lines."
        )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    case = build_case()

    for items in (SOCRATIC_ITEMS, EVIDENCE_ITEMS, GUARDRAIL_ITEMS, TURN_CONTROL_ITEMS):
        for item in items:
            _assert_turn_index_matches(item)

    socratic_rows = [
        {
            "conversation_id": item["id"],
            "category": item["category"],
            "turn_index": item["turn_index"],
            "expected_action": "question",
            "expected_socratic_function": item["category"],
            "baseline_input": render_baseline_input(case, item["transcript"], item["turn_index"]),
            "notes": item["notes"],
        }
        for item in SOCRATIC_ITEMS
    ]
    _write_csv(
        OUTPUT_DIR / "baseline_golden_set_socratic_function.csv",
        ["conversation_id", "category", "turn_index", "expected_action", "expected_socratic_function", "baseline_input", "notes"],
        socratic_rows,
    )
    print(f"{len(socratic_rows)} rows -> baseline_golden_set_socratic_function.csv")

    evidence_rows = [
        {
            "conversation_id": item["id"],
            "category": item["category"],
            "turn_index": item["turn_index"],
            "expected_action": item["expected_action"],
            "expected_block_id": item["expected_block_id"],
            "must_contain": item["must_contain"],
            "must_not_contain": item["must_not_contain"],
            "baseline_input": render_baseline_input(case, item["transcript"], item["turn_index"]),
            "notes": item["notes"],
        }
        for item in EVIDENCE_ITEMS
    ]
    _write_csv(
        OUTPUT_DIR / "baseline_golden_set_evidence_handling.csv",
        [
            "conversation_id",
            "category",
            "turn_index",
            "expected_action",
            "expected_block_id",
            "must_contain",
            "must_not_contain",
            "baseline_input",
            "notes",
        ],
        evidence_rows,
    )
    print(f"{len(evidence_rows)} rows -> baseline_golden_set_evidence_handling.csv")

    guardrail_rows = [
        {
            "conversation_id": item["id"],
            "category": item["category"],
            "turn_index": item["turn_index"],
            "forbidden_substrings": item["forbidden_substrings"],
            "baseline_input": render_baseline_input(case, item["transcript"], item["turn_index"]),
            "notes": item["notes"],
        }
        for item in GUARDRAIL_ITEMS
    ]
    _write_csv(
        OUTPUT_DIR / "baseline_golden_set_guardrail.csv",
        ["conversation_id", "category", "turn_index", "forbidden_substrings", "baseline_input", "notes"],
        guardrail_rows,
    )
    print(f"{len(guardrail_rows)} rows -> baseline_golden_set_guardrail.csv")

    turn_rows = [
        {
            "conversation_id": item["id"],
            "category": item["category"],
            "turn_index": item["turn_index"],
            "expected_action": item["expected_action"],
            "expected_ready_for_judge": item["expected_ready_for_judge"],
            "must_contain": item["must_contain"],
            "baseline_input": render_baseline_input(case, item["transcript"], item["turn_index"]),
            "notes": item["notes"],
        }
        for item in TURN_CONTROL_ITEMS
    ]
    _write_csv(
        OUTPUT_DIR / "baseline_golden_set_turn_control.csv",
        ["conversation_id", "category", "turn_index", "expected_action", "expected_ready_for_judge", "must_contain", "baseline_input", "notes"],
        turn_rows,
    )
    print(f"{len(turn_rows)} rows -> baseline_golden_set_turn_control.csv")

    total = len(socratic_rows) + len(evidence_rows) + len(guardrail_rows) + len(turn_rows)
    print(f"Total: {total} rows across 4 files, written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
