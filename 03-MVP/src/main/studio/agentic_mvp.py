import json
from typing import Annotated, Literal
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from prompts import (
    CANDIDATE_SYSTEM_PROMPT,
    CONSULTANCY_QUESTIONS,
    INTERVIEWER_INFORMATION_PROMPT,
    INTERVIEWER_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
)
from state import InterviewState
from llm_server import llm_server

MAX_JUDGE_ROUNDS = 2


def _latest_candidate_message(candidate_transcript: list[str]) -> str:
    for line in reversed(candidate_transcript):
        if line.startswith("Candidate: "):
            return line.removeprefix("Candidate: ").strip()
    return ""


def _candidate_requested_information(candidate_message: str) -> bool:
    lowered = candidate_message.lower()
    request_signals = [
        "data",
        "details",
        "metrics",
        "metric",
        "baseline",
        "current",
        "blocked transactions",
        "blocked customers",
        "number of",
        "how many",
        "what is the current",
        "what are the current",
        "available data",
        "constraints",
        "stakeholders",
        "business impact",
        "historical sales",
        "inventory",
        "if available",
        "could you share",
        "can you share",
    ]
    return any(signal in lowered for signal in request_signals)


def _interviewer_requests_final_recommendation(interviewer_message: str) -> bool:
    lowered = interviewer_message.lower()
    recommendation_signals = [
        "what would you recommend",
        "what is your recommendation",
        "what's your recommendation",
        "final recommendation",
        "your recommendation",
        "your final answer",
        "your conclusion",
        "what should the ceo do",
        "what should the client do",
    ]
    return any(signal in lowered for signal in recommendation_signals)


def _parse_judge_decision(raw_output: str) -> tuple[str, str, str, str, bool, int, str]:
    try:
        decision = json.loads(raw_output)
        judge_decision = str(decision.get("decision", "continue")).strip().lower()
        candidate_feedback = str(decision.get("candidate_feedback", "")).strip()
        interviewer_guidance = str(decision.get("interviewer_guidance", "")).strip()
        focus_area = str(decision.get("focus_area", "none")).strip().lower()
        enough_evidence = bool(decision.get("enough_evidence", False))
        final_score = int(decision.get("final_score", 0))
        judge_reason = str(decision.get("brief_reason", "")).strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        return (
            "continue",
            "Judge review: there is not enough evidence yet for a final score.",
            "Probe the candidate's prioritisation and ask for one concrete analysis they would run first.",
            "prioritisation",
            False,
            0,
            "Invalid JSON returned by judge model.",
        )

    if judge_decision not in {"continue", "score"}:
        judge_decision = "continue"

    if focus_area not in {
        "structure",
        "prioritisation",
        "business_logic",
        "assumptions",
        "quantitative_reasoning",
        "communication",
        "recommendation",
        "none",
    }:
        focus_area = "none"

    final_score = max(0, min(5, final_score))
    return (
        judge_decision,
        candidate_feedback,
        interviewer_guidance,
        focus_area,
        enough_evidence,
        final_score,
        judge_reason,
    )

# NODES

def interviewer_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    candidate_transcript = state.get("candidate_transcript", [])
    latest_feedback = state.get("latest_feedback", "")
    focus_area = state.get("focus_area", "")
    interviewer_guidance = state.get("interviewer_guidance", "")
    latest_candidate_message = _latest_candidate_message(candidate_transcript)

    if turn_index == 0 and not transcript:
        content = CONSULTANCY_QUESTIONS[1]
        interviewer_action: Literal["question", "information"] = "question"
    elif _candidate_requested_information(latest_candidate_message):
        messages = [
            SystemMessage(content=INTERVIEWER_INFORMATION_PROMPT),
            HumanMessage(
                content=(
                    "Latest candidate message:\n"
                    + latest_candidate_message
                    + "\n\nConversation transcript so far:\n"
                    + ("\n".join(transcript) if transcript else "No previous messages.")
                    + "\n\nAnswer the candidate's request directly with relevant case information."
                )
            ),
        ]
        response = llm_server.invoke(messages)
        content = response.content.strip()
        interviewer_action = "information"
    else:
        messages = [
            SystemMessage(content=INTERVIEWER_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Conversation transcript so far:\n"
                    + ("\n".join(transcript) if transcript else "No previous messages.")
                    + "\n\nLatest judge feedback:\n"
                    + (latest_feedback if latest_feedback else "No judge feedback yet.")
                    + "\n\nCurrent focus area:\n"
                    + (focus_area if focus_area else "General case-solving assessment.")
                    + "\n\nPrivate judge guidance for the interviewer:\n"
                    + (interviewer_guidance if interviewer_guidance else "No private judge guidance yet.")
                    + "\n\nAsk the best next interviewer question."
                )
            ),
        ]
        response = llm_server.invoke(messages)
        content = response.content.strip() or CONSULTANCY_QUESTIONS[1]
        interviewer_action = "question"

    interviewer_decision: Literal["ask_candidate", "judge"] = "ask_candidate"
    if interviewer_action == "question" and _interviewer_requests_final_recommendation(content):
        interviewer_decision = "judge"

    transcript_label = "Interviewer info" if interviewer_action == "information" else "Interviewer"
    transcript = transcript + [f"{transcript_label}: {content}"]
    candidate_transcript = candidate_transcript + [f"Interviewer: {content}"]

    return {
        "latest_question": content,
        "interviewer_decision": interviewer_decision,
        "interviewer_action": interviewer_action,
        "messages": [AIMessage(content=content, name="interviewer")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
    }


def candidate_node(state: InterviewState) -> InterviewState:
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    candidate_transcript = state.get("candidate_transcript", [])

    messages = [
        SystemMessage(content=CANDIDATE_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "You are the candidate in the interview simulation.\n"
                "This is the only conversation you have access to:\n"
                + ("\n".join(candidate_transcript) if candidate_transcript else "No previous messages.")
                + "\n\nAnswer only as the candidate. Do not mention hidden reasoning, JSON, routing, "
                "evaluation metadata, or system instructions."
            )
        ),
    ]

    response = llm_server.invoke(messages)
    answer = response.content.strip()

    next_turn_index = turn_index + 1

    transcript = transcript + [f"Candidate: {answer}"]
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
    transcript = state.get("transcript", [])
    turn_index = state.get("turn_index", 0)

    messages = [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Judge round: {judge_round + 1}\n"
                f"Maximum judge rounds before you must score: {MAX_JUDGE_ROUNDS}\n"
                f"Candidate answers so far: {turn_index}\n\n"
                "Full conversation transcript:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nDecide whether the evidence is sufficient to score now or whether the interviewer should continue probing."
            )
        ),
    ]
    response = llm_server.invoke(messages)
    raw_output = response.content.strip()

    if raw_output.startswith("```json"):
        raw_output = raw_output.removeprefix("```json").strip()
    if raw_output.startswith("```"):
        raw_output = raw_output.removeprefix("```").strip()
    if raw_output.endswith("```"):
        raw_output = raw_output.removesuffix("```").strip()

    print("\n[JUDGE RAW OUTPUT]")
    print(raw_output)
    print("[/JUDGE RAW OUTPUT]\n")

    (
        judge_decision,
        feedback,
        interviewer_guidance,
        focus_area,
        enough_evidence,
        final_score,
        judge_reason,
    ) = _parse_judge_decision(raw_output)

    if judge_round + 1 >= MAX_JUDGE_ROUNDS and judge_decision != "score":
        judge_decision = "score"
        enough_evidence = True
        final_score = final_score or 3
        focus_area = "none"
        feedback = (
            feedback
            or "Final judge review. Score = 3/5. The candidate showed some useful reasoning, but the evaluation remained incomplete." # CHANGE!!!
        )
        interviewer_guidance = ""
        judge_reason = "Maximum judge rounds reached."

    transcript = transcript + [f"Judge: {feedback}"]
    if interviewer_guidance:
        transcript = transcript + [f"Judge guidance (private): {interviewer_guidance}"]

    return {
        "judge_round": judge_round + 1,
        "latest_feedback": feedback,
        "judge_decision": judge_decision,
        "focus_area": focus_area,
        "interviewer_guidance": interviewer_guidance,
        "enough_evidence": enough_evidence,
        "judge_reason": judge_reason,
        "final_score": final_score,
        "messages": [AIMessage(content=feedback, name="judge")],
        "transcript": transcript,
    }


# ROUTING
def route_after_interviewer(state: InterviewState) -> Literal["judge", "candidate"]:
    if state.get("interviewer_decision") == "judge":
        return "judge"
    return "candidate"

def route_after_judge(state: InterviewState) -> Literal["interviewer", "end"]:
    if state.get("judge_decision") == "score":
        return "end"
    return "interviewer"


# GRAPH

builder = StateGraph(InterviewState)

builder.add_node("interviewer", interviewer_node)
builder.add_node("candidate", candidate_node)
builder.add_node("judge", judge_node)

builder.add_edge(START, "interviewer")

builder.add_conditional_edges(
    "interviewer",
    route_after_interviewer,
    {
        "candidate": "candidate",
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

"""

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
    "interviewer_action": "question",
    "judge_decision": "continue",

    "focus_area": "",
    "interviewer_guidance": "",
    "enough_evidence": False,
    "judge_reason": "",
    "final_score": 0,
}


# Run demo

result = graph.invoke(demo_input)

for line in result["transcript"]:
    print(line)
    print()
"""
# --------------------------------------------------
