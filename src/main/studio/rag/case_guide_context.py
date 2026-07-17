from __future__ import annotations

from loader import load_selected_simulation_bundle
from rag.rag_case_guide import (
    CASE_GUIDE_CITATION_LABEL,
    CASE_GUIDE_SOURCE_DESCRIPTION,
    retrieve_case_guide_context as _retrieve_case_guide_context,
)
from state import AgenticGraphState
from utils import extract_case_prompt

DEFAULT_TOP_K = 4

__all__ = [
    "CASE_GUIDE_CITATION_LABEL",
    "CASE_GUIDE_SOURCE_DESCRIPTION",
    "DEFAULT_TOP_K",
    "format_case_guide_snippet",
    "format_case_guide_snippets",
    "get_baseline_case_guide_context",
    "resolve_case_guide_query",
    "retrieve_case_guide_context",
]


def format_case_guide_snippet(chunk: dict) -> str:
    """Format one retrieved case-guide chunk as a citeable line, e.g.
    '[Consulting Case Interview Guide by Paloma Pérez de Madrid, p.12] ...'."""
    page = chunk.get("page")
    page_label = f"p.{int(page) + 1}" if isinstance(page, int) else "p.?"
    citation = chunk.get("citation") or CASE_GUIDE_CITATION_LABEL
    content = str(chunk.get("content", "")).strip()
    return f"[{citation}, {page_label}] {content}"


def format_case_guide_snippets(case_guide_context: list[str]) -> str:
    """Format retrieved guide snippets for prompt injection"""
    if not case_guide_context:
        return "None."
    return "\n".join(f"- {snippet}" for snippet in case_guide_context)


def resolve_case_guide_query(state: AgenticGraphState) -> str:
    """Resolve the base case-guide query from the current scenario"""
    case_prompt = str(state.get("case_prompt", "")).strip()
    if case_prompt:
        return case_prompt

    bundle = load_selected_simulation_bundle(scenario_ref=state.get("scenario_ref"))
    return str(extract_case_prompt(bundle["case"])).strip()


def retrieve_case_guide_context(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Bridge from graph modules into the guide PDF retriever"""
    return _retrieve_case_guide_context(query, top_k=top_k)


def get_baseline_case_guide_context(
    state: AgenticGraphState,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[str], dict]:
    """Retrieve guide snippets for the baseline graph with a simple prompt query.

    Deliberately simple (no LLM decides this query) so baseline stays the "dumb"
    arm of the agentic-vs-baseline comparison.

    Returns (snippets, rag_query_log_entry) so callers can persist the retrieval
    query and retrieved chunk ids alongside the rest of the graph state.
    """
    query = resolve_case_guide_query(state) or "consulting case interview methodology"
    case_guide_chunks = retrieve_case_guide_context(query, top_k=top_k)
    snippets = [
        format_case_guide_snippet(chunk)
        for chunk in case_guide_chunks
        if str(chunk.get("content", "")).strip()
    ]
    log_entry = {
        "node": "baseline",
        "source": "case_guide",
        "query": query,
        "top_k": top_k,
        "chunk_ids": [chunk.get("chunk_id") for chunk in case_guide_chunks],
    }
    return snippets, log_entry
