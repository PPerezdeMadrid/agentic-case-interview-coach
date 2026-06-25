from typing_extensions import NotRequired, TypedDict


class AgenticGraphState(TypedDict):
    case_prompt: str
    candidate_profile: dict
    turn_index: int
    transcript: list[str]
    case_guidance: str
    case_data: dict
    enough_evidence: bool
    focus_areas: list[str]
    case_recommendation: str
    case_performance: dict
    quality_dialog: dict
    data_gathered: list[str]
    scenario_ref: NotRequired[str]
    rubric_data: NotRequired[dict]
    judge_round: NotRequired[int]
    knowledge_base: NotRequired[dict]
    retrieved_public_context: NotRequired[list[str]]
    retrieved_private_context: NotRequired[list[str]]
