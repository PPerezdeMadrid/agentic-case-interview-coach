from __future__ import annotations

from state import AgenticGraphState
from utils import normalize_string_list


def format_case_guide_snippets(case_guide_context: list[str]) -> str:
    """Format retrieved guide snippets for prompt injection."""
    if not case_guide_context:
        return "None."
    return "\n".join(f"- {snippet}" for snippet in case_guide_context)


def build_case_guide_query(
    state: AgenticGraphState,
    case_prompt: str,
    node_name: str,
) -> str:
    """Build a simple natural-language retrieval query for the consulting guide."""
    transcript = state.get("transcript", [])
    latest_candidate_turn = next(
        (
            line.removeprefix("Candidate: ").strip()
            for line in reversed(transcript)
            if line.startswith("Candidate:")
        ),
        "",
    )
    focus_areas = normalize_string_list(state.get("focus_areas", []))

    node_goal_by_name = {
        "judge": "Decide what evidence is still missing before evaluating the candidate.",
        "eval_case_performance": "Evaluate the quality of the candidate's case-solving approach.",
        "eval_dialog_quality": "Evaluate the quality of the candidate's communication and interaction.",
        "give_feedback": "Generate actionable coaching feedback for the candidate.",
    }
    node_goal = node_goal_by_name.get(node_name, "Retrieve the most useful consulting-case methodology.")

    return "\n".join(
        part
        for part in [
            f"Case prompt: {case_prompt}" if case_prompt else "",
            f"Current goal: {node_goal}",
            (
                "Judge focus areas or coaching targets: "
                + "; ".join(focus_areas)
                if focus_areas
                else ""
            ),
            f"Latest candidate reasoning: {latest_candidate_turn}" if latest_candidate_turn else "",
            (
                "Retrieve methodology, evaluation criteria, common mistakes, and examples of strong candidate behaviour "
                "that are most relevant to this exact situation."
            ),
        ]
        if part
    )
