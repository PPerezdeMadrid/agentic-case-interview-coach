"""Retrieval evaluation: Precision@K, Recall@K, Hit Rate, MRR.

Evaluated against golden sets that carry exact per-query `source_chunk_ids` as ground truth.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

WEB_DIR = Path(__file__).resolve().parent
MAIN_DIR = WEB_DIR.parent
SRC_ROOT = MAIN_DIR.parent
STUDIO_DIR = MAIN_DIR / "studio"

if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from rag.rag_case_guide import retrieve_case_guide_context  # noqa: E402
from rag.rag_profitability_guide import retrieve_profitability_guide_context  # noqa: E402

RAG_EVAL_DIR = SRC_ROOT / "database" / "rag_evaluation"

DEFAULT_TOP_K = 5
MIN_TOP_K = 1
MAX_TOP_K = 20

GOLDEN_SETS: list[dict[str, Any]] = [
    {
        "path": RAG_EVAL_DIR / "generation_golden_set_case_guide.csv",
        "source_label": "Case Guide",
        "retrieve": retrieve_case_guide_context,
    },
    {
        "path": RAG_EVAL_DIR / "generation_golden_set_profitability.csv",
        "source_label": "Profitability Guide",
        "retrieve": retrieve_profitability_guide_context,
    },
]

_CACHE: dict[int, dict[str, Any]] = {}


def _load_golden_rows(golden_set: dict[str, Any]) -> list[dict[str, Any]]:
    path: Path = golden_set["path"]
    if not path.exists():
        raise FileNotFoundError(f"Golden set not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 3)


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return {
        "n_queries": len(rows),
        "precision_at_k": _mean([r["precision_at_k"] for r in rows]),
        "recall_at_k": _mean([r["recall_at_k"] for r in rows]),
        "hit_rate": _mean([r["hit"] for r in rows]),
        "mrr": _mean([r["reciprocal_rank"] for r in rows]),
    }


def _aggregate_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row[key]].append(row)

    result = []
    for value, bucket_rows in sorted(buckets.items()):
        agg = _aggregate(bucket_rows)
        if agg is not None:
            agg[key] = value
            result.append(agg)
    return result


def _evaluate(top_k: int) -> dict[str, Any]:
    per_query_rows: list[dict[str, Any]] = []

    for golden_set in GOLDEN_SETS:
        retrieve: Callable[..., list[dict[str, Any]]] = golden_set["retrieve"]
        for row in _load_golden_rows(golden_set):
            relevant_chunk_ids = {
                cid.strip() for cid in (row.get("source_chunk_ids") or "").split(";") if cid.strip()
            }

            retrieved = retrieve(row["query"], top_k=top_k)
            relevant_flags = [chunk["chunk_id"] in relevant_chunk_ids for chunk in retrieved]
            n_relevant_retrieved = sum(relevant_flags)

            rank = next((i + 1 for i, flag in enumerate(relevant_flags) if flag), None)

            per_query_rows.append(
                {
                    "query_id": row.get("query_id", ""),
                    "query": row.get("query", ""),
                    "category": row.get("category", ""),
                    "source_label": golden_set["source_label"],
                    "n_relevant_total": len(relevant_chunk_ids),
                    "retrieved": [
                        {"chunk_id": chunk["chunk_id"], "page": chunk.get("page"), "relevant": flag}
                        for chunk, flag in zip(retrieved, relevant_flags)
                    ],
                    "precision_at_k": round(n_relevant_retrieved / len(retrieved), 3) if retrieved else 0.0,
                    "recall_at_k": (
                        round(n_relevant_retrieved / len(relevant_chunk_ids), 3) if relevant_chunk_ids else None
                    ),
                    "hit": 1 if n_relevant_retrieved > 0 else 0,
                    "first_relevant_rank": rank,
                    "reciprocal_rank": round(1 / rank, 3) if rank else 0.0,
                }
            )

    return {
        "top_k": top_k,
        "rows": per_query_rows,
        "overall": _aggregate(per_query_rows),
        "by_category": _aggregate_by(per_query_rows, "category"),
        "by_source": _aggregate_by(per_query_rows, "source_label"),
    }


def evaluate_retrieval(top_k: int = DEFAULT_TOP_K, *, refresh: bool = False) -> dict[str, Any]:
    top_k = max(MIN_TOP_K, min(MAX_TOP_K, top_k))
    if refresh or top_k not in _CACHE:
        _CACHE[top_k] = _evaluate(top_k)
    return _CACHE[top_k]
