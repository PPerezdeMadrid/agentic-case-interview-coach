from typing import Annotated, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


# --------------------------------------------------
# Fake interview content
# --------------------------------------------------

INTERVIEW_QUESTIONS_PHASE_1 = [
    "You are a case interviewer. The client is a large retail company with declining profits over the last two years. What is the first thing you would want to understand?",
    "Good. How would you structure the problem to investigate the decline?",
]

INTERVIEW_QUESTIONS_PHASE_2 = [
    "The judge suggests focusing more on prioritisation and hypothesis-driven thinking. Based on your structure, which area would you investigate first and why?",
    "Good. Now make this more concrete: what specific analysis or metric would you use to confirm your hypothesis?",
]

CANDIDATE_ANSWERS_PHASE_1 = [
    "I would start by separating the problem into revenue and cost drivers, because profit can only decline if one of those moved unfavorably. Then I would check when the decline started, which business units were affected, and whether the issue comes from price, volume, fixed costs, or variable costs.",
    "I would structure it in two branches: revenues and costs. Under revenues I would break down price, volume, product mix, and channel mix. Under costs I would split fixed and variable costs, then look for operational or supply chain changes.",
]

CANDIDATE_ANSWERS_PHASE_2 = [
    "I would prioritize a profit bridge first, because it would quickly show whether the decline is primarily driven by revenue pressure or cost inflation. If revenue is the issue, I would then check whether the problem comes from lower traffic, lower basket size, or pricing pressure.",
    "The specific analysis would be a profit bridge by business unit and by channel. I would compare revenue, gross margin, and operating costs over the last two years to identify which segment explains most of the profit decline.",
]


JUDGE_INTERMEDIATE_FEEDBACK = (
    "Intermediate judge review: the candidate has a clear initial structure, but the reasoning is still quite generic. "
    "Do not score yet. Continue for two more interviewer-candidate iterations. "
    "Focus the next questions on prioritisation, hypothesis-driven thinking, and concrete analysis."
)

JUDGE_FINAL_FEEDBACK = (
    "Final judge review. Score = 4/5. The candidate shows strong critical thinking across the conversation: "
    "they separated profit into revenue and cost drivers, created a coherent structure, and then improved the answer "
    "by prioritising a profit bridge and making the analysis more concrete. The answer is not a 5 because the candidate "
    "could still be more specific about expected data, benchmarks, and final recommendation."
)


# --------------------------------------------------
# State
# --------------------------------------------------

class InterviewState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    transcript: list[str]

    turn_index: int
    judge_round: int

    latest_question: str
    latest_answer: str
    latest_feedback: str

    interviewer_decision: Literal["ask_candidate", "judge"]
    judge_decision: Literal["continue", "score"]

    focus_area: str
    final_score: int


# --------------------------------------------------
# Nodes
# --------------------------------------------------

def interviewer_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    judge_round = state.get("judge_round", 0)

    if judge_round == 0:
        questions = INTERVIEW_QUESTIONS_PHASE_1
    else:
        questions = INTERVIEW_QUESTIONS_PHASE_2

    local_turn_index = turn_index % 2
    question = questions[local_turn_index]

    transcript = state.get("transcript", []) + [f"Interviewer: {question}"]

    return {
        "latest_question": question,
        "interviewer_decision": "ask_candidate",
        "messages": [AIMessage(content=question, name="interviewer")],
        "transcript": transcript,
    }


def candidate_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    judge_round = state.get("judge_round", 0)

    if judge_round == 0:
        answers = CANDIDATE_ANSWERS_PHASE_1
    else:
        answers = CANDIDATE_ANSWERS_PHASE_2

    local_turn_index = turn_index % 2
    answer = answers[local_turn_index]

    next_turn_index = turn_index + 1

    # Every two candidate answers, send conversation to judge
    decision: Literal["ask_candidate", "judge"] = (
        "judge" if next_turn_index % 2 == 0 else "ask_candidate"
    )

    transcript = state["transcript"] + [f"Candidate: {answer}"]

    return {
        "turn_index": next_turn_index,
        "latest_answer": answer,
        "interviewer_decision": decision,
        "messages": [HumanMessage(content=answer, name="candidate")],
        "transcript": transcript,
    }


def judge_node(state: InterviewState) -> InterviewState:
    judge_round = state.get("judge_round", 0)

    if judge_round == 0:
        feedback = JUDGE_INTERMEDIATE_FEEDBACK
        judge_decision: Literal["continue", "score"] = "continue"
        final_score = 0
        focus_area = "Prioritisation, hypothesis-driven thinking, and concrete analysis"
    else:
        feedback = JUDGE_FINAL_FEEDBACK
        judge_decision = "score"
        final_score = 4
        focus_area = ""

    transcript = state["transcript"] + [f"Judge: {feedback}"]

    return {
        "judge_round": judge_round + 1,
        "latest_feedback": feedback,
        "judge_decision": judge_decision,
        "focus_area": focus_area,
        "final_score": final_score,
        "messages": [AIMessage(content=feedback, name="judge")],
        "transcript": transcript,
    }


# --------------------------------------------------
# Routing
# --------------------------------------------------

def route_after_candidate(state: InterviewState) -> Literal["interviewer", "judge"]:
    if state.get("interviewer_decision", "ask_candidate") == "judge":
        return "judge"
    return "interviewer"


def route_after_judge(state: InterviewState) -> Literal["interviewer", "end"]:
    if state.get("judge_decision") == "score":
        return "end"
    return "interviewer"


# --------------------------------------------------
# Build graph
# --------------------------------------------------

builder = StateGraph(InterviewState)

builder.add_node("interviewer", interviewer_node)
builder.add_node("candidate", candidate_node)
builder.add_node("judge", judge_node)

builder.add_edge(START, "interviewer")
builder.add_edge("interviewer", "candidate")

builder.add_conditional_edges(
    "candidate",
    route_after_candidate,
    {
        "interviewer": "interviewer",
        "judge": "judge",
    },
)

builder.add_conditional_edges(
    "judge",
    route_after_judge,
    {
        "interviewer": "interviewer",
        "end": END,
    },
)

graph = builder.compile()


# --------------------------------------------------
# Demo input
# --------------------------------------------------

demo_input: InterviewState = {
    "messages": [],
    "transcript": [],

    "turn_index": 0,
    "judge_round": 0,

    "latest_question": "",
    "latest_answer": "",
    "latest_feedback": "",

    "interviewer_decision": "ask_candidate",
    "judge_decision": "continue",

    "focus_area": "",
    "final_score": 0,
}


# --------------------------------------------------
# Run demo
# --------------------------------------------------

result = graph.invoke(demo_input)

for line in result["transcript"]:
    print(line)
    print()