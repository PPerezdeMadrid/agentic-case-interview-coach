import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from adapter import (
    get_candidate_visible_blocks,
    get_case_block_by_id,
)
from loader import (
    DEFAULT_MAX_JUDGE_ROUNDS,
    load_selected_simulation_bundle,
)
from llm_server import (
    candidate_llm_server,
    feedback_llm_server,
    interviewer_llm_server,
    judge_llm_server,
    lmstudio_llm_server,
    openai_llm_server,
)
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
    CASE_GUIDE_SOURCE_DESCRIPTION,
    format_case_guide_snippets,
    retrieve_case_guide_context,
)
from rag.profitability_guide_context import (
    PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
    format_profitability_guide_context,
    retrieve_profitability_guide_context,
)
from state import (
    AgenticGraphState,
    CandidateResponse,
    CaseAndProfitabilityRagScoutingDecision,
    CaseEvaluation,
    CaseGuideRagScoutingDecision,
    DialogEvaluation,
    InterviewerMove,
    JudgeResponse,
)
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
    normalize_string_list,
    normalize_eval_payload,
    normalize_focus_areas,
    parse_interviewer_output,
    strip_thinking,
)

# Per-role servers: interviewer/candidate/judge on OpenRouter, feedback on local LM Studio.
candidate_llm = feedback_llm_server
judge_llm = judge_llm_server
interviewer_llm = feedback_llm_server
feedback_llm = feedback_llm_server

MAX_JUDGE_ROUNDS = DEFAULT_MAX_JUDGE_ROUNDS
MAX_INTERVIEWER_TURNS_BEFORE_JUDGE = 4
DEFAULT_THREAD_ID = "main_default"
MAX_INTERVIEWER_JSON_RETRIES = 3

# Field names are derived from the schemas in state.py so the prompt text,
# response_format hint, and normalize_eval_payload all stay in sync.
CASE_PERFORMANCE_FIELDS = list(CaseEvaluation.model_fields.keys())
QUALITY_DIALOG_FIELDS = list(DialogEvaluation.model_fields.keys())


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


def format_focus_areas_for_prompt(focus_areas: list[str]) -> str:
    """Format judge focus areas as direct interviewer instructions."""
    normalized_focus_areas = normalize_string_list(focus_areas)
    if not normalized_focus_areas:
        return "None."
    return "\n".join(f"- {focus_area}" for focus_area in normalized_focus_areas)


def _scout_case_guide(
    llm,
    *,
    base_prompt: str,
    situation: str,
    decision_instruction: str,
    node_name: str,
    top_k: int = 4,
) -> tuple[list[str], dict, list[dict]]:
    """Let a node decide -- with its own prompt/persona and its own LLM -- whether
    it needs an excerpt from the Consulting Case Interview Guide right now, and
    what to ask it. This is not a shared "RAG node": every call site supplies its
    own base_prompt/situation/decision_instruction, so the decision is made in
    that node's own voice. Returns ([], {}, usage_log) when the node decides it
    doesn't need the guide this round.
    """
    scouting_messages = [
        SystemMessage(
            content=(
                base_prompt
                + "\n\n"
                + situation
                + "\n\nAvailable support source -- "
                + CASE_GUIDE_SOURCE_DESCRIPTION
                + "\n\n"
                + decision_instruction
            )
        )
    ]
    payload, usage_log = invoke_json_llm(
        llm, scouting_messages, node=f"{node_name}_case_guide_scout", schema=CaseGuideRagScoutingDecision
    )
    query = str(payload.get("case_guide_query", "")).strip()
    if not query:
        return [], {}, usage_log

    chunks = retrieve_case_guide_context(query, top_k=top_k)
    snippets = [str(chunk.get("content", "")).strip() for chunk in chunks if str(chunk.get("content", "")).strip()]
    log_entry = {
        "node": node_name,
        "source": "case_guide",
        "query": query,
        "top_k": top_k,
        "chunk_ids": [chunk.get("chunk_id") for chunk in chunks],
    }
    return snippets, log_entry, usage_log


def _build_interviewer_messages(
    case_prompt: str,
    transcript: list[str],
    visible_blocks: list[dict],
    case_guidance: str,
    focus_areas: list[str],
    turn_index: int,
) -> list[SystemMessage]:
    is_final_turn = turn_index >= MAX_INTERVIEWER_TURNS_BEFORE_JUDGE - 1
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
                + f"\n\nCurrent turn index: {turn_index} (final turn before judge evaluation: "
                + ("yes" if is_final_turn else "no")
                + ")"
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
    turn_index: int,
) -> tuple[str, str, str, bool, str, list[dict]]:
    messages = _build_interviewer_messages(
        case_prompt,
        transcript,
        visible_blocks,
        case_guidance,
        focus_areas,
        turn_index,
    )
    print("Calling Interviewer Server...")
    payload, usage_log = invoke_json_llm(
        interviewer_llm,
        messages,
        node="interviewer",
        schema=InterviewerMove,
        accept=lambda candidate: parse_interviewer_output(candidate) is not None,
        retries=MAX_INTERVIEWER_JSON_RETRIES,
    )
    parsed = parse_interviewer_output(payload)
    if parsed is not None:
        return (*parsed, usage_log)

    return (
        "question",
        "I need one concrete next step from you. Which area would you like to analyze first: revenue or costs?",
        "",
        False,
        "",
        usage_log,
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
        "case_performance": None,
        "quality_dialog": None,
        "data_gathered": [],
        "thread_id": DEFAULT_THREAD_ID,
        "trace_step_index": 0,
        "rubric_data": bundle["rubric"],
        "judge_round": 0,
        "retrieved_profitability_context": [],
        "rag_query_log": [],
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
        "rag_query_log": [],
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

    if turn_index >= MAX_INTERVIEWER_TURNS_BEFORE_JUDGE:
        # The candidate just answered the final-recommendation ask issued on the
        # previous turn. Hand off to the judge without another interviewer
        # message so the candidate's recommendation stays the last word before
        # evaluation, instead of a dangling interviewer question.
        return {"enough_evidence": True}

    visible_blocks = get_candidate_visible_blocks(case_data) if isinstance(case_data, dict) else []

    interviewer_action, content, revealed_block_id, ready_for_judge, reasoning, usage_log = _invoke_interviewer_move(
        case_prompt,
        transcript,
        visible_blocks,
        case_guidance,
        focus_areas if isinstance(focus_areas, list) else [],
        turn_index,
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

    return {
        "enough_evidence": ready_for_judge,
        "turn_index": turn_index + 1,
        "transcript": transcript,
        "interviewer_reasoning": reasoning,
        "llm_usage": usage_log,
    }


def candidate_node(state: AgenticGraphState) -> AgenticGraphState:
    """Generate the synthetic candidate reply and update known facts."""
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

    payload, usage_log = invoke_json_llm(
        candidate_llm,
        messages,
        node="candidate",
        schema=CandidateResponse,
        accept=lambda candidate: bool(str(candidate.get("answer", "")).strip()),
        # The model's raw prose is still a perfectly usable candidate answer
        # even when it skips the JSON envelope, so treat it as one rather
        # than spending retries or losing the reply to a canned fallback.
        on_exhausted=lambda raw_text: {"answer": strip_thinking(raw_text)},
        retries=1,
    )
    answer = str(payload.get("answer", "")).strip()
    reasoning = str(payload.get("reasoning", "")).strip()
    updated_data_gathered = normalize_string_list(payload.get("data_gathered", data_gathered))

    transcript = transcript + [f"Candidate: {answer}"]

    return {
        "transcript": transcript,
        "data_gathered": updated_data_gathered,
        "candidate_reasoning": reasoning,
        "llm_usage": usage_log,
    }


def judge_node(state: AgenticGraphState) -> AgenticGraphState:
    """Decide whether there is enough evidence to evaluate the candidate."""
    judge_round = state.get("judge_round", 0)
    transcript = state.get("transcript", [])
    rubric_data = state.get("rubric_data", {})

    situation = (
        f"Judge round: {judge_round + 1}\n"
        f"Maximum judge rounds before forcing evaluation: {MAX_JUDGE_ROUNDS}\n\n"
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
    )

    case_guide_context, case_guide_log, scout_usage_log = _scout_case_guide(
        judge_llm,
        base_prompt=JUDGE_GRAPH_SYSTEM_PROMPT,
        situation=situation,
        decision_instruction=(
            "Before deciding whether there is enough evidence, decide whether reading an excerpt "
            "from the guide above would sharpen your judgment right now. If yes, write one short, "
            "specific question for it. If you don't need it this round, leave case_guide_query empty."
        ),
        node_name="judge",
    )

    messages = [
        SystemMessage(
            content=(
                JUDGE_GRAPH_SYSTEM_PROMPT
                + "\n\n"
                + situation
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
            )
        ),
    ]
    payload, usage_log = invoke_json_llm(judge_llm, messages, node="judge", schema=JudgeResponse)

    enough_evidence = bool(payload.get("enough_evidence", False))
    new_focus_areas = normalize_focus_areas(payload.get("focus_areas", []))

    if judge_round + 1 >= MAX_JUDGE_ROUNDS and not enough_evidence:
        enough_evidence = True
        new_focus_areas = []

    update = {
        "judge_round": judge_round + 1,
        "enough_evidence": enough_evidence,
        "focus_areas": None if enough_evidence else new_focus_areas,
        "rag_query_log": [case_guide_log] if case_guide_log else [],
        "llm_usage": scout_usage_log + usage_log,
    }
    if not enough_evidence:
        # Reset the interviewer-turn budget so judge coaching leads to another
        # interviewer -> candidate exchange instead of an immediate bounce back.
        update["turn_index"] = 0
    return update


def eval_case_performance_node(state: AgenticGraphState) -> AgenticGraphState:
    """Score case-performance dimensions using transcript and rubric evidence."""
    rubric_data = state.get("rubric_data", {})

    situation = (
        "Transcript:\n"
        + "\n".join(state.get("transcript", []))
        + "\n\nCase guidance:\n"
        + str(state.get("case_guidance", "None."))
        + "\n\nCase data:\n"
        + format_full_case_data(state.get("case_data", {}))
        + "\n\nExpected recommendation:\n"
        + str(state.get("case_recommendation", "None."))
        + "\n\nRubric:\n"
        + format_rubric(rubric_data if isinstance(rubric_data, dict) else {}, CASE_PERFORMANCE_FIELDS)
    )

    # This node can draw on two sources, so it scouts both in one decision rather
    # than through the single-source _scout_case_guide helper.
    scouting_messages = [
        SystemMessage(
            content=(
                CASE_EVAL_SYSTEM_PROMPT
                + "\n\n"
                + situation
                + "\n\nAvailable support sources:\n"
                + "- Consulting Case Interview Guide -- "
                + CASE_GUIDE_SOURCE_DESCRIPTION
                + "\n- Profitability methodology textbook -- "
                + PROFITABILITY_SOURCE_NAVIGATION_GUIDE
                + "\n\nBefore scoring, decide whether an excerpt from either source would help you "
                + "score accurately. Write one short, specific question for whichever source(s) you "
                + "need; leave a field empty if you don't need that source."
            )
        )
    ]
    scouting_payload, scouting_usage_log = invoke_json_llm(
        judge_llm,
        scouting_messages,
        node="eval_case_performance_scout",
        schema=CaseAndProfitabilityRagScoutingDecision,
    )

    case_guide_query = str(scouting_payload.get("case_guide_query", "")).strip()
    case_guide_context: list[str] = []
    case_guide_log: dict = {}
    if case_guide_query:
        case_guide_chunks = retrieve_case_guide_context(case_guide_query, top_k=4)
        case_guide_context = [
            str(chunk.get("content", "")).strip()
            for chunk in case_guide_chunks
            if str(chunk.get("content", "")).strip()
        ]
        case_guide_log = {
            "node": "eval_case_performance",
            "source": "case_guide",
            "query": case_guide_query,
            "top_k": 4,
            "chunk_ids": [chunk.get("chunk_id") for chunk in case_guide_chunks],
        }

    profitability_query = str(scouting_payload.get("profitability_query", "")).strip()
    profitability_context: list[dict] = []
    profitability_log: dict = {}
    if profitability_query:
        profitability_context = retrieve_profitability_guide_context(profitability_query, top_k=5)
        profitability_log = {
            "node": "case_performance",
            "source": "profitability_guide",
            "query": profitability_query,
            "top_k": 5,
            "chunk_ids": [chunk.get("chunk_id") for chunk in profitability_context],
        }

    messages = [
        SystemMessage(
            content=(
                CASE_EVAL_SYSTEM_PROMPT
                + "\n\nReturn a JSON object with these fields: "
                + ", ".join(CASE_PERFORMANCE_FIELDS)
                + ". Each field must be an object {\"score\": 1-4 or \"not_tested\", \"rationale\": \"short text\"}."
                + "\n\n"
                + situation
                + "\n\nRetrieved profitability methodology context:\n"
                + format_profitability_guide_context(profitability_context)
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
            )
        ),
    ]
    payload, usage_log = invoke_json_llm(
        judge_llm, messages, node="eval_case_performance", schema=CaseEvaluation
    )
    case_performance = normalize_eval_payload(payload, CASE_PERFORMANCE_FIELDS)

    return {
        "case_performance": case_performance,
        "retrieved_profitability_context": [
            str(chunk.get("content", "")).strip()
            for chunk in profitability_context
            if str(chunk.get("content", "")).strip()
        ],
        "rag_query_log": [entry for entry in (case_guide_log, profitability_log) if entry],
        "llm_usage": scouting_usage_log + usage_log,
    }


def eval_dialog_quality_node(state: AgenticGraphState) -> AgenticGraphState:
    """Score interaction-quality dimensions from the transcript."""
    rubric_data = state.get("rubric_data", {})
    situation = (
        "Transcript:\n"
        + "\n".join(state.get("transcript", []))
        + "\n\nRubric:\n"
        + format_rubric(rubric_data if isinstance(rubric_data, dict) else {}, QUALITY_DIALOG_FIELDS)
    )
    case_guide_context, case_guide_log, scout_usage_log = _scout_case_guide(
        judge_llm,
        base_prompt=DIALOG_EVAL_SYSTEM_PROMPT,
        situation=situation,
        decision_instruction=(
            "Before scoring, decide whether reading an excerpt from the guide above would help you "
            "judge communication and interaction quality accurately. If yes, write one short, "
            "specific question for it. If not, leave case_guide_query empty."
        ),
        node_name="eval_dialog_quality",
    )
    messages = [
        SystemMessage(
            content=(
                DIALOG_EVAL_SYSTEM_PROMPT
                + "\n\nReturn a JSON object with these fields: "
                + ", ".join(QUALITY_DIALOG_FIELDS)
                + ". Each field must be an object {\"score\": 1-4 or \"not_tested\", \"rationale\": \"short text\"}."
                + "\n\n"
                + situation
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
            )
        ),
    ]
    payload, usage_log = invoke_json_llm(
        judge_llm, messages, node="eval_dialog_quality", schema=DialogEvaluation
    )
    quality_dialog = normalize_eval_payload(payload, QUALITY_DIALOG_FIELDS)
    return {
        "quality_dialog": quality_dialog,
        "rag_query_log": [case_guide_log] if case_guide_log else [],
        "llm_usage": scout_usage_log + usage_log,
    }


def give_feedback_node(state: AgenticGraphState) -> AgenticGraphState:
    """Write final user-facing feedback from the evaluation outputs."""
    situation = (
        "Transcript:\n"
        + "\n".join(state.get("transcript", []))
        + "\n\nCase performance:\n"
        + json.dumps(state.get("case_performance", {}), ensure_ascii=True, indent=2)
        + "\n\nDialog quality:\n"
        + json.dumps(state.get("quality_dialog", {}), ensure_ascii=True, indent=2)
    )
    case_guide_context, case_guide_log, scout_usage_log = _scout_case_guide(
        feedback_llm,
        base_prompt=FEEDBACK_SYSTEM_PROMPT,
        situation=situation,
        decision_instruction=(
            "Before writing feedback, decide whether an excerpt from the guide above would sharpen "
            "your coaching. If yes, write one short, specific question for it. If not, leave "
            "case_guide_query empty."
        ),
        node_name="give_feedback",
    )
    messages = [
        SystemMessage(
            content=(
                FEEDBACK_SYSTEM_PROMPT
                + "\n\n"
                + situation
                + "\n\nGuide navigation rules:\n"
                + CASE_GUIDE_NAVIGATION_PROMPT
                + "\n\nConsulting Case Interview Guide excerpts:\n"
                + format_case_guide_snippets(case_guide_context)
            )
        ),
    ]
    response = feedback_llm.invoke(messages)
    usage_entry = extract_token_usage(response, node="give_feedback", model=feedback_llm.model_name)
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
        "rag_query_log": [case_guide_log] if case_guide_log else [],
        "llm_usage": scout_usage_log + [usage_entry],
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
    "candidate_llm",
    "candidate_node",
    "eval_case_performance_node",
    "eval_dialog_quality_node",
    "feedback_llm",
    "format_focus_areas_for_prompt",
    "get_candidate_visible_transcript",
    "give_feedback_node",
    "interviewer_llm",
    "interviewer_node",
    "judge_llm",
    "judge_node",
    "load_scenario_node",
    "openai_llm_server",
    "route_after_interviewer",
    "route_after_judge_agentic_02",
]
