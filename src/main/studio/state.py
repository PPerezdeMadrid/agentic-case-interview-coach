from typing import Annotated

from typing_extensions import NotRequired, TypedDict


def append_focus_areas(existing: list[str], new_values: list[str] | None) -> list[str]:
    if new_values is None:
        return []

    merged = list(existing)
    for value in new_values:
        if value not in merged:
            merged.append(value)
    return merged


class AgenticGraphState(TypedDict):
    case_prompt: str
    candidate_profile: dict
    turn_index: int
    transcript: list[str]
    case_guidance: str
    case_data: dict
    enough_evidence: bool
    focus_areas: Annotated[list[str], append_focus_areas]
    case_recommendation: str
    case_performance: dict
    quality_dialog: dict
    data_gathered: list[str]
    thread_id: NotRequired[str]
    scenario_ref: NotRequired[str]
    rubric_data: NotRequired[dict]
    judge_round: NotRequired[int]
    profitability_knowledge_base: NotRequired[dict]
    retrieved_profitability_context: NotRequired[list[str]]
