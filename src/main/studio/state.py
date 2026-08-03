from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict
from typing_extensions import NotRequired, TypedDict


def replace_focus_areas(existing: list[str], new_values: list[str] | None) -> list[str]:
    del existing
    if new_values is None:
        return []
    return list(new_values)


def append_rag_query_log(existing: list[dict], new_entries: list[dict] | None) -> list[dict]:
    """Concatenate so concurrent nodes (e.g. the two eval nodes fanning out from judge) don't clobber each other."""
    if not new_entries:
        return existing
    return existing + list(new_entries)


def append_llm_usage(existing: list[dict], new_entries: list[dict] | None) -> list[dict]:
    """Same concatenation pattern as append_rag_query_log, for token usage entries."""
    if not new_entries:
        return existing
    return existing + list(new_entries)


class BaseCaseState(TypedDict):
    """Fields both graphs read/write identically. Role-specific fields live on
    AgenticGraphState / BaselineState below, not here."""

    case_prompt: str
    candidate_profile: dict
    turn_index: int
    transcript: list[str]
    case_guidance: str
    case_data: dict
    enough_evidence: bool
    case_recommendation: str
    case_performance: dict | None
    quality_dialog: dict | None
    data_gathered: list[str]
    thread_id: NotRequired[str]
    run_id: NotRequired[str]
    trace_step_index: NotRequired[int]
    scenario_ref: NotRequired[str]
    rubric_data: NotRequired[dict]
    interviewer_reasoning: NotRequired[str]
    retrieved_profitability_context: NotRequired[list[str]]
    rag_query_log: NotRequired[Annotated[list[dict], append_rag_query_log]]
    llm_usage: NotRequired[Annotated[list[dict], append_llm_usage]]

    


class AgenticGraphState(BaseCaseState):
    """State for the role-differentiated graph (node.py): separate interviewer/candidate/judge/eval/feedback
    nodes, so the judge's evidence loop needs its own round counter and focus areas."""

    focus_areas: Annotated[list[str], replace_focus_areas]
    judge_round: NotRequired[int]
    total_turns_used: NotRequired[int]
    candidate_reasoning: NotRequired[str]


class BaselineState(BaseCaseState):
    """State for the single-call baseline graph (baseline.py): no separate scouting call, so a RAG
    query flagged this turn can only be resolved and shown back on the *next* turn -- hence pending_*."""

    pending_case_guide_query: NotRequired[str]
    pending_profitability_query: NotRequired[str]


class InterviewerMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str
    action: Literal["question", "reveal"]
    content: str
    block_id: str
    ready_for_judge: bool


class CandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    reasoning: str
    data_gathered: list[str]


class JudgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str
    enough_evidence: bool
    focus_areas: list[str]


class CaseGuideRagScoutingDecision(BaseModel):
    """A node's decision on whether it needs a Case Interview Guide excerpt. Empty string = no."""

    model_config = ConfigDict(extra="forbid")

    case_guide_query: str


class CaseAndProfitabilityRagScoutingDecision(BaseModel):
    """Same as CaseGuideRagScoutingDecision, plus the profitability methodology textbook."""

    model_config = ConfigDict(extra="forbid")

    case_guide_query: str
    profitability_query: str


class ScoreRationale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int | Literal["not_tested"]
    rationale: str


class CaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_opening: ScoreRationale
    case_structure: ScoreRationale
    case_math_answer: ScoreRationale
    case_creative_answer: ScoreRationale
    final_recommendation: ScoreRationale
    overall_structure: ScoreRationale
    overall_problem_solving: ScoreRationale
    overall_communication: ScoreRationale


class DialogEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clarity_and_concision: ScoreRationale
    responsiveness_and_adaptation: ScoreRationale
    groundedness: ScoreRationale
    confidence_calibration: ScoreRationale
    multi_turn_coherence: ScoreRationale


class BaselineTurnOutput(BaseModel):
    """The baseline's single per-turn schema, reused whether it's an ordinary move or the terminal
    call. case_performance/quality_dialog/feedback are null unless action is "evaluate", in which
    case all three are populated together -- baseline has no separate judge/eval/feedback turns.
    case_guide_query/profitability_query are this call's own opportunistic RAG ask (empty = none);
    with no separate scouting turn, a query written now is only fetched on the *next* turn."""

    model_config = ConfigDict(extra="forbid")

    reasoning: str
    action: Literal["question", "reveal", "evaluate"]
    content: str
    block_id: str
    case_guide_query: str
    profitability_query: str
    ready_for_evaluation: bool
    case_performance: CaseEvaluation | None
    quality_dialog: DialogEvaluation | None
    feedback: str | None
