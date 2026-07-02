from typing import Literal

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import (
    BASELINE_FINAL_FEEDBACK_PROMPT,
    BASELINE_INFORMATION_PROMPT,
    BASELINE_SYSTEM_PROMPT,
    CANDIDATE_SYSTEM_PROMPT,
    CONSULTANCY_QUESTIONS,
    DEFAULT_QUESTION_FALLBACK,
    TOTAL_TURNS,
)
from state import BaselineState


llm_server = ChatOpenAI(
    model="local-model",
    base_url="http://localhost:8081/v1",
    api_key="lm-studio",
    temperature=0.14,
)


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
        "current fraud rate",
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
        "transaction histories",
        "customer behavior",
        "if available",
        "gather the required information",
    ]
    return any(signal in lowered for signal in request_signals)


def _parse_baseline_decision(raw_output: str) -> tuple[str, str, dict]:
    try:
        decision = json.loads(raw_output)
        action = str(decision.get("action", "question")).strip().lower()
        content = str(decision.get("content", "")).strip()
        private_assessment = decision.get("private_assessment", {})
        if not isinstance(private_assessment, dict):
            private_assessment = {}
        return action, content, private_assessment
    except json.JSONDecodeError:
        return (
            "question",
            DEFAULT_QUESTION_FALLBACK,
            {
                "enough_evidence": False,
                "weakest_area": "none",
                "brief_reason": "Invalid JSON returned by baseline model.",
            },
        )


def baseline_node(state: BaselineState) -> BaselineState:
    turn_index = state.get("turn_index", 0)
    transcript = state.get("transcript", [])
    candidate_transcript = state.get("candidate_transcript", [])
    latest_candidate_message = _latest_candidate_message(candidate_transcript)

    if turn_index == 0 and not candidate_transcript:
        opening_question = CONSULTANCY_QUESTIONS[0]
        transcript = transcript + [f"Baseline: {opening_question}"]
        candidate_transcript = candidate_transcript + [f"Interviewer: {opening_question}"]

        return {
            "next_step": "candidate",
            "baseline_action": "question",
            "messages": [AIMessage(content=opening_question, name="baseline")],
            "transcript": transcript,
            "candidate_transcript": candidate_transcript,
            "private_assessment": {
                "enough_evidence": False,
                "weakest_area": "none",
                "brief_reason": "Opening case question from CONSULTANCY_QUESTIONS.",
            },
        }

    messages = [
        SystemMessage(content=BASELINE_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Current turn index: {turn_index}\n"
                f"Maximum allowed turns: {TOTAL_TURNS}\n\n"
                "Full conversation transcript so far:\n"
                + ("\n".join(transcript) if transcript else "No previous messages.")
                + "\n\nDecide whether to ask another question or give final feedback."
            )
        ),
    ]

    response = llm_server.invoke(messages)
    raw_output = response.content.strip()
    raw_output = raw_output.strip()

    if raw_output.startswith("```json"):
        raw_output = raw_output.removeprefix("```json").strip()

    if raw_output.startswith("```"):
        raw_output = raw_output.removeprefix("```").strip()

    if raw_output.endswith("```"):
        raw_output = raw_output.removesuffix("```").strip()

    print("\n[BASELINE RAW OUTPUT]")
    print(raw_output)
    print("[/BASELINE RAW OUTPUT]\n")

    action, content, private_assessment = _parse_baseline_decision(raw_output)

    if action not in ["question", "information", "feedback"]:
        action = "question"

    if action == "question" and _candidate_requested_information(latest_candidate_message):
        info_messages = [
            SystemMessage(content=BASELINE_INFORMATION_PROMPT),
            HumanMessage(
                content=(
                    "Latest candidate message:\n"
                    + latest_candidate_message
                    + "\n\nRelevant conversation transcript:\n"
                    + ("\n".join(transcript) if transcript else "No previous messages.")
                    + "\n\nAnswer the candidate's request directly with case information."
                )
            ),
        ]
        info_response = llm_server.invoke(info_messages)
        info_raw_output = info_response.content.strip()

        if info_raw_output.startswith("```json"):
            info_raw_output = info_raw_output.removeprefix("```json").strip()
        if info_raw_output.startswith("```"):
            info_raw_output = info_raw_output.removeprefix("```").strip()
        if info_raw_output.endswith("```"):
            info_raw_output = info_raw_output.removesuffix("```").strip()

        print("\n[BASELINE INFO RAW OUTPUT]")
        print(info_raw_output)
        print("[/BASELINE INFO RAW OUTPUT]\n")

        info_action, info_content, info_private_assessment = _parse_baseline_decision(info_raw_output)
        if info_action == "information" and info_content:
            action = info_action
            content = info_content
            private_assessment = info_private_assessment


    if not content:
        content = DEFAULT_QUESTION_FALLBACK

    # Force final feedback if maximum turns reached
    if action != "feedback" and turn_index >= TOTAL_TURNS:
        feedback_messages = [
            SystemMessage(content=BASELINE_FINAL_FEEDBACK_PROMPT),
            HumanMessage(
                content=(
                    "Full conversation transcript:\n"
                    + ("\n".join(transcript) if transcript else "No previous messages.")
                    + "\n\nGive final feedback now."
                )
            ),
        ]

        feedback_response = llm_server.invoke(feedback_messages)
        content = feedback_response.content.strip()
        action = "feedback"
        private_assessment = {
            "enough_evidence": True,
            "weakest_area": "none",
            "brief_reason": "Maximum turn limit reached.",
        }

    if action == "feedback":
        transcript = transcript + [f"Baseline feedback: {content}"]

        return {
            "next_step": "end",
            "baseline_action": "feedback",
            "messages": [AIMessage(content=content, name="baseline")],
            "transcript": transcript,
            "candidate_transcript": candidate_transcript,
            "private_assessment": private_assessment,
        }

    transcript_label = "Baseline info" if action == "information" else "Baseline"
    transcript = transcript + [
        f"{transcript_label}: {content}",
        f"Private assessment: {json.dumps(private_assessment, ensure_ascii=False)}",
    ]

    candidate_transcript = candidate_transcript + [f"Interviewer: {content}"]

    return {
        "next_step": "candidate",
        "baseline_action": action,
        "messages": [AIMessage(content=content, name="baseline")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
        "private_assessment": private_assessment,
    }


def candidate_node(state: BaselineState) -> BaselineState:
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
        "next_step": "baseline",
        "messages": [HumanMessage(content=answer, name="candidate")],
        "transcript": transcript,
        "candidate_transcript": candidate_transcript,
    }


def route_after_baseline(state: BaselineState) -> Literal["candidate", "end"]:
    if state.get("baseline_action") == "feedback":
        return "end"
    return state.get("next_step", "end")


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
    "candidate_transcript": [],
    "turn_index": 0,
    "next_step": "baseline",
    "private_assessment": {},
}


if __name__ == "__main__":
    result = graph.invoke(demo_input)
