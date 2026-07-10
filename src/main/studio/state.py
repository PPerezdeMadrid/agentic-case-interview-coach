from typing import Annotated

from typing_extensions import NotRequired, TypedDict


def replace_focus_areas(existing: list[str], new_values: list[str] | None) -> list[str]:
    del existing
    if new_values is None:
        return []
    return list(new_values)


def append_rag_query_log(existing: list[dict], new_entries: list[dict] | None) -> list[dict]:
    """Concatenate RAG query-log entries so concurrent nodes (e.g. the two eval
    nodes that fan out from judge) can each append without clobbering the other."""
    if not new_entries:
        return existing
    return existing + list(new_entries)


class AgenticGraphState(TypedDict):
    case_prompt: str
    candidate_profile: dict
    turn_index: int
    transcript: list[str]
    case_guidance: str
    case_data: dict
    enough_evidence: bool
    focus_areas: Annotated[list[str], replace_focus_areas]
    case_recommendation: str
    case_performance: dict
    quality_dialog: dict
    data_gathered: list[str]
    thread_id: NotRequired[str]
    run_id: NotRequired[str]
    trace_step_index: NotRequired[int]
    scenario_ref: NotRequired[str]
    rubric_data: NotRequired[dict]
    judge_round: NotRequired[int]
    retrieved_profitability_context: NotRequired[list[str]]
    rag_query_log: NotRequired[Annotated[list[dict], append_rag_query_log]]
