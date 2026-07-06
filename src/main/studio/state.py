from typing import Annotated

from typing_extensions import NotRequired, TypedDict


def replace_focus_areas(existing: list[str], new_values: list[str] | None) -> list[str]:
    del existing
    if new_values is None:
        return []
    return list(new_values)


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
    profitability_knowledge_base: NotRequired[dict]
    retrieved_profitability_context: NotRequired[list[str]]
