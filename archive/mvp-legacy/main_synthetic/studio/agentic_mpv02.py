import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
)
from loader import (
    DEFAULT_MAX_JUDGE_ROUNDS,
    ROUNDS_TILL_JUDGE,
    load_selected_simulation_bundle,
)
from llm_server import llm_server
from prompts import (
    CANDIDATE_SYSTEM_PROMPT,
    CASE_EVAL_SYSTEM_PROMPT,
    DIALOG_EVAL_SYSTEM_PROMPT,
    FEEDBACK_SYSTEM_PROMPT,
    INTERVIEWER_GRAPH_SYSTEM_PROMPT,
    JUDGE_GRAPH_SYSTEM_PROMPT,
)
from state import AgenticGraphState
from utils import (
    append_focus_areas,
    compute_final_score,
    extract_case_guidance,
    extract_case_prompt,
    extract_case_recommendation,
    format_candidate_persona,
    format_case_blocks,
    format_rubric,
    load_json_object,
    normalize_eval_payload,
    normalize_focus_areas,
    parse_interviewer_output,
    strip_thinking,
)

MAX_JUDGE_ROUNDS = DEFAULT_MAX_JUDGE_ROUNDS

CASE_PERFORMANCE_FIELDS = [
    "case_opening",
    "case_structure",
    "case_math_answer",
    "case_creative_answer",
    "final_recommendation",
    "overall_structure",
    "overall_problem_solving",
    "overall_communication",
]

QUALITY_DIALOG_FIELDS = [
    "clarity_and_concision",
    "responsiveness_and_adaptation",
    "groundedness",
    "confidence_calibration",
    "multi_turn_coherence",
]


def get_candidate_visible_transcript(transcript: list[str]) -> list[str]:
    visible_prefixes = ("Interviewer:", "Interviewer reveal:", "Candidate:")
    return [line for line in transcript if line.startswith(visible_prefixes)]



def build_initial_interview_state(
    case_name: str | None = None,
    seed: int | None = None,
    scenario_ref: str | None = None,
) -> AgenticGraphState:
    selected_ref = scenario_ref or case_name
    bundle = load_selected_simulation_bundle(scenario_ref=selected_ref, seed=seed)
    scenario = bundle["scenario"]
    case_data = bundle["case"]

    return {
        "messages": [],
        "scenario_ref": selected_ref or str(scenario.get("scenario_id", "")),
        "case_prompt": extract_case_prompt(case_data),
        "candidate_profile": scenario.get("candidate_profile", {}),
        "turn_index": 0,
        "transcript": [],
        "case_guidance": extract_case_guidance(case_data),
        "case_data": case_data,
        "enough_evidence": False,
        "focus_areas": [],
        "case_recommendation": extract_case_recommendation(case_data),
        "case_performance": {},
        "quality_dialog": {},
        "data_gathered": [],
        "rubric_data": bundle["rubric"],
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
        "judge_reason": "",
        "final_score": 0,
    }


def retrieve_case_node(state: AgenticGraphState) -> AgenticGraphState:
    if state.get("case_prompt") and state.get("case_guidance") and state.get("case_recommendation"):
        return {}

    bundle = load_selected_simulation_bundle(scenario_ref=state.get("scenario_ref"))
    scenario = bundle["scenario"]
    case_data = bundle["case"]

    return {
        "case_prompt": extract_case_prompt(case_data),
        "candidate_profile": scenario.get("candidate_profile", {}),
        "case_guidance": extract_case_guidance(case_data),
        "case_data": case_data,
        "case_recommendation": extract_case_recommendation(case_data),
        "rubric_data": bundle["rubric"],
    }


def interviewer_node(state: AgenticGraphState) -> AgenticGraphState:
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    case_prompt = state.get("case_prompt", "")
    case_data = state.get("case_data", {})
    case_guidance = state.get("case_guidance", "")
    focus_areas = state.get("focus_areas", [])
    interviewer_guidance = state.get("interviewer_guidance", "")
    last_judge_turn_index = state.get("last_judge_turn_index", 0)
    latest_answer = state.get("latest_answer", "")
    data_gathered = list(state.get("data_gathered", []))

    if turn_index == 0 and not transcript:
        content = case_prompt or "Walk me through your approach."
        transcript = transcript + [f"Interviewer: {content}"]
        return {
            "latest_question": content,
            "interviewer_decision": "ask_candidate",
            "interviewer_action": "question",
            "messages": [AIMessage(content=content, name="interviewer")],
            "transcript": transcript,
        }

    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []
    messages = [
        SystemMessage(content=INTERVIEWER_GRAPH_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Case prompt:\n"
                + (case_prompt or "None.")
                + "\n\nPublic transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nCandidate-visible case blocks:\n"
                + format_case_blocks(visible_blocks)
                + "\n\nHidden case guidance:\n"
                + (case_guidance or "None.")
                + "\n\nCurrent judge focus areas:\n"
                + (", ".join(focus_areas) if focus_areas else "None.")
                + "\n\nPrivate interviewer guidance from judge:\n"
                + (interviewer_guidance or "None.")
                + "\n\nDecide the best next interviewer move."
            )
        ),
    ]
    response = llm_server.invoke(messages)
    interviewer_action, content, revealed_block_id, ready_for_judge = parse_interviewer_output(response.content)

    if interviewer_action == "reveal" and revealed_block_id:
        revealed_block = get_case_block_by_id(case_data, revealed_block_id)
        if isinstance(revealed_block, dict) and revealed_block.get("visible_to_candidate") is True:
            revealed_content = str(revealed_block.get("content", "")).strip()
            title = str(revealed_block.get("title", "")).strip() or revealed_block_id
            if revealed_content:
                content = revealed_content
            data_gathered = data_gathered + [title]
        else:
            interviewer_action = "question"

    auto_ready = (
        turn_index > 0
        and bool(latest_answer.strip())
        and (turn_index - last_judge_turn_index) >= ROUNDS_TILL_JUDGE
    )
    if "recommend" in latest_answer.lower() and turn_index >= 2:
        auto_ready = True

    interviewer_decision: Literal["ask_candidate", "judge"] = "judge" if (ready_for_judge or auto_ready) else "ask_candidate"
    transcript_label = "Interviewer reveal" if interviewer_action == "reveal" else "Interviewer"
    transcript = transcript + [f"{transcript_label}: {content}"]

    return {
        "latest_question": content,
        "interviewer_decision": interviewer_decision,
        "interviewer_action": interviewer_action,
        "messages": [AIMessage(content=content, name="interviewer")],
        "transcript": transcript,
        "data_gathered": data_gathered,
    }


def candidate_node(state: AgenticGraphState) -> AgenticGraphState:
    turn_index = state.get("turn_index", 0)
    candidate_profile = state.get("candidate_profile", {})
    transcript = state.get("transcript", [])
    visible_transcript = get_candidate_visible_transcript(transcript)

    messages = [
        SystemMessage(content=CANDIDATE_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Synthetic candidate scenario to follow:\n"
                + format_candidate_persona(candidate_profile if isinstance(candidate_profile, dict) else {})
                + "\n\nThis is the only conversation you can see:\n"
                + ("\n".join(visible_transcript) if visible_transcript else "No previous messages.")
                + "\n\nAnswer only as the candidate."
            )
        ),
    ]

    response = llm_server.invoke(messages)
    answer = strip_thinking(response.content)
    transcript = transcript + [f"Candidate: {answer}"]

    return {
        "turn_index": turn_index + 1,
        "latest_answer": answer,
        "messages": [HumanMessage(content=answer, name="candidate")],
        "transcript": transcript,
    }


def judge_node(state: AgenticGraphState) -> AgenticGraphState:
    judge_round = state.get("judge_round", 0)
    transcript = state.get("transcript", [])
    rubric_data = state.get("rubric_data", {})
    focus_areas = state.get("focus_areas", [])

    messages = [
        SystemMessage(content=JUDGE_GRAPH_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Judge round: {judge_round + 1}\n"
                f"Maximum judge rounds before forcing evaluation: {MAX_JUDGE_ROUNDS}\n\n"
                "Transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nCase guidance:\n"
                + str(state.get("case_guidance", "None."))
                + "\n\nCase data:\n"
                + format_case_blocks(get_candidate_visible_blocks(state.get("case_data", {})))
                + "\n\nExpected recommendation:\n"
                + str(state.get("case_recommendation", "None."))
                + "\n\nRubric:\n"
                + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
            )
        ),
    ]
    response = llm_server.invoke(messages)
    payload = load_json_object(response.content)

    enough_evidence = bool(payload.get("enough_evidence", False))
    new_focus_areas = normalize_focus_areas(payload.get("focus_areas", []))
    interviewer_guidance = str(payload.get("interviewer_guidance", "")).strip()
    candidate_feedback = str(payload.get("candidate_feedback", "")).strip()
    judge_reason = str(payload.get("brief_reason", "")).strip()

    if judge_round + 1 >= MAX_JUDGE_ROUNDS and not enough_evidence:
        enough_evidence = True
        new_focus_areas = []
        interviewer_guidance = ""
        candidate_feedback = candidate_feedback or "Judge note: maximum review rounds reached, moving to final evaluation."
        judge_reason = judge_reason or "Maximum judge rounds reached."

    merged_focus_areas = focus_areas if enough_evidence else append_focus_areas(focus_areas, new_focus_areas)
    if enough_evidence:
        merged_focus_areas = []

    judge_decision: Literal["continue", "score"] = "score" if enough_evidence else "continue"
    visible_feedback = candidate_feedback or (
        "Judge note: enough evidence collected for evaluation."
        if enough_evidence
        else "Judge note: more evidence is needed before evaluation."
    )
    transcript = transcript + [f"Judge: {visible_feedback}"]
    if interviewer_guidance:
        transcript = transcript + [f"Judge guidance (private): {interviewer_guidance}"]

    primary_focus_area = merged_focus_areas[-1] if merged_focus_areas else "none"
    return {
        "judge_round": judge_round + 1,
        "last_judge_turn_index": state.get("turn_index", 0),
        "enough_evidence": enough_evidence,
        "focus_areas": merged_focus_areas,
        "latest_feedback": visible_feedback,
        "judge_decision": judge_decision,
        "focus_area": primary_focus_area,
        "interviewer_guidance": interviewer_guidance,
        "judge_reason": judge_reason,
        "messages": [AIMessage(content=visible_feedback, name="judge")],
        "transcript": transcript,
    }


def eval_case_performance_node(state: AgenticGraphState) -> AgenticGraphState:
    rubric_data = state.get("rubric_data", {})
    messages = [
        SystemMessage(content=CASE_EVAL_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Return a JSON object with these fields: "
                + ", ".join(CASE_PERFORMANCE_FIELDS)
                + ". Each field must be an object {\"score\": 1-4 or \"not_tested\", \"rationale\": \"short text\"}."
                + "\n\nTranscript:\n"
                + "\n".join(state.get("transcript", []))
                + "\n\nCase guidance:\n"
                + str(state.get("case_guidance", "None."))
                + "\n\nCase data:\n"
                + format_case_blocks(get_candidate_visible_blocks(state.get("case_data", {})))
                + "\n\nExpected recommendation:\n"
                + str(state.get("case_recommendation", "None."))
                + "\n\nRubric:\n"
                + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
            )
        ),
    ]
    response = llm_server.invoke(messages)
    payload = load_json_object(response.content)
    case_performance = normalize_eval_payload(payload, CASE_PERFORMANCE_FIELDS)

    transcript = state.get("transcript", []) + [
        "Eval Case Performance: structured case-performance assessment completed."
    ]
    return {
        "case_performance": case_performance,
        "transcript": transcript,
    }


def eval_dialog_quality_node(state: AgenticGraphState) -> AgenticGraphState:
    rubric_data = state.get("rubric_data", {})
    messages = [
        SystemMessage(content=DIALOG_EVAL_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Return a JSON object with these fields: "
                + ", ".join(QUALITY_DIALOG_FIELDS)
                + ". Each field must be an object {\"score\": 1-4 or \"not_tested\", \"rationale\": \"short text\"}."
                + "\n\nTranscript:\n"
                + "\n".join(state.get("transcript", []))
                + "\n\nRubric:\n"
                + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
            )
        ),
    ]
    response = llm_server.invoke(messages)
    payload = load_json_object(response.content)
    quality_dialog = normalize_eval_payload(payload, QUALITY_DIALOG_FIELDS)
    final_score = compute_final_score(state.get("case_performance", {}), quality_dialog)

    transcript = state.get("transcript", []) + [
        "Eval Dialog Quality: structured interaction-quality assessment completed."
    ]
    return {
        "quality_dialog": quality_dialog,
        "final_score": final_score,
        "transcript": transcript,
    }


def give_feedback_node(state: AgenticGraphState) -> AgenticGraphState:
    messages = [
        SystemMessage(content=FEEDBACK_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Transcript:\n"
                + "\n".join(state.get("transcript", []))
                + "\n\nCase performance:\n"
                + json.dumps(state.get("case_performance", {}), ensure_ascii=True, indent=2)
                + "\n\nDialog quality:\n"
                + json.dumps(state.get("quality_dialog", {}), ensure_ascii=True, indent=2)
            )
        ),
    ]
    response = llm_server.invoke(messages)
    latest_feedback = strip_thinking(response.content).strip()
    if not latest_feedback:
        latest_feedback = f"Final feedback generated. Overall score: {state.get('final_score', 0)}/4."

    transcript = state.get("transcript", []) + [f"Give Feedback: {latest_feedback}"]
    return {
        "latest_feedback": latest_feedback,
        "messages": [AIMessage(content=latest_feedback, name="feedback")],
        "transcript": transcript,
    }


def route_after_interviewer(state: AgenticGraphState) -> Literal["judge", "candidate"]:
    if state.get("interviewer_decision") == "judge":
        return "judge"
    return "candidate"


def route_after_judge(state: AgenticGraphState) -> Literal["interviewer", "end"]:
    if state.get("judge_decision") == "score" or state.get("enough_evidence") is True:
        return "end"
    return "interviewer"


def route_after_judge_agentic_02(
    state: AgenticGraphState,
) -> Literal["interviewer", "eval_case_performance"]:
    if state.get("enough_evidence") is True:
        return "eval_case_performance"
    return "interviewer"


builder = StateGraph(AgenticGraphState)
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


agentic_02_builder = StateGraph(AgenticGraphState)
agentic_02_builder.add_node("retrieve_case", retrieve_case_node)
agentic_02_builder.add_node("interviewer", interviewer_node)
agentic_02_builder.add_node("candidate", candidate_node)
agentic_02_builder.add_node("judge", judge_node)
agentic_02_builder.add_node("eval_case_performance", eval_case_performance_node)
agentic_02_builder.add_node("eval_dialog_quality", eval_dialog_quality_node)
agentic_02_builder.add_node("give_feedback", give_feedback_node)

agentic_02_builder.add_edge(START, "retrieve_case")
agentic_02_builder.add_edge("retrieve_case", "interviewer")
agentic_02_builder.add_conditional_edges(
    "interviewer",
    route_after_interviewer,
    {
        "candidate": "candidate",
        "judge": "judge",
    },
)
agentic_02_builder.add_edge("candidate", "interviewer")
agentic_02_builder.add_conditional_edges(
    "judge",
    route_after_judge_agentic_02,
    {
        "interviewer": "interviewer",
        "eval_case_performance": "eval_case_performance",
    },
)
agentic_02_builder.add_edge("eval_case_performance", "eval_dialog_quality")
agentic_02_builder.add_edge("eval_dialog_quality", "give_feedback")
agentic_02_builder.add_edge("give_feedback", END)

agentic_02_graph = agentic_02_builder.compile()
