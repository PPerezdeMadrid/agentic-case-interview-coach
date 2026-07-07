from __future__ import annotations

from typing import Any

from rag.rag_profitability_guide import (
    PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
    format_profitability_guide_context as _format_profitability_guide_context,
    retrieve_profitability_guide_context as _retrieve_profitability_guide_context,
)
from state import AgenticGraphState
from utils import normalize_string_list

DEFAULT_TOP_K = 4


def build_profitability_retrieval_query(
    case_prompt: str,
    transcript: list[str],
    *,
    evaluation_target: str = "",
    focus_areas: list[str] | None = None,
) -> str:
    relevant_lines = [line.strip() for line in transcript[-8:] if isinstance(line, str) and line.strip()]
    recent_transcript = "\n".join(relevant_lines)
    candidate_final_recommendation = ""
    for line in reversed(transcript):
        if isinstance(line, str) and line.startswith("Candidate:"):
            candidate_final_recommendation = line.strip()
            break

    normalized_focus_areas = normalize_string_list(focus_areas or [])
    
    # so it is easier to read for agents
    sections = [
        "Consulting profitability case methodology grounded in managerial accounting.",
        f"Evaluation target: {evaluation_target.strip()}" if evaluation_target.strip() else "",
        f"Case prompt: {case_prompt.strip()}" if case_prompt.strip() else "",
        f"Recent transcript:\n{recent_transcript}" if recent_transcript else "",
        f"Latest candidate recommendation: {candidate_final_recommendation}" if candidate_final_recommendation else "",
        (
            "Judge focus areas or coaching targets: " + "; ".join(normalized_focus_areas)
            if normalized_focus_areas
            else ""
        ),
        "Source coverage: " + PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
        (
            "Write the retrieval intent for this exact situation using the source coverage above. "
            "Retrieve only the parts of the textbook that are most useful for the current case, reasoning step, "
            "or evaluation need."
        ),
    ]
    return "\n".join(section for section in sections if section)


def retrieve_profitability_guide_context(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Bridge from graph modules into the profitability PDF retriever"""
    return _retrieve_profitability_guide_context(query, top_k=top_k)


def format_profitability_guide_context(chunks: list[dict[str, Any]]) -> str:
    """Bridge from graph modules into the profitability PDF formatter"""
    return _format_profitability_guide_context(chunks)


def get_profitability_guide_context(state: AgenticGraphState, *,evaluation_target: str,top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Retrieve profitability-guide snippets tailored to the current situation"""
    query = build_profitability_retrieval_query(
        str(state.get("case_prompt", "")),
        state.get("transcript", []),
        evaluation_target=evaluation_target,
        focus_areas=normalize_string_list(state.get("focus_areas", [])),
    )
    if not query.strip():
        return []
    return retrieve_profitability_guide_context(query, top_k=top_k)
