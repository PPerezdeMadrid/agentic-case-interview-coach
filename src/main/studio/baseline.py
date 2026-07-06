import json
from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
)
from rag.knowledge_base import (
    build_profitability_knowledge_base,
    build_profitability_retrieval_query,
    format_retrieved_chunks,
    retrieve_knowledge_context,
)
from loader import load_selected_simulation_bundle
from llm_server import llm_server
from persistence import make_persist_run_node, resolve_thread_id
from prompts import (
    BASELINE_GRAPH_SYSTEM_PROMPT,
    CANDIDATE_SYSTEM_PROMPT,
    CASE_EVAL_SYSTEM_PROMPT,
    DIALOG_EVAL_SYSTEM_PROMPT,
    FEEDBACK_SYSTEM_PROMPT,
)
from rag.rag_case_guide import retrieve_case_guide_context
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
    normalize_eval_payload,
    normalize_string_list,
    strip_thinking,
)

DEFAULT_THREAD_ID = "main_baseline"
MAX_BASELINE_TURNS = 4

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


class GraphConfig(TypedDict, total=False):
    thread_id: str


def get_candidate_visible_transcript(transcript: list[str]) -> list[str]:
    visible_prefixes = ("Interviewer:", "Interviewer reveal:", "Candidate:")
    return [line for line in transcript if line.startswith(visible_prefixes)]


def format_case_guide_snippets(case_guide_context: list[str]) -> str:
    if not case_guide_context:
        return "None."
    return "\n".join(f"- {snippet}" for snippet in case_guide_context)


def resolve_case_guide_query(state: AgenticGraphState) -> str:
    case_prompt = str(state.get("case_prompt", "")).strip()
    if case_prompt:
        return case_prompt

    bundle = load_selected_simulation_bundle(scenario_ref=state.get("scenario_ref"))
    return str(extract_case_prompt(bundle["case"])).strip()


def build_initial_baseline_state(
    case_name: str | None = None,
    seed: int | None = None,
    scenario_ref: str | None = None,
) -> AgenticGraphState:
    selected_ref = scenario_ref or case_name
    bundle = load_selected_simulation_bundle(scenario_ref=selected_ref, seed=seed)
    scenario = bundle["scenario"]
    case_data = bundle["case"]
    profitability_knowledge_base = build_profitability_knowledge_base(case_data)

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
        "thread_id": DEFAULT_THREAD_ID,
        "rubric_data": bundle["rubric"],
        "judge_round": 0,
        "profitability_knowledge_base": profitability_knowledge_base,
        "retrieved_profitability_context": [],
        "case_guide_context": [],
    }


def load_scenario_node(
    state: AgenticGraphState,
    config: RunnableConfig | None = None,
) -> AgenticGraphState:
    thread_id = resolve_thread_id(state, config)
    if state.get("case_prompt") and state.get("case_guidance") and state.get("case_recommendation"):
        return {"thread_id": thread_id}

    bundle = load_selected_simulation_bundle(scenario_ref=state.get("scenario_ref"))
    scenario = bundle["scenario"]
    case_data = bundle["case"]
    profitability_knowledge_base = build_profitability_knowledge_base(case_data)

    return {
        "thread_id": thread_id,
        "scenario_ref": str(state.get("scenario_ref") or scenario.get("scenario_id", "")),
        "case_prompt": extract_case_prompt(case_data),
        "candidate_profile": scenario.get("candidate_profile", {}),
        "case_guidance": extract_case_guidance(case_data),
        "case_data": case_data,
        "case_recommendation": extract_case_recommendation(case_data),
        "rubric_data": bundle["rubric"],
        "profitability_knowledge_base": profitability_knowledge_base,
        "retrieved_profitability_context": [],
        "case_guide_context": [],
    }


def retrieve_case_guide_node(state: AgenticGraphState) -> AgenticGraphState:
    query = resolve_case_guide_query(state) or "consulting case interview methodology"
    case_guide_chunks = retrieve_case_guide_context(query, top_k=4)
    return {
        "case_guide_context": [
            str(chunk.get("content", "")).strip()
            for chunk in case_guide_chunks
            if str(chunk.get("content", "")).strip()
        ],
    }


def parse_baseline_output(raw_output: str) -> tuple[str, str, str, bool]:
    payload = load_json_object(raw_output)
    action = str(payload.get("action", "question")).strip().lower()
    content = str(payload.get("content", "")).strip()
    block_id = str(payload.get("block_id", "")).strip()
    ready_for_evaluation = bool(payload.get("ready_for_evaluation", False))

    if action not in {"question", "reveal", "evaluate"}:
        action = "question"
    if action == "evaluate":
        return action, "", "", True
    if not content:
        content = "Could you walk me through your approach?"
    return action, content, block_id, ready_for_evaluation


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


def evaluate_case_performance(state: AgenticGraphState) -> dict:
    rubric_data = state.get("rubric_data", {})
    retrieval_query = build_profitability_retrieval_query(
        str(state.get("case_prompt", "")),
        state.get("transcript", []),
        evaluation_target="case_performance",
        focus_areas=state.get("focus_areas", []),
    )
    profitability_knowledge_base = state.get("profitability_knowledge_base", {})
    profitability_context = retrieve_knowledge_context(
        profitability_knowledge_base if isinstance(profitability_knowledge_base, dict) else {},
        retrieval_query,
        top_k=5,
        visibility="all",
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
                + "\n\nRetrieved profitability methodology context:\n"
                + format_retrieved_chunks(profitability_context)
                + "\n\nCase data:\n"
                + format_full_case_data(state.get("case_data", {}))
                + "\n\nExpected recommendation:\n"
                + str(state.get("case_recommendation", "None."))
                + "\n\nRubric:\n"
                + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(state.get("case_guide_context", []))
            )
        ),
    ]
    response = llm_server.invoke(messages)
    payload = load_json_object(response.content)
    case_performance = normalize_eval_payload(payload, CASE_PERFORMANCE_FIELDS)
    return {
        "case_performance": case_performance,
        "retrieved_profitability_context": [
            str(chunk.get("content", "")).strip()
            for chunk in profitability_context
            if str(chunk.get("content", "")).strip()
        ],
    }


def evaluate_dialog_quality(state: AgenticGraphState) -> dict:
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
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(state.get("case_guide_context", []))
            )
        ),
    ]
    response = llm_server.invoke(messages)
    payload = load_json_object(response.content)
    return normalize_eval_payload(payload, QUALITY_DIALOG_FIELDS)


def generate_final_feedback(transcript: list[str], case_performance: dict, quality_dialog: dict) -> str:
    messages = [
        SystemMessage(
            content=(
                FEEDBACK_SYSTEM_PROMPT
                + "\n\nTranscript:\n"
                + "\n".join(transcript)
                + "\n\nCase performance:\n"
                + json.dumps(case_performance, ensure_ascii=True, indent=2)
                + "\n\nDialog quality:\n"
                + json.dumps(quality_dialog, ensure_ascii=True, indent=2)
            )
        ),
    ]
    response = llm_server.invoke(messages)
    latest_feedback = strip_thinking(response.content).strip()
    return latest_feedback or "Final feedback generated from case performance and dialog quality."


def baseline_node(state: AgenticGraphState) -> AgenticGraphState:
    case_prompt = state.get("case_prompt", "")
    candidate_profile = state.get("candidate_profile", {})
    case_data = state.get("case_data", {})
    case_guidance = state.get("case_guidance", "")
    case_recommendation = state.get("case_recommendation", "")
    rubric_data = state.get("rubric_data", {})
    profitability_knowledge_base = state.get("profitability_knowledge_base", {})
    case_guide_context = state.get("case_guide_context", [])

    transcript = list(state.get("transcript", []))
    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []

    if not transcript:
        opening = case_prompt or "Walk me through your approach."
        return {
            "turn_index": 1,
            "transcript": transcript + [f"Interviewer: {opening}"],
            "enough_evidence": False,
        }

    turn_index = int(state.get("turn_index", 0))
    if turn_index >= MAX_BASELINE_TURNS:
        enough_evidence = True
    else:
        retrieval_query = build_profitability_retrieval_query(
            str(case_prompt),
            transcript,
            evaluation_target="baseline_interviewer",
        )
        profitability_context = retrieve_knowledge_context(
            profitability_knowledge_base if isinstance(profitability_knowledge_base, dict) else {},
            retrieval_query,
            top_k=3,
            visibility="all",
        )
        messages = [
            SystemMessage(
                content=(
                    BASELINE_GRAPH_SYSTEM_PROMPT
                    + "\n\nCurrent interviewer turn: "
                    + str(turn_index)
                    + "\nMaximum interviewer turns before forced evaluation: "
                    + str(MAX_BASELINE_TURNS)
                    + "\n\nPublic transcript:\n"
                    + ("\n".join(transcript) if transcript else "No previous messages.")
                    + "\n\nCase prompt:\n"
                    + (case_prompt or "None.")
                    + "\n\nRetrieved profitability methodology context:\n"
                    + format_retrieved_chunks(profitability_context)
                    + "\n\nCandidate-visible case blocks:\n"
                    + format_case_blocks(visible_blocks)
                    + "\n\nHidden case guidance:\n"
                    + (case_guidance or "None.")
                    + "\n\nCase data:\n"
                    + format_full_case_data(case_data if isinstance(case_data, dict) else {})
                    + "\n\nExpected recommendation:\n"
                    + (case_recommendation or "None.")
                    + "\n\nRubric:\n"
                    + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
                    + "\n\nConsulting Case Interview Guide excerpts:\n"
                    + format_case_guide_snippets(case_guide_context)
                )
            ),
        ]
        response = llm_server.invoke(messages)
        action, content, revealed_block_id, enough_evidence = parse_baseline_output(response.content)

        if action == "reveal" and revealed_block_id:
            revealed_block = get_case_block_by_id(case_data, revealed_block_id)
            if isinstance(revealed_block, dict) and revealed_block.get("visible_to_candidate") is True:
                revealed_content = str(revealed_block.get("content", "")).strip()
                if revealed_content:
                    content = revealed_content
            else:
                action = "question"
                content = "Could you walk me through your approach?"

        if not enough_evidence:
            transcript_label = "Interviewer reveal" if action == "reveal" else "Interviewer"
            return {
                "turn_index": turn_index + 1,
                "transcript": transcript + [f"{transcript_label}: {content}"],
                "enough_evidence": False,
                "retrieved_profitability_context": [
                    str(chunk.get("content", "")).strip()
                    for chunk in profitability_context
                    if str(chunk.get("content", "")).strip()
                ],
            }

    final_state: AgenticGraphState = {
        **state,
        "turn_index": turn_index,
        "transcript": transcript,
        "enough_evidence": True,
    }
    case_performance_payload = evaluate_case_performance(final_state)
    case_performance = case_performance_payload["case_performance"]
    quality_dialog = evaluate_dialog_quality(final_state)
    latest_feedback = generate_final_feedback(transcript, case_performance, quality_dialog)
    return {
        "turn_index": turn_index,
        "transcript": transcript
        + [
            "Eval Case Performance: structured case-performance assessment completed.",
            "Eval Dialog Quality: structured interaction-quality assessment completed.",
            f"Give Feedback: {latest_feedback}",
        ],
        "enough_evidence": True,
        "case_performance": case_performance,
        "quality_dialog": quality_dialog,
        "retrieved_profitability_context": case_performance_payload["retrieved_profitability_context"],
    }


def route_after_baseline(
    state: AgenticGraphState,
) -> Literal["candidate", "end"]:
    if state.get("enough_evidence") is True:
        return "end"
    return "candidate"


def build_graph_config(thread_id: str | None = None) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id or DEFAULT_THREAD_ID,
        }
    }


builder = StateGraph(AgenticGraphState, config_schema=GraphConfig)
builder.add_node("load_scenario", load_scenario_node)
builder.add_node("retrieve_case_guide", retrieve_case_guide_node)
builder.add_node("baseline", baseline_node)
builder.add_node("candidate", candidate_node)
builder.add_node("persist_run", make_persist_run_node("baseline"))

builder.add_edge(START, "load_scenario")
builder.add_edge(START, "retrieve_case_guide")
builder.add_edge(["load_scenario", "retrieve_case_guide"], "baseline")
builder.add_conditional_edges(
    "baseline",
    route_after_baseline,
    {
        "candidate": "candidate",
        "end": "persist_run",
    },
)
builder.add_edge("candidate", "baseline")
builder.add_edge("persist_run", END)

graph = builder.compile()
