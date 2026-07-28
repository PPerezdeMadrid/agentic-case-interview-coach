from __future__ import annotations

from rag.rag_case_guide import (
    CASE_GUIDE_CITATION_LABEL,
    CASE_GUIDE_SOURCE_DESCRIPTION,
    retrieve_case_guide_context as _retrieve_case_guide_context,
)
from state import BaselineState

DEFAULT_TOP_K = 4

__all__ = [
    "CASE_GUIDE_CITATION_LABEL",
    "CASE_GUIDE_SOURCE_DESCRIPTION",
    "DEFAULT_TOP_K",
    "format_case_guide_snippet",
    "format_case_guide_snippets",
    "get_pending_case_guide_context",
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


def retrieve_case_guide_context(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Bridge from graph modules into the guide PDF retriever"""
    return _retrieve_case_guide_context(query, top_k=top_k)


def get_pending_case_guide_context(
    state: BaselineState,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[str], dict]:
    """Fetch the case-guide excerpt the *previous* baseline turn asked for, if
    any. Baseline has no separate scouting call -- the single combined schema
    (see BaselineTurnOutput.case_guide_query) lets the model flag a query
    opportunistically while producing its move, so the earliest that query can
    be resolved and shown back to the model is the following turn. Mirrors
    baseline.get_pending_profitability_guide_context.

    Returns (snippets, rag_query_log_entry) so callers can persist the retrieval
    query and retrieved chunk ids alongside the rest of the graph state.
    """
    query = str(state.get("pending_case_guide_query", "") or "").strip()
    if not query:
        return [], {}

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
