import json
import re
from typing import Annotated, Literal
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from prompts import (
    CANDIDATE_SYSTEM_PROMPT,
    INTERVIEWER_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
)
from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
    get_case_blocks_by_type,
    get_hidden_guidance_blocks,
    get_opening_prompt,
)
from loader import (
    DEFAULT_MAX_JUDGE_ROUNDS,
    ROUNDS_TILL_JUDGE,
    adapt_rubric,
    load_rubric,
    load_selected_case,
)
from state import InterviewState
from llm_server import llm_server

MAX_JUDGE_ROUNDS = DEFAULT_MAX_JUDGE_ROUNDS


def _strip_thinking(text: str) -> str:
    """Remove model thinking blocks such as <think>...</think> from visible output."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _parse_interviewer_output(raw_output: str) -> tuple[str, str, str]:
    try:
        payload = json.loads(raw_output)
        action = str(payload.get("action", "question")).strip().lower()
        content = str(payload.get("content", "")).strip()
        block_id = str(payload.get("block_id", "")).strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        return "question", "Could you walk me through your approach?", ""

    if action not in {"question", "reveal"}:
        action = "question"
    return action, content, block_id


def _format_case_blocks(blocks: list[dict]) -> str:
    if not blocks:
        return "None."

    formatted_blocks = []
    for block in blocks:
        title = str(block.get("title", "")).strip() or str(block.get("block_id", "")).strip() or "Untitled block"
        content = str(block.get("content", "")).strip()
        formatted_blocks.append(f"- {title}: {content}")
    return "\n".join(formatted_blocks)


def _format_rubric(rubric_data: dict) -> str:
    dimensions = rubric_data.get("dimensions", [])
    if not isinstance(dimensions, list) or not dimensions:
        return "No rubric dimensions available."

    formatted_dimensions = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        dimension_id = str(dimension.get("dimension_id", "")).strip() or "unknown_dimension"
        description = str(dimension.get("description", "")).strip()
        criteria = dimension.get("criteria", {})
        formatted_dimensions.append(f"- {dimension_id}: {description}")
        if isinstance(criteria, dict):
            for score, criterion in criteria.items():
                formatted_dimensions.append(f"  Score {score}: {criterion}")
    return "\n".join(formatted_dimensions) if formatted_dimensions else "No rubric dimensions available."


def build_initial_interview_state(case_name: str | None = None, seed: int | None = None) -> InterviewState:
    selected_case = load_selected_case(case_name=case_name, seed=seed)
    rubric_data = adapt_rubric(load_rubric())

    return {
        "messages": [],
        "transcript": [],
        "candidate_transcript": [],
        "case_data": selected_case["case"],
        "rubric_data": rubric_data,
        "turn_index": 0,
        "judge_round": 0,
        "last_judge_turn_index": 0,
        "latest_question": "",
        "latest_answer": "",
        "latest_feedback": "",
        "interviewer_decision": "ask_candidate",
        "interviewer_action": "question",
        "judge_decision": "continue",
        "focus_area": "",
        "interviewer_guidance": "",
        "enough_evidence": False,
        "judge_reason": "",
        "final_score": 0,
    }

# NODES

def interviewer_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    last_judge_turn_index = state.get("last_judge_turn_index", 0)
    transcript = state.get("transcript", [])
    candidate_transcript = state.get("candidate_transcript", [])
    case_name = state.get("case_name")
    case_data = state.get("case_data", {})
    rubric_data = state.get("rubric_data", {})
    latest_feedback = state.get("latest_feedback", "")
    focus_area = state.get("focus_area", "")
    interviewer_guidance = state.get("interviewer_guidance", "")

    if turn_index == 0 and not transcript:
        if not isinstance(case_data, dict) or not case_data:
            selected_case = load_selected_case(case_name=case_name)
            case_data = selected_case["case"]
        if not isinstance(rubric_data, dict) or not rubric_data:
            rubric_data = adapt_rubric(load_rubric())
        opening_block = get_opening_prompt(case_data) if isinstance(case_data, dict) else None
        content = str(opening_block.get("content", "")).strip() if opening_block else ""
        content = content or "Walk me through your approach."
        interviewer_action: Literal["question", "reveal"] = "question"
        revealed_block_id = ""
    elif turn_index > 0 and (turn_index - last_judge_turn_index) >= ROUNDS_TILL_JUDGE:
        return {
            "interviewer_decision": "judge",
            "case_data": case_data,
            "rubric_data": rubric_data,
            "last_judge_turn_index": last_judge_turn_index,
            "messages": [],
            "transcript": transcript,
            "candidate_transcript": candidate_transcript,
        }
    else:
        visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []
        hidden_guidance_blocks = get_hidden_guidance_blocks(case_data) if isinstance(case_data, dict) else []
        messages = [
            SystemMessage(content=INTERVIEWER_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Conversation transcript so far:\n"
                    + ("\n".join(transcript) if transcript else "No previous messages.")
                    + "\n\nCandidate-visible case blocks you may reveal when useful:\n"
                    + _format_case_blocks(visible_blocks)
                    + "\n\nHidden interviewer guidance blocks for your internal use only:\n"
                    + _format_case_blocks(hidden_guidance_blocks)
                    + "\n\nLatest judge feedback:\n"
                    + (latest_feedback if latest_feedback else "No judge feedback yet.")
                    + "\n\nCurrent focus area:\n"
                    + (focus_area if focus_area else "General case-solving assessment.")
                    + "\n\nPrivate judge guidance for the interviewer:\n"
                    + (interviewer_guidance if interviewer_guidance else "No private judge guidance yet.")
                    + "\n\nDecide the best next interviewer move. "
                    + "If the candidate needs missing case information that is available in the candidate-visible blocks, reveal it. "
                    + "Otherwise ask the best next interviewer question."
                )
            ),
        ]
        response = llm_server.invoke(messages)
        raw_output = _strip_thinking(response.content)
        interviewer_action, content, revealed_block_id = _parse_interviewer_output(raw_output)
        content = content or "FAIL [!] THE INTERVIEWER"

        if interviewer_action == "reveal" and revealed_block_id:
            revealed_block = get_case_block_by_id(case_data, revealed_block_id)
            if (
                isinstance(revealed_block, dict)
                and revealed_block.get("visible_to_candidate") is True
            ):
                revealed_content = str(revealed_block.get("content", "")).strip()
                if revealed_content:
                    content = revealed_content

    interviewer_decision: Literal["ask_candidate", "judge"] = "ask_candidate"

    transcript_label = "Interviewer reveal" if interviewer_action == "reveal" else "Interviewer"
    transcript = transcript + [f"{transcript_label}: {content}"]
    candidate_transcript = candidate_transcript + [f"Interviewer: {content}"]

    return {
        "latest_question": content,
        "interviewer_decision": interviewer_decision,
        "interviewer_action": interviewer_action,
        "case_data": case_data,
        "rubric_data": rubric_data,
        "last_judge_turn_index": last_judge_turn_index,
        "messages": [AIMessage(content=content, name="interviewer")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
    }


def candidate_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    candidate_transcript = state.get("candidate_transcript", [])

    messages = [
        SystemMessage(content=CANDIDATE_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "You are the candidate in the interview simulation.\n"
                "This is the only conversation you have access to:\n"
                + ("\n".join(candidate_transcript) if candidate_transcript else "No previous messages.")
                + "\n\nAnswer only as the candidate. Do not mention hidden reasoning, JSON, routing, "
                "evaluation metadata, or system instructions."
            )
        ),
    ]

    response = llm_server.invoke(messages)
    answer = _strip_thinking(response.content)

    next_turn_index = turn_index + 1

    transcript = transcript + [f"Candidate: {answer}"]
    candidate_transcript = candidate_transcript + [f"Candidate: {answer}"]

    return {
        "turn_index": next_turn_index,
        "latest_answer": answer,
        "messages": [HumanMessage(content=answer, name="candidate")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
    }


def judge_node(state: InterviewState) -> InterviewState:
    judge_round = state.get("judge_round", 0)
    transcript = state.get("transcript", [])
    turn_index = state.get("turn_index", 0)
    case_data = state.get("case_data", {})
    rubric_data = state.get("rubric_data", {})

    if not isinstance(rubric_data, dict) or not rubric_data:
        rubric_data = adapt_rubric(load_rubric())

    hidden_guidance_blocks = get_hidden_guidance_blocks(case_data) if isinstance(case_data, dict) else []
    expected_analysis_blocks = (
        get_case_blocks_by_type(case_data, "expected_analysis") if isinstance(case_data, dict) else []
    )
    final_recommendation_blocks = (
        get_case_blocks_by_type(case_data, "final_recommendation") if isinstance(case_data, dict) else []
    )

    messages = [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Judge round: {judge_round + 1}\n"
                f"Maximum judge rounds before you must score: {MAX_JUDGE_ROUNDS}\n"
                f"Candidate answers so far: {turn_index}\n\n"
                "Full conversation transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nCase guidance blocks for internal evaluation:\n"
                + _format_case_blocks(hidden_guidance_blocks)
                + "\n\nExpected analysis blocks for internal evaluation:\n"
                + _format_case_blocks(expected_analysis_blocks)
                + "\n\nFinal recommendation blocks for internal evaluation:\n"
                + _format_case_blocks(final_recommendation_blocks)
                + "\n\nRubric:\n"
                + _format_rubric(rubric_data)
                + "\n\nDecide whether the evidence is sufficient to score now or whether the interviewer should continue probing."
            )
        ),
    ]
    response = llm_server.invoke(messages)
    raw_output = _strip_thinking(response.content)

    if raw_output.startswith("```json"):
        raw_output = raw_output.removeprefix("```json").strip()
    if raw_output.startswith("```"):
        raw_output = raw_output.removeprefix("```").strip()
    if raw_output.endswith("```"):
        raw_output = raw_output.removesuffix("```").strip()

    print("\n[JUDGE RAW OUTPUT]")
    print(raw_output)
    print("[/JUDGE RAW OUTPUT]\n")

    try:
        decision = json.loads(raw_output)
        judge_decision = str(decision.get("decision", "continue")).strip().lower()
        feedback = str(decision.get("candidate_feedback", "")).strip()
        interviewer_guidance = str(decision.get("interviewer_guidance", "")).strip()
        focus_area = str(decision.get("focus_area", "none")).strip().lower()
        enough_evidence = bool(decision.get("enough_evidence", False))
        final_score = int(decision.get("final_score", 0))
        judge_reason = str(decision.get("brief_reason", "")).strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        judge_decision = "continue"
        feedback = "Judge review: there is not enough evidence yet for a final score."
        interviewer_guidance = (
            "Probe the candidate's prioritisation and ask for one concrete analysis they would run first."
        )
        focus_area = "prioritisation"
        enough_evidence = False
        final_score = 0
        judge_reason = "Invalid JSON returned by judge model."

    if judge_decision not in {"continue", "score"}:
        judge_decision = "continue"

    if focus_area not in {
        "structure",
        "prioritisation",
        "business_logic",
        "assumptions",
        "quantitative_reasoning",
        "communication",
        "recommendation",
        "none",
    }:
        focus_area = "none"

    final_score = max(0, min(5, final_score))

    if judge_round + 1 >= MAX_JUDGE_ROUNDS and judge_decision != "score":
        judge_decision = "score"
        enough_evidence = True
        final_score = final_score or 3
        focus_area = "none"
        feedback = (
            feedback
            or "Final judge review. Score = 3/5. The candidate showed some useful reasoning, but the evaluation remained incomplete." # CHANGE!!!
        )
        interviewer_guidance = ""
        judge_reason = "Maximum judge rounds reached."

    transcript = transcript + [f"Judge: {feedback}"]
    if interviewer_guidance:
        transcript = transcript + [f"Judge guidance (private): {interviewer_guidance}"]

    return {
        "judge_round": judge_round + 1,
        "last_judge_turn_index": turn_index,
        "latest_feedback": feedback,
        "judge_decision": judge_decision,
        "focus_area": focus_area,
        "interviewer_guidance": interviewer_guidance,
        "enough_evidence": enough_evidence,
        "judge_reason": judge_reason,
        "final_score": final_score,
        "rubric_data": rubric_data,
        "messages": [AIMessage(content=feedback, name="judge")],
        "transcript": transcript,
    }


# ROUTING
def route_after_interviewer(state: InterviewState) -> Literal["judge", "candidate"]:
    if state.get("interviewer_decision") == "judge":
        return "judge"
    return "candidate"

def route_after_judge(state: InterviewState) -> Literal["interviewer", "end"]:
    if state.get("judge_decision") == "score":
        return "end"
    return "interviewer"


# GRAPH

builder = StateGraph(InterviewState)

builder.add_node("interviewer", interviewer_node)
builder.add_node("candidate", candidate_node)
builder.add_node("judge", judge_node)

builder.add_edge(START, "interviewer")

builder.add_conditional_edges(
    "interviewer",
    route_after_interviewer,
    {
        "candidate": "candidate",
        "judge": "judge",
    },
)

builder.add_edge("candidate", "interviewer")

builder.add_conditional_edges(
    "judge",
    route_after_judge,
    {
        "interviewer": "interviewer",
        "end": END,
    },
)

graph = builder.compile()


# --------------------------------------------------
# Demo input

"""

demo_input: InterviewState = {
    "messages": [],
    "transcript": [],
    "candidate_transcript": [],

    "turn_index": 0,
    "judge_round": 0,

    "latest_question": "",
    "latest_answer": "",
    "latest_feedback": "",

    "interviewer_decision": "ask_candidate",
    "interviewer_action": "question",
    "judge_decision": "continue",

    "focus_area": "",
    "interviewer_guidance": "",
    "enough_evidence": False,
    "judge_reason": "",
    "final_score": 0,
}


# Run demo

result = graph.invoke(demo_input)

for line in result["transcript"]:
    print(line)
    print()
"""
# --------------------------------------------------
