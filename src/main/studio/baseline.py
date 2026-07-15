from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
)
from rag.case_guide_context import (
    format_case_guide_snippets,
    get_baseline_case_guide_context,
)
from rag.profitability_guide_context import (
    PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
    format_profitability_guide_context,
    retrieve_profitability_guide_context,
)
from loader import load_selected_simulation_bundle
from llm_server import judge_llm_server
from persistence import make_persist_run_node, make_trace_node, resolve_thread_id
from prompts import (
    BASELINE_GRAPH_SYSTEM_PROMPT,
    CANDIDATE_SYSTEM_PROMPT,
)
from state import AgenticGraphState, BaselineTurnOutput, ProfitabilityRagScoutingDecision
from utils import (
    extract_case_guidance,
    extract_case_prompt,
    extract_case_recommendation,
    extract_token_usage,
    format_candidate_persona,
    format_case_blocks,
    format_full_case_data,
    format_rubric,
    invoke_json_llm,
    load_json_object,
    normalize_eval_payload,
    normalize_string_list,
    strip_thinking,
)

# Baseline uses a single model (Llama-3.1-70B via OpenRouter) across all roles, unlike
# the role-differentiated agentic graph.
candidate_llm = judge_llm_server
judge_llm = judge_llm_server
interviewer_llm = judge_llm_server

DEFAULT_THREAD_ID = "main_baseline"
MAX_BASELINE_TURNS = 4
MAX_BASELINE_JSON_RETRIES = 3

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


def _candidate_transcript_messages(visible_transcript: list[str]) -> list:
    """Replay the visible transcript as real conversation turns so the candidate
    sees its own prior answers as assistant turns instead of as text described
    inside the system prompt.
    """
    messages: list = []
    for line in visible_transcript:
        if line.startswith("Candidate:"):
            messages.append(AIMessage(content=line[len("Candidate:"):].strip()))
        elif line.startswith("Interviewer reveal:"):
            messages.append(HumanMessage(content="[revealed fact] " + line[len("Interviewer reveal:"):].strip()))
        else:
            messages.append(HumanMessage(content=line[len("Interviewer:"):].strip()))
    return messages


def get_profitability_guide_context(
    state: AgenticGraphState,
    *,
    evaluation_target: str,
    top_k: int,
    base_prompt: str,
    situation: str,
) -> tuple[list[dict], dict, list[dict]]:
    """Let this step decide -- with its own prompt and its own (single) model --
    whether it needs an excerpt from the profitability textbook right now, and
    what to ask it. Mirrors node.py's eval_case_performance_node scouting, but
    as a standalone helper since baseline's case_guide retrieval stays the
    deliberately simple comparison arm (see get_baseline_case_guide_context).

    Returns (chunks, rag_query_log_entry, scouting_usage_log).
    """
    scouting_messages = [
        SystemMessage(
            content=(
                base_prompt
                + "\n\n"
                + situation
                + "\n\nAvailable support source -- Profitability methodology textbook: "
                + PROFITABILITY_SOURCE_NAVIGATION_GUIDE
                + "\n\nBefore continuing, decide whether an excerpt from this textbook would help "
                + "you right now. If yes, write one short, specific question for it. If not, leave "
                + "profitability_query empty."
            )
        )
    ]
    payload, usage_log = invoke_json_llm(
        judge_llm,
        scouting_messages,
        node=f"{evaluation_target}_profitability_scout",
        schema=ProfitabilityRagScoutingDecision,
    )
    query = str(payload.get("profitability_query", "")).strip()
    if not query:
        return [], {}, usage_log

    chunks = retrieve_profitability_guide_context(query, top_k=top_k)
    log_entry = {
        "node": evaluation_target,
        "source": "profitability_guide",
        "query": query,
        "top_k": top_k,
        "chunk_ids": [chunk.get("chunk_id") for chunk in chunks],
    }
    return chunks, log_entry, usage_log


def build_initial_baseline_state(
    case_name: str | None = None,
    seed: int | None = None,
    scenario_ref: str | None = None,
) -> AgenticGraphState:
    selected_ref = scenario_ref or case_name
    bundle = load_selected_simulation_bundle(scenario_ref=selected_ref, seed=seed)
    scenario = bundle["scenario"]
    case_data = bundle["case"]

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
        "case_performance": None,
        "quality_dialog": None,
        "data_gathered": [],
        "thread_id": DEFAULT_THREAD_ID,
        "rubric_data": bundle["rubric"],
        "judge_round": 0,
        "retrieved_profitability_context": [],
        "rag_query_log": [],
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

    return {
        "thread_id": thread_id,
        "scenario_ref": str(state.get("scenario_ref") or scenario.get("scenario_id", "")),
        "case_prompt": extract_case_prompt(case_data),
        "candidate_profile": scenario.get("candidate_profile", {}),
        "case_guidance": extract_case_guidance(case_data),
        "case_data": case_data,
        "case_recommendation": extract_case_recommendation(case_data),
        "rubric_data": bundle["rubric"],
        "retrieved_profitability_context": [],
        "rag_query_log": [],
    }


def parse_baseline_output(payload: dict, *, require_evaluate: bool = False) -> dict | None:
    """Parse the baseline's single unified per-turn payload.

    Unlike the agentic graph, baseline gets no separate judge/eval/feedback
    turns: this same schema is used on every call, and when action is
    "evaluate" it must also carry the full case_performance/quality_dialog/
    feedback content in that one response. `require_evaluate` is set once the
    turn budget is exhausted, so a model that ignores the instruction to
    evaluate now is treated as an invalid reply and retried rather than
    silently continuing the interview past its turn budget.
    """
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
            "ready_for_evaluation": False,
        }

    payload, usage_log = invoke_json_llm(
        interviewer_llm,
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


def candidate_node(state: AgenticGraphState) -> AgenticGraphState:
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
        *_candidate_transcript_messages(visible_transcript),
        HumanMessage(
            content=(
                "Current factual data_gathered list:\n"
                + ("\n".join(data_gathered) if data_gathered else "None yet.")
                + "\n\nUpdate data_gathered so it contains the factual case information you have learned so far."
            )
        ),
    ]

    response = candidate_llm.invoke(messages)
    usage_entry = extract_token_usage(response, node="baseline_candidate", model=candidate_llm.model_name)
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


def baseline_node(state: AgenticGraphState) -> AgenticGraphState:
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
    is_final_turn = turn_index >= MAX_BASELINE_TURNS - 1
    force_evaluation = turn_index >= MAX_BASELINE_TURNS

    case_guide_context, case_guide_log = get_baseline_case_guide_context(state)
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
    )
    profitability_context, profitability_log, profitability_rag_usage = get_profitability_guide_context(
        state,
        evaluation_target="baseline",
        top_k=3,
        base_prompt=BASELINE_GRAPH_SYSTEM_PROMPT,
        situation=situation,
    )
    messages = [
        SystemMessage(
            content=(
                BASELINE_GRAPH_SYSTEM_PROMPT
                + "\n\n"
                + situation
                + "\n\nRetrieved profitability methodology context:\n"
                + format_profitability_guide_context(profitability_context)
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
            )
        ),
    ]

    move, move_usage_log = _invoke_baseline_move(messages, force_evaluation=force_evaluation)
    action = move["action"]
    content = move["content"]
    revealed_block_id = move["block_id"]
    ready_for_evaluation = move["ready_for_evaluation"]
    reasoning = move["reasoning"]

    if action == "reveal" and revealed_block_id:
        revealed_block = get_case_block_by_id(case_data, revealed_block_id)
        if isinstance(revealed_block, dict) and revealed_block.get("visible_to_candidate") is True:
            revealed_content = str(revealed_block.get("content", "")).strip()
            if revealed_content:
                content = revealed_content
        else:
            action = "question"

    if not ready_for_evaluation:
        transcript_label = "Interviewer reveal" if action == "reveal" else "Interviewer"
        return {
            "turn_index": turn_index + 1,
            "transcript": transcript + [f"{transcript_label}: {content}"],
            "enough_evidence": False,
            "interviewer_reasoning": reasoning,
            "case_performance": None,
            "quality_dialog": None,
            "retrieved_profitability_context": [
                str(chunk.get("content", "")).strip()
                for chunk in profitability_context
                if str(chunk.get("content", "")).strip()
            ],
            "rag_query_log": [entry for entry in (case_guide_log, profitability_log) if entry],
            "llm_usage": profitability_rag_usage + move_usage_log,
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
            str(chunk.get("content", "")).strip()
            for chunk in profitability_context
            if str(chunk.get("content", "")).strip()
        ],
        "rag_query_log": [entry for entry in (case_guide_log, profitability_log) if entry],
        "llm_usage": profitability_rag_usage + move_usage_log,
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
