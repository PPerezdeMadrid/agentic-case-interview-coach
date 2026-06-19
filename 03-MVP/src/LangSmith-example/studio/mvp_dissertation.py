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
    "Based on your structure, which area would you investigate first and why?",
    "You have identified a priority area. What specific analysis or metric would you use to confirm your hypothesis?",
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
    candidate_transcript: list[str]

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
    transcript_so_far = state.get("transcript", [])
    turn_index = state.get("turn_index", 0)
    judge_round = state.get("judge_round", 0)
    latest_answer = state.get("latest_answer", "")
    latest_feedback = state.get("latest_feedback", "")
    focus_area = state.get("focus_area", "")
    last_transcript_entry = transcript_so_far[-1] if transcript_so_far else ""

    if judge_round == 0:
        questions = INTERVIEW_QUESTIONS_PHASE_1
    else:
        questions = INTERVIEW_QUESTIONS_PHASE_2

    local_turn_index = turn_index % 2
    question = questions[local_turn_index]
    interviewer_decision: Literal["ask_candidate", "judge"] = (
        "judge"
        if latest_answer and turn_index % 2 == 0 and last_transcript_entry.startswith("Candidate: ")
        else "ask_candidate"
    )

    if interviewer_decision == "ask_candidate" and judge_round > 0 and local_turn_index < len(INTERVIEW_QUESTIONS_PHASE_2):
        if focus_area:
            question = f"{question} Focus on {focus_area.lower()}."
        elif latest_feedback:
            question = f"{question} Use the previous evaluation to probe the weak spots more directly."

    transcript = transcript_so_far + [f"Interviewer: {question}"]
    candidate_transcript = state.get("candidate_transcript", []) + [f"Interviewer: {question}"]

    return {
        "latest_question": question,
        "interviewer_decision": interviewer_decision,
        "messages": [AIMessage(content=question, name="interviewer")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
    }


def candidate_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    judge_round = state.get("judge_round", 0)
    candidate_transcript = state.get("candidate_transcript", [])

    if judge_round == 0:
        answers = CANDIDATE_ANSWERS_PHASE_1
    else:
        answers = CANDIDATE_ANSWERS_PHASE_2

    local_turn_index = turn_index % 2
    answer = answers[local_turn_index]

    next_turn_index = turn_index + 1

    transcript = state["transcript"] + [f"Candidate: {answer}"]
    candidate_transcript = candidate_transcript + [f"Candidate: {answer}"]

    return {
        "turn_index": next_turn_index,
        "latest_answer": answer,
        "messages": [HumanMessage(content=answer, name="candidate")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
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
        "messages": [],
        "transcript": transcript,
    }


# --------------------------------------------------
# Routing
# --------------------------------------------------

def route_after_interviewer(state: InterviewState) -> Literal["interviewer", "judge"]:
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
builder.add_conditional_edges(
    "interviewer",
    route_after_interviewer,
    {
        "interviewer": "candidate",
        "judge": "judge",
    },
)
builder.add_edge("candidate", "interviewer")

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
    "candidate_transcript": [],

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
