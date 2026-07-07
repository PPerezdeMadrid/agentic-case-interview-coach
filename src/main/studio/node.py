import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
)
from loader import (
    DEFAULT_MAX_JUDGE_ROUNDS,
    load_selected_simulation_bundle,
)
from llm_server import openai_llm_server, lmstudio_llm_server
from persistence import resolve_thread_id
from prompts import (
    CASE_GUIDE_NAVIGATION_PROMPT,
    CANDIDATE_SYSTEM_PROMPT,
    CASE_EVAL_SYSTEM_PROMPT,
    DIALOG_EVAL_SYSTEM_PROMPT,
    FEEDBACK_SYSTEM_PROMPT,
    INTERVIEWER_GRAPH_SYSTEM_PROMPT,
    JUDGE_GRAPH_SYSTEM_PROMPT,
)
from rag.case_guide_context import (
    build_case_guide_query,
    format_case_guide_snippets,
    resolve_case_guide_query,
    retrieve_case_guide_context,
)
from rag.profitability_guide_context import (
    build_profitability_retrieval_query,
    format_profitability_guide_context,
    retrieve_profitability_guide_context,
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
    normalize_string_list,
    normalize_eval_payload,
    normalize_focus_areas,
    parse_interviewer_output,
    strip_thinking,
)

# Shared default server for the graph today.
llm_server = lmstudio_llm_server

MAX_JUDGE_ROUNDS = DEFAULT_MAX_JUDGE_ROUNDS
MAX_INTERVIEWER_TURNS_BEFORE_JUDGE = 4
DEFAULT_THREAD_ID = "main_default"
MAX_INTERVIEWER_JSON_RETRIES = 3

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


def format_focus_areas_for_prompt(focus_areas: list[str]) -> str:
    """Format judge focus areas as direct interviewer instructions."""
    normalized_focus_areas = normalize_string_list(focus_areas)
    if not normalized_focus_areas:
        return "None."
    return "\n".join(f"- {focus_area}" for focus_area in normalized_focus_areas)


def get_case_guide_context(state: AgenticGraphState, node_name: str, *, top_k: int = 4) -> list[str]:
    """Retrieve guide snippets tailored to a specific evaluation node."""
    case_prompt = resolve_case_guide_query(state)
    query = build_case_guide_query(state, case_prompt, node_name)
    if not query.strip():
        return []

    case_guide_chunks = retrieve_case_guide_context(query, top_k=top_k)
    return [
        str(chunk.get("content", "")).strip()
        for chunk in case_guide_chunks
        if str(chunk.get("content", "")).strip()
    ]


def get_profitability_guide_context(
    state: AgenticGraphState,
    *,
    evaluation_target: str,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve profitability-guide snippets tailored to the current situation."""
    query = build_profitability_retrieval_query(
        str(state.get("case_prompt", "")),
        state.get("transcript", []),
        evaluation_target=evaluation_target,
        focus_areas=state.get("focus_areas", []),
    )
    if not query.strip():
        return []
    return retrieve_profitability_guide_context(query, top_k=top_k)


def _build_interviewer_messages(
    case_prompt: str,
    transcript: list[str],
    visible_blocks: list[dict],
    case_guidance: str,
    focus_areas: list[str],
) -> list[SystemMessage]:
    return [
        SystemMessage(
            content=(
                INTERVIEWER_GRAPH_SYSTEM_PROMPT
                + "\n\nCase prompt:\n"
                + (case_prompt or "None.")
                + "\n\nPublic transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nCandidate-visible case blocks:\n"
                + format_case_blocks(visible_blocks)
                + "\n\nHidden case guidance:\n"
                + (case_guidance or "None.")
                + "\n\nCurrent judge focus areas to act on directly:\n"
                + format_focus_areas_for_prompt(focus_areas if isinstance(focus_areas, list) else [])
                + "\n\nDecide the best next interviewer move."
            )
        ),
    ]


def _invoke_interviewer_move(
    case_prompt: str,
    transcript: list[str],
    visible_blocks: list[dict],
    case_guidance: str,
    focus_areas: list[str],
) -> tuple[str, str, str, bool]:
    messages = _build_interviewer_messages(
        case_prompt,
        transcript,
        visible_blocks,
        case_guidance,
        focus_areas,
    )
    response = openai_llm_server.invoke(messages)
    print("Calling OpenAI Server...")
    parsed = parse_interviewer_output(response.content)
    if parsed is not None:
        return parsed

    raw_output = str(response.content).strip()
    for _ in range(MAX_INTERVIEWER_JSON_RETRIES - 1):
        repair_messages = messages + [
            HumanMessage(
                content=(
                    "Your previous reply was invalid for the required schema.\n"
                    "Return exactly one valid JSON object with keys action, content, block_id, ready_for_judge.\n"
                    "Do not add markdown, code fences, analysis, or any extra text.\n\n"
                    f"Previous invalid reply:\n{raw_output or '[empty response]'}"
                )
            )
        ]
        response = openai_llm_server.invoke(repair_messages)
        print("Calling OpenAI Server...")
        raw_output = str(response.content).strip()
        parsed = parse_interviewer_output(raw_output)
        if parsed is not None:
            return parsed

    return (
        "question",
        "I need one concrete next step from you. Which area would you like to analyze first: revenue or costs?",
        "",
        False,
    )


def build_initial_interview_state(
    case_name: str | None = None,
    seed: int | None = None,
    scenario_ref: str | None = None,
) -> AgenticGraphState:
    """Build the initial runtime state for the agentic interview graph."""
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
        "case_performance": {},
        "quality_dialog": {},
        "data_gathered": [],
        "thread_id": DEFAULT_THREAD_ID,
        "trace_step_index": 0,
        "rubric_data": bundle["rubric"],
        "judge_round": 0,
        "retrieved_profitability_context": [],
    }


def load_scenario_node(
    state: AgenticGraphState,
    config: RunnableConfig | None = None,
) -> AgenticGraphState:
    """Load scenario assets into state if they are not present yet."""
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
    }


def interviewer_node(state: AgenticGraphState) -> AgenticGraphState:
    """Generate the next interviewer move and update the transcript."""
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    case_prompt = state.get("case_prompt", "")
    case_data = state.get("case_data", {})
    case_guidance = state.get("case_guidance", "")
    focus_areas = state.get("focus_areas", [])

    if turn_index == 0 and not transcript:
        content = case_prompt or "Walk me through your approach."
        transcript = transcript + [f"Interviewer: {content}"]
        return {
            "enough_evidence": False,
            "turn_index": turn_index + 1,
            "transcript": transcript,
        }

    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []

    interviewer_action, content, revealed_block_id, ready_for_judge = _invoke_interviewer_move(
        case_prompt,
        transcript,
        visible_blocks,
        case_guidance,
        focus_areas if isinstance(focus_areas, list) else [],
    )

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

    next_turn_index = turn_index + 1
    return {
        "enough_evidence": ready_for_judge or next_turn_index >= MAX_INTERVIEWER_TURNS_BEFORE_JUDGE,
        "turn_index": next_turn_index,
        "transcript": transcript,
    }


def candidate_node(state: AgenticGraphState) -> AgenticGraphState:
    """Generate the synthetic candidate reply and update known facts."""
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
    """Decide whether there is enough evidence to evaluate the candidate."""
    judge_round = state.get("judge_round", 0)
    transcript = state.get("transcript", [])
    rubric_data = state.get("rubric_data", {})
    case_guide_context = get_case_guide_context(state, "judge")

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
                + "\n\nCase data:\n"
                + format_full_case_data(state.get("case_data", {}))
                + "\n\nExpected recommendation:\n"
                + str(state.get("case_recommendation", "None."))
                + "\n\nRubric:\n"
                + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
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

    update = {
        "judge_round": judge_round + 1,
        "enough_evidence": enough_evidence,
        "focus_areas": None if enough_evidence else new_focus_areas,
    }
    if not enough_evidence:
        # Reset the interviewer-turn budget so judge coaching leads to another
        # interviewer -> candidate exchange instead of an immediate bounce back.
        update["turn_index"] = 0
    return update


def eval_case_performance_node(state: AgenticGraphState) -> AgenticGraphState:
    """Score case-performance dimensions using transcript and rubric evidence."""
    rubric_data = state.get("rubric_data", {})
    case_guide_context = get_case_guide_context(state, "eval_case_performance")
    profitability_context = get_profitability_guide_context(
        state,
        evaluation_target="case_performance",
        top_k=5,
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
                + format_profitability_guide_context(profitability_context)
                + "\n\nCase data:\n"
                + format_full_case_data(state.get("case_data", {}))
                + "\n\nExpected recommendation:\n"
                + str(state.get("case_recommendation", "None."))
                + "\n\nRubric:\n"
                + format_rubric(rubric_data if isinstance(rubric_data, dict) else {})
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
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


def eval_dialog_quality_node(state: AgenticGraphState) -> AgenticGraphState:
    """Score interaction-quality dimensions from the transcript."""
    rubric_data = state.get("rubric_data", {})
    case_guide_context = get_case_guide_context(state, "eval_dialog_quality")
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
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
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
    """Write final user-facing feedback from the evaluation outputs."""
    case_guide_context = get_case_guide_context(state, "give_feedback")
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
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
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
    """Route to judge when enough evidence exists, otherwise continue."""
    if state.get("enough_evidence") is True:
        return "judge"
    return "candidate"


def route_after_judge_agentic_02(
    state: AgenticGraphState,
) -> Literal["interviewer"] | list[Literal["eval_case_performance", "eval_dialog_quality"]]:
    """Route from judge either back to interview or into evaluation."""
    if state.get("enough_evidence") is True:
        return ["eval_case_performance", "eval_dialog_quality"]
    return "interviewer"


__all__ = [
    "CASE_PERFORMANCE_FIELDS",
    "DEFAULT_THREAD_ID",
    "MAX_JUDGE_ROUNDS",
    "QUALITY_DIALOG_FIELDS",
    "build_initial_interview_state",
    "candidate_node",
    "eval_case_performance_node",
    "eval_dialog_quality_node",
    "format_focus_areas_for_prompt",
    "get_candidate_visible_transcript",
    "get_case_guide_context",
    "get_profitability_guide_context",
    "give_feedback_node",
    "interviewer_node",
    "judge_node",
    "llm_server",
    "load_scenario_node",
    "openai_llm_server",
    "resolve_case_guide_query",
    "route_after_interviewer",
    "route_after_judge_agentic_02",
]
