from typing import Annotated, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict

"""
Baseline states
"""

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
    scenario_ref: NotRequired[str]
    scenario_data: NotRequired[dict]
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

from typing import Annotated, Literal
import operator
from langgraph.graph import MessagesState
from typing_extensions import TypedDict

"""
Agentic states
"""


def readonly(current, new):
    """Ignore any attempted writes — field is set once at load time."""
    return current

def append_list(current: list, new: list) -> list:
    return current + new


#  Graph State 

class GraphState(TypedDict):

    # Shared (all nodes read, set once by LoadScenario)
    case_prompt:       Annotated[str, readonly]
    candidate_profile: Annotated[dict, readonly]
    turn_index:        int
    transcript:        Annotated[list[str], append_list]

    # Judge + Interviewer only
    case_guidance:     Annotated[str, readonly]
    case_data:         Annotated[dict, readonly]
    enough_evidence:   bool   # Interviewer sets True; Judge can revert to False
    focus_areas:       Annotated[list[str], append_list]  # Judge writes, Interviewer reads

    # Judge only
    case_recommendation: Annotated[str, readonly]   # ground truth from JSON, never shown to candidate
    case_performance:    dict                        # Judge writes after scoring
    quality_dialog:      dict                        # Judge writes after scoring

    # Candidate only
    data_gathered: Annotated[list[str], append_list]  # what the candidate has requested/discovered


#  Node States 

class LoadScenarioState(TypedDict):
    """Reads scenario_XX.json and populates the readonly fields."""
    case_prompt:         str
    candidate_profile:   dict
    case_guidance:       str
    case_data:           dict
    case_recommendation: str


class InterviewerState(TypedDict):
    """Drives the conversation and decides when to call the Judge."""
    case_prompt:      str
    turn_index:       int
    transcript:       list[str]
    enough_evidence:  bool   # writes True when ready to evaluate
    focus_areas:      list[str]  # reads Judge feedback


class JudgeState(TypedDict):
    """Evaluates the transcript against the rubric and ground truth."""
    case_guidance:       str
    case_data:           str
    case_recommendation: str   # ground truth — read only
    transcript:          list[str]
    enough_evidence:     bool         # can revert to False
    focus_areas:         list[str]    # writes guidance for Interviewer
    case_performance:    dict         # writes final score breakdown
    quality_dialog:      dict         # writes dialog quality assessment


class CandidateState(TypedDict):
    """Receives questions and responds — never sees Judge fields."""
    case_prompt:       str
    candidate_profile: dict
    transcript:        list[str]
    data_gathered:     list[str]


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
    messages: NotRequired[list[AnyMessage]]
    scenario_ref: NotRequired[str]
    rubric_data: NotRequired[dict]
    judge_round: NotRequired[int]
    last_judge_turn_index: NotRequired[int]
    latest_question: NotRequired[str]
    latest_answer: NotRequired[str]
    latest_feedback: NotRequired[str]
    interviewer_decision: NotRequired[Literal["ask_candidate", "judge"]]
    interviewer_action: NotRequired[Literal["question", "reveal"]]
    judge_decision: NotRequired[Literal["continue", "score"]]
    focus_area: NotRequired[str]
    interviewer_guidance: NotRequired[str]
    judge_reason: NotRequired[str]
    final_score: NotRequired[int]
