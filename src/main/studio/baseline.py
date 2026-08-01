import os
import time
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from adapter import get_candidate_visible_blocks
from rag.case_guide_context import (
    CASE_GUIDE_CITATION_LABEL,
    CASE_GUIDE_SOURCE_DESCRIPTION,
    format_case_guide_snippets,
    get_pending_case_guide_context,
)
from rag.profitability_guide_context import (
    PROFITABILITY_CITATION_LABEL,
    PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
    format_profitability_guide_context,
    format_profitability_guide_snippet,
    retrieve_profitability_guide_context,
)
from llm_server import baseline_llm_server, candidate_llm_server, candidate_llm_server_gpu
from persistence import build_initial_graph_state, load_scenario_node, make_persist_run_node, make_trace_node
from prompts import (
    BASELINE_GRAPH_SYSTEM_PROMPT,
    CANDIDATE_SYSTEM_PROMPT,
)
from state import BaselineState, BaselineTurnOutput
from utils import (
    candidate_transcript_messages,
    extract_token_usage,
    format_candidate_persona,
    format_case_blocks,
    format_full_case_data,
    format_rubric,
    get_candidate_visible_transcript,
    invoke_json_llm,
    load_json_object,
    normalize_eval_payload,
    normalize_string_list,
    resolve_reveal_content,
    strip_thinking,
)

candidate_llm = candidate_llm_server # candidate_llm_server_gpu
baseline_llm = baseline_llm_server

DEFAULT_THREAD_ID = "main_baseline"
MAX_BASELINE_TURNS = int(os.getenv("MAX_BASELINE_TURNS", "15"))
MAX_BASELINE_JSON_RETRIES = int(os.getenv("MAX_BASELINE_JSON_RETRIES", "3"))

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


def get_pending_profitability_guide_context(
    state: BaselineState,
    *,
    top_k: int,
) -> tuple[list[dict], dict]:
    """Fetch the profitability excerpt the *previous* baseline turn asked for,
    if any. Baseline has no separate scouting call -- the single combined
    schema (see BaselineTurnOutput.profitability_query) lets the model flag a
    query opportunistically while producing its move, so the earliest that
    query can be resolved and shown back to the model is the following turn.

    Returns (chunks, rag_query_log_entry).
    """
    query = str(state.get("pending_profitability_query", "") or "").strip()
    if not query:
        return [], {}

    chunks = retrieve_profitability_guide_context(query, top_k=top_k)
    log_entry = {
        "node": "baseline",
        "source": "profitability_guide",
        "query": query,
        "top_k": top_k,
        "chunk_ids": [chunk.get("chunk_id") for chunk in chunks],
    }
    return chunks, log_entry


def build_initial_baseline_state(
    case_name: str | None = None,
    seed: int | None = None,
    scenario_ref: str | None = None,
) -> BaselineState:
    return build_initial_graph_state(
        case_name=case_name,
        seed=seed,
        scenario_ref=scenario_ref,
        thread_id=DEFAULT_THREAD_ID,
    )


def parse_baseline_output(payload: dict, *, require_evaluate: bool = False) -> dict | None:
    """Parse the baseline's single unified per-turn payload."""
    if not payload:
        return None

    action = str(payload.get("action", "question")).strip().lower()
    reasoning = str(payload.get("reasoning", "")).strip()

    if action not in {"question", "reveal", "evaluate"}:
        return None
    if require_evaluate and action != "evaluate":
        return None

    if action == "evaluate":
        case_performance_raw = payload.get("case_performance")
        quality_dialog_raw = payload.get("quality_dialog")
        feedback = str(payload.get("feedback") or "").strip()
        if not isinstance(case_performance_raw, dict) or not isinstance(quality_dialog_raw, dict):
            return None
        if not feedback:
            return None
        return {
            "action": "evaluate",
            "content": "",
            "block_id": "",
            "case_guide_query": "",
            "profitability_query": "",
            "ready_for_evaluation": True,
            "reasoning": reasoning,
            "case_performance": normalize_eval_payload(case_performance_raw, CASE_PERFORMANCE_FIELDS),
            "quality_dialog": normalize_eval_payload(quality_dialog_raw, QUALITY_DIALOG_FIELDS),
            "feedback": feedback,
        }

    content = str(payload.get("content", "")).strip()
    if not content:
        return None
    return {
        "action": action,
        "content": content,
        "block_id": str(payload.get("block_id", "")).strip(),
        "case_guide_query": str(payload.get("case_guide_query", "")).strip(),
        "profitability_query": str(payload.get("profitability_query", "")).strip(),
        "ready_for_evaluation": bool(payload.get("ready_for_evaluation", False)),
        "reasoning": reasoning,
        "case_performance": None,
        "quality_dialog": None,
        "feedback": None,
    }


def _invoke_baseline_move(messages: list[SystemMessage], *, force_evaluation: bool) -> tuple[dict, list[dict]]:
    """Call the baseline's single combined model for this turn, with JSON-repair
    retries via invoke_json_llm, mirroring node.py's interviewer/eval nodes."""

    def on_exhausted(_raw_output: str) -> dict:
        if force_evaluation:
            return {
                "reasoning": "",
                "action": "evaluate",
                "content": "",
                "block_id": "",
                "case_guide_query": "",
                "profitability_query": "",
                "ready_for_evaluation": True,
                "case_performance": {},
                "quality_dialog": {},
                "feedback": "Final feedback generated from case performance and dialog quality.",
            }
        return {
            "reasoning": "",
            "action": "question",
            "content": "I need one concrete next step from you. Which area would you like to analyze first: revenue or costs?",
            "block_id": "",
            "case_guide_query": "",
            "profitability_query": "",
            "ready_for_evaluation": False,
        }

    payload, usage_log = invoke_json_llm(
        baseline_llm,
        messages,
        node="baseline_move",
        schema=BaselineTurnOutput,
        accept=lambda candidate: parse_baseline_output(candidate, require_evaluate=force_evaluation) is not None,
        on_exhausted=on_exhausted,
        retries=MAX_BASELINE_JSON_RETRIES,
    )
    parsed = parse_baseline_output(payload, require_evaluate=force_evaluation)
    if parsed is None:
        parsed = parse_baseline_output(on_exhausted(""), require_evaluate=force_evaluation)
    return parsed, usage_log


def candidate_node(state: BaselineState) -> BaselineState:
    candidate_profile = state.get("candidate_profile", {})
    transcript = state.get("transcript", [])
    data_gathered = normalize_string_list(state.get("data_gathered", []))
    visible_transcript = get_candidate_visible_transcript(transcript)

    messages = [
        SystemMessage(content=CANDIDATE_SYSTEM_PROMPT),
        SystemMessage(
            content=(
                "Synthetic candidate scenario to follow:\n"
                + format_candidate_persona(candidate_profile if isinstance(candidate_profile, dict) else {})
            )
        ),
        *candidate_transcript_messages(visible_transcript),
        HumanMessage(
            content=(
                "Current factual data_gathered list:\n"
                + ("\n".join(data_gathered) if data_gathered else "None yet.")
                + "\n\nUpdate data_gathered so it contains the factual case information you have learned so far."
            )
        ),
    ]

    started_at = time.perf_counter()
    response = candidate_llm.invoke(messages)
    usage_entry = extract_token_usage(
        response, node="baseline_candidate", model=candidate_llm.model_name, duration_seconds=time.perf_counter() - started_at
    )
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
        "llm_usage": [usage_entry],
    }


def _build_baseline_messages(
    case_prompt: str,
    case_data: dict,
    case_guidance: str,
    case_recommendation: str,
    rubric_data: dict,
    transcript: list[str],
    visible_blocks: list[dict],
    turn_index: int,
    case_guide_context: list[dict],
    profitability_context: list[dict],
) -> list[SystemMessage]:
    """Pure prompt-assembly for one baseline turn -- no LLM call, no RAG lookup,
    factored out of baseline_node so a golden-set harness can call the exact
    rendered prompt directly, same reasoning as node._build_interviewer_messages
    (see build_interviewer_golden_sets.py)."""
    is_final_turn = turn_index >= MAX_BASELINE_TURNS - 1
    force_evaluation = turn_index >= MAX_BASELINE_TURNS
    situation = (
        "Current interviewer turn: "
        + str(turn_index)
        + "\nMaximum interviewer turns before forced evaluation: "
        + str(MAX_BASELINE_TURNS)
        + "\nFinal turn before forced evaluation: "
        + ("yes" if is_final_turn else "no")
        + "\nTurn budget exhausted, must evaluate now: "
        + ("yes" if force_evaluation else "no")
        + "\n\nPublic transcript:\n"
        + ("\n".join(transcript) if transcript else "No previous messages.")
        + "\n\nCase prompt:\n"
        + (case_prompt or "None.")
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
        + "\n\nWhen action is \"evaluate\", case_performance must contain exactly these fields: "
        + ", ".join(CASE_PERFORMANCE_FIELDS)
        + ". quality_dialog must contain exactly these fields: "
        + ", ".join(QUALITY_DIALOG_FIELDS)
        + ". Each field in both objects must be an object {\"score\": 1-4 or \"not_tested\", \"rationale\": \"short text\"}."
        + "\n\nAvailable support sources:\n"
        + "- Consulting Case Interview Guide -- "
        + CASE_GUIDE_SOURCE_DESCRIPTION
        + "\n- Profitability methodology textbook -- "
        + PROFITABILITY_SOURCE_NAVIGATION_GUIDE
        + "\n\nDecide, as part of this same response, whether an excerpt from either source would "
        + "help you right now. Write one short, specific question for whichever source(s) you need in "
        + "case_guide_query / profitability_query; leave a field empty if you don't need that source. "
        + "You have no separate turn to consult them: a query you write now can only be retrieved and "
        + "shown to you on your NEXT turn, not this one, so do not treat it as already available while "
        + "producing this response."
    )
    return [
        SystemMessage(
            content=(
                BASELINE_GRAPH_SYSTEM_PROMPT
                + "\n\n"
                + situation
                + f"\n\nExcerpts from {PROFITABILITY_CITATION_LABEL}:\n"
                + format_profitability_guide_context(profitability_context)
                + f"\n\nExcerpts from the {CASE_GUIDE_CITATION_LABEL}:\n"
                + format_case_guide_snippets(case_guide_context)
            )
        ),
    ]


def baseline_node(state: BaselineState) -> BaselineState:
    case_prompt = state.get("case_prompt", "")
    case_data = state.get("case_data", {})
    case_guidance = state.get("case_guidance", "")
    case_recommendation = state.get("case_recommendation", "")
    rubric_data = state.get("rubric_data", {})

    transcript = list(state.get("transcript", []))
    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []

    if not transcript:
        opening = case_prompt or "Walk me through your approach."
        return {
            "turn_index": 1,
            "transcript": transcript + [f"Interviewer: {opening}"],
            "enough_evidence": False,
            "case_performance": None,
            "quality_dialog": None,
        }

    turn_index = int(state.get("turn_index", 0))
    force_evaluation = turn_index >= MAX_BASELINE_TURNS

    case_guide_context, case_guide_log = get_pending_case_guide_context(state)
    profitability_context, profitability_log = get_pending_profitability_guide_context(state, top_k=3)
    messages = _build_baseline_messages(
        case_prompt,
        case_data,
        case_guidance,
        case_recommendation,
        rubric_data,
        transcript,
        visible_blocks,
        turn_index,
        case_guide_context,
        profitability_context,
    )

    move, move_usage_log = _invoke_baseline_move(messages, force_evaluation=force_evaluation)
    action = move["action"]
    content = move["content"]
    revealed_block_id = move["block_id"]
    ready_for_evaluation = move["ready_for_evaluation"]
    reasoning = move["reasoning"]
    next_case_guide_query = move["case_guide_query"]
    next_profitability_query = move["profitability_query"]

    action, content = resolve_reveal_content(case_data, action, revealed_block_id, content)

    if not ready_for_evaluation:
        transcript_label = "Interviewer reveal" if action == "reveal" else "Interviewer"
        return {
            "turn_index": turn_index + 1,
            "transcript": transcript + [f"{transcript_label}: {content}"],
            "enough_evidence": False,
            "interviewer_reasoning": reasoning,
            "case_performance": None,
            "quality_dialog": None,
            "pending_case_guide_query": next_case_guide_query,
            "pending_profitability_query": next_profitability_query,
            "retrieved_profitability_context": [
                format_profitability_guide_snippet(chunk)
                for chunk in profitability_context
                if str(chunk.get("content", "")).strip()
            ],
            "rag_query_log": [entry for entry in (case_guide_log, profitability_log) if entry],
            "llm_usage": move_usage_log,
        }

    return {
        "turn_index": turn_index,
        "transcript": transcript
        + [
            "Eval Case Performance: structured case-performance assessment completed.",
            "Eval Dialog Quality: structured interaction-quality assessment completed.",
            f"Give Feedback: {move['feedback']}",
        ],
        "enough_evidence": True,
        "interviewer_reasoning": reasoning,
        "case_performance": move["case_performance"],
        "quality_dialog": move["quality_dialog"],
        "retrieved_profitability_context": [
            format_profitability_guide_snippet(chunk)
            for chunk in profitability_context
            if str(chunk.get("content", "")).strip()
        ],
        "rag_query_log": [entry for entry in (case_guide_log, profitability_log) if entry],
        "llm_usage": move_usage_log,
    }


def route_after_baseline(
    state: BaselineState,
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


builder = StateGraph(BaselineState, config_schema=GraphConfig)
builder.add_node("load_scenario", load_scenario_node)
builder.add_node("baseline", make_trace_node("baseline", "baseline", "interviewer", baseline_node))
builder.add_node("candidate", make_trace_node("baseline", "candidate", "candidate", candidate_node))
builder.add_node("persist_run", make_persist_run_node("baseline"))

builder.add_edge(START, "load_scenario")
builder.add_edge("load_scenario", "baseline")
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
