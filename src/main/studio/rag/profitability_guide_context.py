from __future__ import annotations

from rag.rag_profitability_guide import (
    PROFITABILITY_SOURCE_NAVIGATION_GUIDE,
    format_profitability_guide_context as _format_profitability_guide_context,
    retrieve_profitability_guide_context as _retrieve_profitability_guide_context,
)

DEFAULT_TOP_K = 4

__all__ = [
    "DEFAULT_TOP_K",
    "PROFITABILITY_SOURCE_NAVIGATION_GUIDE",
    "format_profitability_guide_context",
    "retrieve_profitability_guide_context",
]


def retrieve_profitability_guide_context(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Bridge from graph modules into the profitability PDF retriever"""
    return _retrieve_profitability_guide_context(query, top_k=top_k)


def format_profitability_guide_context(chunks: list[dict]) -> str:
    """Bridge from graph modules into the profitability PDF formatter"""
    return _format_profitability_guide_context(chunks)
