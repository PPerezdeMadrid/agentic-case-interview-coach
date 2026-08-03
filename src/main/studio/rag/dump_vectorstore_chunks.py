"""Dump every chunk in the persisted vector stores to CSV for manual review
(used to pick `source_chunk_ids` for the golden RAG eval datasets, see doc/evaluation/RAG-evaluation.md).

Usage:
    python -m src.main.studio.rag.dump_vectorstore_chunks
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from src.main.studio.rag.rag_case_guide import get_case_guide_vectorstore
from src.main.studio.rag.rag_profitability_guide import get_profitability_guide_vectorstore

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "database" / "rag_evaluation"


def _chunk_sort_key(chunk_id: str) -> int:
    match = re.search(r"chunk_(\d+)$", chunk_id)
    return int(match.group(1)) if match else 0


def _dump_store(store, output_path: Path) -> int:
    data = store.get(include=["documents", "metadatas"])
    rows = list(zip(data["ids"], data["documents"], data["metadatas"]))
    rows.sort(key=lambda row: _chunk_sort_key(row[0]))

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["chunk_id", "page", "content"])
        for chunk_id, content, metadata in rows:
            page = metadata.get("page") if metadata else None
            page_label = page + 1 if isinstance(page, int) else ""
            writer.writerow([chunk_id, page_label, content.strip()])

    return len(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    case_guide_store = get_case_guide_vectorstore()
    case_guide_out = OUTPUT_DIR / "case_guide_chunks_dump.csv"
    n_case = _dump_store(case_guide_store, case_guide_out)
    print(f"Wrote {n_case} case-guide chunks to {case_guide_out}")

    profitability_store = get_profitability_guide_vectorstore()
    profitability_out = OUTPUT_DIR / "profitability_chunks_dump.csv"
    n_profitability = _dump_store(profitability_store, profitability_out)
    print(f"Wrote {n_profitability} profitability chunks to {profitability_out}")


if __name__ == "__main__":
    main()
