"""Backfill `source_chunk_ids` onto `retrieve_golden_set.csv`.

`retrieve_golden_set.csv` only carries `source_document` + `source_page`, unlike the
generation golden sets which already have exact per-query `source_chunk_ids`. This
resolves chunk-level ground truth automatically: embed each row's `answer` (and
`query`) text, similarity-search the correct vector store for candidates, then score
each candidate by lexical word-overlap against the answer to pick the chunk(s) that
actually contain that content -- semantic search alone can return a topically related
but wrong chunk, so the lexical check is what turns "plausible" into "grounded".

Rows the heuristic isn't confident about are flagged for manual review rather than
silently accepted, since this backs a dissertation dataset.

Usage (from repo root, with the project venv active):
    python -m src.main.studio.rag.build_retrieve_golden_set_chunk_ids            # report only
    python -m src.main.studio.rag.build_retrieve_golden_set_chunk_ids --apply    # rewrite the CSV
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

from src.main.studio.rag.rag_case_guide import CASE_GUIDE_PDF_PATH, get_case_guide_vectorstore
from src.main.studio.rag.rag_profitability_guide import (
    PROFITABILITY_GUIDE_PDF_PATH,
    get_profitability_guide_vectorstore,
)

RAG_EVAL_DIR = Path(__file__).resolve().parents[3] / "database" / "rag_evaluation"
GOLDEN_SET_PATH = RAG_EVAL_DIR / "retrieve_golden_set.csv"
REPORT_PATH = RAG_EVAL_DIR / "retrieve_golden_set_chunk_match_report.csv"

CANDIDATE_K = 8
HIGH_CONFIDENCE = 0.5
MEDIUM_CONFIDENCE = 0.3
SECOND_CHUNK_MIN_SCORE = 0.25

STOPWORDS = {
    "this", "that", "with", "from", "into", "than", "then", "them", "they", "their",
    "there", "these", "those", "which", "while", "what", "when", "where", "should",
    "would", "could", "about", "being", "been", "have", "has", "had", "does", "doing",
    "the", "and", "for", "are", "was", "were", "not", "but", "you", "your", "its",
    "it's", "each", "some", "such", "most", "more", "less", "over", "under", "also",
    "guide", "candidate", "candidates", "case", "interview",
}


def _normalize_source_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


SOURCES: dict[str, dict[str, Any]] = {
    _normalize_source_name(CASE_GUIDE_PDF_PATH.name): {
        "label": "Case Guide",
        "get_store": get_case_guide_vectorstore,
    },
    _normalize_source_name(PROFITABILITY_GUIDE_PDF_PATH.name): {
        "label": "Profitability Guide",
        "get_store": get_profitability_guide_vectorstore,
    },
}


def _resolve_source(source_document: str) -> dict[str, Any] | None:
    return SOURCES.get(_normalize_source_name(source_document))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS}


def _overlap_score(answer_words: set[str], chunk_text: str) -> float:
    if not answer_words:
        return 0.0
    return len(answer_words & _words(chunk_text)) / len(answer_words)


def _chunk_index(chunk_id: str) -> int | None:
    match = re.search(r"chunk_(\d+)$", chunk_id)
    return int(match.group(1)) if match else None


def resolve_chunk_ids(row: dict[str, str], store: Any) -> tuple[list[str], float]:
    answer = row.get("answer", "")
    query = row.get("query", "")

    candidates = {doc.id: doc for doc in store.similarity_search(answer, k=CANDIDATE_K)}
    for doc in store.similarity_search(query, k=CANDIDATE_K):
        candidates.setdefault(doc.id, doc)

    answer_words = _words(answer)

    # Deliberately no bonus for matching `source_section` text: a section heading
    # only appears verbatim in the first chunk of that section, so rewarding it
    # systematically favors that chunk over the one that actually continues the
    # matching content -- confirmed this flipped a real pick (CG_FW_001 picked the
    # section-opening chunk_10 over the actually-matching chunk_12) before removal.
    scored = [(chunk_id, _overlap_score(answer_words, doc.page_content), doc) for chunk_id, doc in candidates.items()]
    scored.sort(key=lambda t: -t[1])

    if not scored:
        return [], 0.0

    best_id, best_score, _ = scored[0]
    chosen = [best_id]

    # Check the immediate neighbor chunks directly (chunking is sequential, so the
    # continuation of an answer that spans a chunk boundary is always chunk_N-1/N+1) --
    # relying on the embedding candidate pool alone can miss it if it doesn't happen
    # to rank in the top-K for this particular query/answer text.
    best_index = _chunk_index(best_id)
    if best_index is not None:
        stem = best_id.rsplit("::chunk_", 1)[0]
        neighbor_ids = [f"{stem}::chunk_{best_index - 1}", f"{stem}::chunk_{best_index + 1}"]
        neighbor_data = store.get(ids=neighbor_ids, include=["documents"])
        neighbor_scored = [
            (neighbor_id, _overlap_score(answer_words, content))
            for neighbor_id, content in zip(neighbor_data["ids"], neighbor_data["documents"])
        ]
        neighbor_scored.sort(key=lambda t: -t[1])
        if neighbor_scored and neighbor_scored[0][1] >= SECOND_CHUNK_MIN_SCORE:
            chosen.append(neighbor_scored[0][0])

    chosen.sort(key=lambda cid: (_chunk_index(cid) if _chunk_index(cid) is not None else 0))
    return chosen, best_score


def _confidence_label(score: float) -> str:
    if score >= HIGH_CONFIDENCE:
        return "high"
    if score >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Rewrite retrieve_golden_set.csv in place")
    args = parser.parse_args()

    with GOLDEN_SET_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "source_chunk_ids" not in fieldnames:
        fieldnames.append("source_chunk_ids")

    report_rows = []
    counts = {"high": 0, "medium": 0, "low": 0, "unresolved_source": 0}

    for row in rows:
        source = _resolve_source(row.get("source_document", ""))
        if source is None:
            row["source_chunk_ids"] = ""
            counts["unresolved_source"] += 1
            report_rows.append({**row, "confidence": "unresolved_source", "match_score": ""})
            continue

        store = source["get_store"]()
        chunk_ids, score = resolve_chunk_ids(row, store)
        row["source_chunk_ids"] = ";".join(chunk_ids)
        confidence = _confidence_label(score)
        counts[confidence] += 1
        report_rows.append({**row, "confidence": confidence, "match_score": round(score, 3)})

    print(f"{len(rows)} rows processed:")
    for label in ("high", "medium", "low", "unresolved_source"):
        print(f"  {label}: {counts[label]}")

    print("\nRows needing manual review (medium/low confidence or unresolved source):")
    for row in report_rows:
        if row["confidence"] in ("high",):
            continue
        print(
            f"  [{row['confidence']:>17}] {row['query_id']:<14} "
            f"score={row.get('match_score','-'):<6} chunks={row.get('source_chunk_ids','-')}"
        )

    report_fieldnames = fieldnames + ["confidence", "match_score"]
    with REPORT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=report_fieldnames)
        writer.writeheader()
        for row in report_rows:
            writer.writerow(row)
    print(f"\nFull match report written to {REPORT_PATH}")

    if args.apply:
        with GOLDEN_SET_PATH.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"Wrote source_chunk_ids into {GOLDEN_SET_PATH}")
    else:
        print("\nDry run only (no file changed). Re-run with --apply to write source_chunk_ids into the CSV.")


if __name__ == "__main__":
    main()
