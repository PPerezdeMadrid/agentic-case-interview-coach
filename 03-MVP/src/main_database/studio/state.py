from typing import Annotated, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict


class BaselineState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    transcript: list[str] # Transcript for eval/debug
    candidate_transcript: list[str]
    turn_index: int
    next_step: Literal["candidate", "baseline", "end"]
    baseline_action: NotRequired[Literal["question", "information", "feedback"]]
    private_assessment: NotRequired[dict]

class InterviewState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    transcript: list[str]
    candidate_transcript: list[str]
    case_name: NotRequired[str]
    case_data: NotRequired[dict]
    rubric_data: NotRequired[dict]
    turn_index: int
    judge_round: int
    last_judge_turn_index: int
    latest_question: str
    latest_answer: str
    latest_feedback: str
    interviewer_decision: Literal["ask_candidate", "judge"]
    interviewer_action: NotRequired[Literal["question", "reveal"]]
    judge_decision: Literal["continue", "score"]
    focus_area: str
    interviewer_guidance: str
    enough_evidence: bool
    judge_reason: str
    final_score: int
