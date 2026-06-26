import json
from typing import Literal

from langchain_core.messages import SystemMessage
# from langgraph.checkpoint.memory import InMemorySaver --> Handled automatically by LangGraph API
from langgraph.graph import END, START, StateGraph

from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
)
from knowledge_base import (
    build_case_knowledge_base,
    build_retrieval_query,
    format_retrieved_chunks,
    retrieve_knowledge_context,
)
from loader import (
    DEFAULT_MAX_JUDGE_ROUNDS,
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
    extract_case_guidance,
    extract_case_prompt,
    extract_case_recommendation,
    format_candidate_persona,
    format_case_blocks,
    format_full_case_data,
    format_rubric,
    load_json_object,
    merge_focus_areas,
    normalize_string_list,
    normalize_eval_payload,
    normalize_focus_areas,
    parse_interviewer_output,
    strip_thinking,
)

MAX_JUDGE_ROUNDS = DEFAULT_MAX_JUDGE_ROUNDS
DEFAULT_THREAD_ID = "main02_default"

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
    # Primary entrypoint for LangSmith / Studio: pass scenario_ref with a synthetic scenario id
    # such as "scenario_01_solventus". If omitted, the loader falls back to a random synthetic scenario.
    selected_ref = scenario_ref or case_name
    bundle = load_selected_simulation_bundle(scenario_ref=selected_ref, seed=seed)
    scenario = bundle["scenario"]
    case_data = bundle["case"]
    knowledge_base = build_case_knowledge_base(case_data)

    return {
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
        "knowledge_base": knowledge_base,
        "retrieved_public_context": [],
        "retrieved_private_context": [],
    }


def load_scenario_node(state: AgenticGraphState) -> AgenticGraphState:
    if state.get("case_prompt") and state.get("case_guidance") and state.get("case_recommendation"):
        return {}

    bundle = load_selected_simulation_bundle(scenario_ref=state.get("scenario_ref"))
    scenario = bundle["scenario"]
    case_data = bundle["case"]
    knowledge_base = build_case_knowledge_base(case_data)

    return {
        "case_prompt": extract_case_prompt(case_data),
        "candidate_profile": scenario.get("candidate_profile", {}),
        "case_guidance": extract_case_guidance(case_data),
        "case_data": case_data,
        "case_recommendation": extract_case_recommendation(case_data),
        "rubric_data": bundle["rubric"],
        "knowledge_base": knowledge_base,
        "retrieved_public_context": [],
        "retrieved_private_context": [],
    }


def interviewer_node(state: AgenticGraphState) -> AgenticGraphState:
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    case_prompt = state.get("case_prompt", "")
    case_data = state.get("case_data", {})
    case_guidance = state.get("case_guidance", "")
    focus_areas = state.get("focus_areas", [])
    knowledge_base = state.get("knowledge_base", {})

    if turn_index == 0 and not transcript:
        content = case_prompt or "Walk me through your approach."
        transcript = transcript + [f"Interviewer: {content}"]
        return {
            "enough_evidence": False,
            "turn_index": turn_index + 1,
            "transcript": transcript,
            "retrieved_public_context": [],
            "retrieved_private_context": [],
        }

    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []
    retrieval_query = build_retrieval_query(case_prompt, transcript, focus_areas)
    public_context = retrieve_knowledge_context(
        knowledge_base if isinstance(knowledge_base, dict) else {},
        retrieval_query,
        top_k=3,
        visibility="candidate_visible",
    )
    private_context = retrieve_knowledge_context(
        knowledge_base if isinstance(knowledge_base, dict) else {},
        retrieval_query,
        top_k=3,
        visibility="interviewer_only",
    )

    messages = [
        SystemMessage(
            content=(
                INTERVIEWER_GRAPH_SYSTEM_PROMPT
                + "\n\nCase prompt:\n"
                + (case_prompt or "None.")
                + "\n\nPublic transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nCandidate-visible case blocks:\n"
                + format_case_blocks(visible_blocks)
                + "\n\nRetrieved candidate-visible context:\n"
                + format_retrieved_chunks(public_context)
                + "\n\nHidden case guidance:\n"
                + (case_guidance or "None.")
                + "\n\nRetrieved interviewer-only context:\n"
                + format_retrieved_chunks(private_context)
                + "\n\nCurrent judge focus areas:\n"
                + (", ".join(focus_areas) if focus_areas else "None.")
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
            if revealed_content:
                content = revealed_content
        else:
            interviewer_action = "question"

    transcript_label = "Interviewer reveal" if interviewer_action == "reveal" else "Interviewer"
    transcript = transcript + [f"{transcript_label}: {content}"]

    return {
        "enough_evidence": ready_for_judge,
        "turn_index": turn_index + 1,
        "transcript": transcript,
        "retrieved_public_context": [
            str(chunk.get("content", "")).strip() for chunk in public_context if str(chunk.get("content", "")).strip()
        ],
        "retrieved_private_context": [
            str(chunk.get("content", "")).strip() for chunk in private_context if str(chunk.get("content", "")).strip()
        ],
    }


def candidate_node(state: AgenticGraphState) -> AgenticGraphState:
    case_prompt = state.get("case_prompt", "")
    candidate_profile = state.get("candidate_profile", {})
    transcript = state.get("transcript", [])
    data_gathered = normalize_string_list(state.get("data_gathered", []))
    visible_transcript = get_candidate_visible_transcript(transcript)

    messages = [
        SystemMessage(
            content=(
                CANDIDATE_SYSTEM_PROMPT
                + "\n\nCase prompt:\n"
                + (case_prompt or "None.")
                + "\n\nSynthetic candidate scenario to follow:\n"
                + format_candidate_persona(candidate_profile if isinstance(candidate_profile, dict) else {})
                + "\n\nThis is the only conversation you can see:\n"
                + ("\n".join(visible_transcript) if visible_transcript else "No previous messages.")
                + "\n\nCurrent factual data_gathered list:\n"
                + ("\n".join(data_gathered) if data_gathered else "None yet.")
                + "\n\nUpdate data_gathered so it contains the factual case information you have learned so far."
            )
        ),
    ]

    response = llm_server.invoke(messages)
    payload = load_json_object(response.content)
    answer = str(payload.get("answer", "")).strip()
    updated_data_gathered = normalize_string_list(payload.get("data_gathered", data_gathered))

    if not answer:
        answer = strip_thinking(response.content)
        updated_data_gathered = data_gathered

    transcript = transcript + [f"Candidate: {answer}"]

    return {
        "transcript": transcript,
        "data_gathered": updated_data_gathered,
    }


def judge_node(state: AgenticGraphState) -> AgenticGraphState:
    judge_round = state.get("judge_round", 0)
    transcript = state.get("transcript", [])
    rubric_data = state.get("rubric_data", {})
    focus_areas = state.get("focus_areas", [])
    knowledge_base = state.get("knowledge_base", {})
    retrieval_query = build_retrieval_query(str(state.get("case_prompt", "")), transcript, focus_areas)
    public_context = retrieve_knowledge_context(
        knowledge_base if isinstance(knowledge_base, dict) else {},
        retrieval_query,
        top_k=4,
        visibility="candidate_visible",
    )
    private_context = retrieve_knowledge_context(
        knowledge_base if isinstance(knowledge_base, dict) else {},
        retrieval_query,
        top_k=4,
        visibility="interviewer_only",
    )

    messages = [
        SystemMessage(
            content=(
                JUDGE_GRAPH_SYSTEM_PROMPT
                + "\n\n"
                + f"Judge round: {judge_round + 1}\n"
                + f"Maximum judge rounds before forcing evaluation: {MAX_JUDGE_ROUNDS}\n\n"
                + "Case prompt:\n"
                + str(state.get("case_prompt", "None."))
                + "\n\n"
                + "Transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nCase guidance:\n"
                + str(state.get("case_guidance", "None."))
                + "\n\nRetrieved candidate-visible context:\n"
                + format_retrieved_chunks(public_context)
                + "\n\nRetrieved interviewer-only context:\n"
                + format_retrieved_chunks(private_context)
                + "\n\nCase data:\n"
                + format_full_case_data(state.get("case_data", {}))
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

    if judge_round + 1 >= MAX_JUDGE_ROUNDS and not enough_evidence:
        enough_evidence = True
        new_focus_areas = []

    merged_focus_areas = focus_areas if enough_evidence else merge_focus_areas(focus_areas, new_focus_areas)
    if enough_evidence:
        merged_focus_areas = []

    return {
        "judge_round": judge_round + 1,
        "enough_evidence": enough_evidence,
        "focus_areas": merged_focus_areas,
    }


def eval_case_performance_node(state: AgenticGraphState) -> AgenticGraphState:
    rubric_data = state.get("rubric_data", {})
    retrieval_query = build_retrieval_query(
        str(state.get("case_prompt", "")),
        state.get("transcript", []),
        state.get("focus_areas", []),
    )
    knowledge_base = state.get("knowledge_base", {})
    private_context = retrieve_knowledge_context(
        knowledge_base if isinstance(knowledge_base, dict) else {},
        retrieval_query,
        top_k=5,
        visibility="interviewer_only",
    )
    messages = [
        SystemMessage(
            content=(
                CASE_EVAL_SYSTEM_PROMPT
                + "\n\nReturn a JSON object with these fields: "
                + ", ".join(CASE_PERFORMANCE_FIELDS)
                + ". Each field must be an object {\"score\": 1-4 or \"not_tested\", \"rationale\": \"short text\"}."
                + "\n\nTranscript:\n"
                + "\n".join(state.get("transcript", []))
                + "\n\nCase guidance:\n"
                + str(state.get("case_guidance", "None."))
                + "\n\nRetrieved interviewer-only context:\n"
                + format_retrieved_chunks(private_context)
                + "\n\nCase data:\n"
                + format_full_case_data(state.get("case_data", {}))
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

    return {
        "case_performance": case_performance,
    }


def eval_dialog_quality_node(state: AgenticGraphState) -> AgenticGraphState:
    rubric_data = state.get("rubric_data", {})
    messages = [
        SystemMessage(
            content=(
                DIALOG_EVAL_SYSTEM_PROMPT
                + "\n\nReturn a JSON object with these fields: "
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
    return {
        "quality_dialog": quality_dialog,
    }


def give_feedback_node(state: AgenticGraphState) -> AgenticGraphState:
    messages = [
        SystemMessage(
            content=(
                FEEDBACK_SYSTEM_PROMPT
                + "\n\nTranscript:\n"
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
        latest_feedback = "Final feedback generated from case performance and dialog quality."

    transcript = state.get("transcript", []) + [
        "Eval Case Performance: structured case-performance assessment completed.",
        "Eval Dialog Quality: structured interaction-quality assessment completed.",
        f"Give Feedback: {latest_feedback}",
    ]
    return {
        "transcript": transcript,
    }


def route_after_interviewer(state: AgenticGraphState) -> Literal["judge", "candidate"]:
    if state.get("enough_evidence") is True:
        return "judge"
    return "candidate"

def route_after_judge_agentic_02(
    state: AgenticGraphState,
) -> Literal["interviewer"] | list[Literal["eval_case_performance", "eval_dialog_quality"]]:
    if state.get("enough_evidence") is True:
        return ["eval_case_performance", "eval_dialog_quality"]
    return "interviewer"


def build_graph_config(thread_id: str | None = None) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id or DEFAULT_THREAD_ID,
        }
    }


builder = StateGraph(AgenticGraphState)
builder.add_node("load_scenario", load_scenario_node)
builder.add_node("interviewer", interviewer_node)
builder.add_node("candidate", candidate_node)
builder.add_node("judge", judge_node)
builder.add_node("eval_case_performance", eval_case_performance_node)
builder.add_node("eval_dialog_quality", eval_dialog_quality_node)
builder.add_node("give_feedback", give_feedback_node)

builder.add_edge(START, "load_scenario")
builder.add_edge("load_scenario", "interviewer")
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
    route_after_judge_agentic_02,
    {
        "interviewer": "interviewer",
        "eval_case_performance": "eval_case_performance",
        "eval_dialog_quality": "eval_dialog_quality",
    },
)
builder.add_edge(["eval_case_performance", "eval_dialog_quality"], "give_feedback")
builder.add_edge("give_feedback", END)

# checkpointer = InMemorySaver()
# graph = builder.compile(checkpointer=checkpointer)

graph = builder.compile()
