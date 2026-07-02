from typing import Annotated, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


BASELINE_PROMPTS = [
    (
        "Let's begin. The client is a large retail company with declining profits "
        "over the last two years. Walk me through your initial approach."
    ),
    (
        "Good start. Now prioritise the area you would investigate first and explain why."
    ),
    (
        "Make it more concrete. What analysis or metric would you use to confirm your hypothesis?"
    ),
]

CANDIDATE_ANSWERS = [
    (
        "I would start by separating the problem into revenue and cost drivers, then "
        "identify which business units and time periods explain most of the decline."
    ),
    (
        "I would prioritise a profit bridge first, because it would show whether the "
        "decline is mainly driven by revenue pressure or cost inflation."
    ),
    (
        "I would use a profit bridge by business unit and channel, comparing revenue, "
        "gross margin, and operating costs over the last two years."
    ),
]

TOTAL_TURNS = 3


class BaselineState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    transcript: list[str]
    turn_index: int
    next_step: Literal["candidate", "baseline", "end"]


def baseline_node(state: BaselineState) -> BaselineState:
    turn_index = state.get("turn_index", 0)

    if turn_index >= TOTAL_TURNS:
        closing_message = "Baseline: Interview complete."
        transcript = state.get("transcript", []) + [closing_message]
        return {
            "next_step": "end",
            "messages": [AIMessage(content=closing_message, name="baseline")],
            "transcript": transcript,
        }

    prompt = BASELINE_PROMPTS[turn_index]
    transcript = state.get("transcript", []) + [f"Baseline: {prompt}"]

    return {
        "next_step": "candidate",
        "messages": [AIMessage(content=prompt, name="baseline")],
        "transcript": transcript,
    }


def candidate_node(state: BaselineState) -> BaselineState:
    turn_index = state.get("turn_index", 0)
    answer = CANDIDATE_ANSWERS[turn_index]
    next_turn_index = turn_index + 1
    transcript = state.get("transcript", []) + [f"Candidate: {answer}"]

    return {
        "turn_index": next_turn_index,
        "next_step": "baseline",
        "messages": [HumanMessage(content=answer, name="candidate")],
        "transcript": transcript,
    }


def route_after_baseline(state: BaselineState) -> Literal["candidate", "end"]:
    if state.get("next_step") == "end":
        return "end"
    return "candidate"


builder = StateGraph(BaselineState)

builder.add_node("baseline", baseline_node)
builder.add_node("candidate", candidate_node)

builder.add_edge(START, "baseline")
builder.add_conditional_edges(
    "baseline",
    route_after_baseline,
    {
        "candidate": "candidate",
        "end": END,
    },
)
builder.add_edge("candidate", "baseline")

graph = builder.compile()


demo_input: BaselineState = {
    "messages": [],
    "transcript": [],
    "turn_index": 0,
    "next_step": "candidate",
}


result = graph.invoke(demo_input)

for line in result["transcript"]:
    print(line)
    print()
