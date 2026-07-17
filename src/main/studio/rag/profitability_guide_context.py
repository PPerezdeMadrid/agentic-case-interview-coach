from __future__ import annotations

from rag.rag_profitability_guide import (
    PROFITABILITY_CITATION_LABEL,
    PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
    format_profitability_guide_context as _format_profitability_guide_context,
    retrieve_profitability_guide_context as _retrieve_profitability_guide_context,
)

DEFAULT_TOP_K = 4

__all__ = [
    "DEFAULT_TOP_K",
    "PROFITABILITY_CITATION_LABEL",
    "PROFITABILITY_SOURCE_NAVIGATION_GUIDE",
    "format_profitability_guide_context",
    "format_profitability_guide_snippet",
    "retrieve_profitability_guide_context",
]


def format_profitability_guide_snippet(chunk: dict) -> str:
    """Format one retrieved profitability chunk as a citeable line, e.g.
    '[Principles of Managerial Accounting by Dr. Patricia Goedl, p.42] ...'."""
    page = chunk.get("page")
    page_label = f"p.{int(page) + 1}" if isinstance(page, int) else "p.?"
    citation = chunk.get("citation") or PROFITABILITY_CITATION_LABEL
    content = str(chunk.get("content", "")).strip()
    return f"[{citation}, {page_label}] {content}"


def retrieve_profitability_guide_context(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Bridge from graph modules into the profitability PDF retriever"""
    return _retrieve_profitability_guide_context(query, top_k=top_k)


def format_profitability_guide_context(chunks: list[dict]) -> str:
    """Bridge from graph modules into the profitability PDF formatter"""
    return _format_profitability_guide_context(chunks)
