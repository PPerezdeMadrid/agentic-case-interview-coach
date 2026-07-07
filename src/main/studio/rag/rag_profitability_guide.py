"""Persistent vector-store RAG over the profitability methodology PDF."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

MAIN_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = Path(__file__).resolve().parents[3]
PROFITABILITY_GUIDE_PDF_PATH = SRC_ROOT / "database" / "Principles-of-Managerial-Accounting-profitability.pdf"
VECTORSTORE_DIR = MAIN_DIR / "database" / "vectorstore" / "profitability_guide"
RAG_SOURCE_METADATA_PATH = SRC_ROOT / "database" / "rag_sources" / "profitability_source_navigation.json"

COLLECTION_NAME = "profitability_guide"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_TOP_K = 4

_embeddings_singleton: FastEmbedEmbeddings | None = None
_vectorstore_singleton: Chroma | None = None


def _load_profitability_source_navigation_guide() -> str:
    try:
        payload = json.loads(RAG_SOURCE_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Could not load profitability RAG metadata from {RAG_SOURCE_METADATA_PATH}."
        ) from exc

    guidance = str(payload.get("retrieval_guidance", "")).strip()
    if not guidance:
        raise RuntimeError(
            f"Profitability RAG metadata in {RAG_SOURCE_METADATA_PATH} is missing 'retrieval_guidance'."
        )
    return guidance


PROFITABILITY_SOURCE_NAVIGATION_GUIDE = _load_profitability_source_navigation_guide()


def get_embeddings() -> FastEmbedEmbeddings:
    global _embeddings_singleton
    if _embeddings_singleton is None:
        _embeddings_singleton = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    return _embeddings_singleton


def _load_and_split_profitability_guide(
    pdf_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Profitability guide PDF not found: {pdf_path}")

    pages = PyPDFLoader(str(pdf_path)).load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(pages)


def build_profitability_guide_vectorstore(
    *,
    pdf_path: Path = PROFITABILITY_GUIDE_PDF_PATH,
    persist_dir: Path = VECTORSTORE_DIR,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    force_rebuild: bool = False,
) -> Chroma:
    embeddings = get_embeddings()
    persist_dir.mkdir(parents=True, exist_ok=True)

    if force_rebuild:
        import shutil

        shutil.rmtree(persist_dir, ignore_errors=True)
        persist_dir.mkdir(parents=True, exist_ok=True)

    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )

    if not force_rebuild and store._collection.count() > 0:
        return store

    documents = _load_and_split_profitability_guide(pdf_path, chunk_size, chunk_overlap)
    if not documents:
        raise RuntimeError(f"No extractable text found in {pdf_path}")

    ids = [f"{pdf_path.stem}::chunk_{index + 1}" for index in range(len(documents))]
    store.add_documents(documents, ids=ids)
    return store


def get_profitability_guide_vectorstore(force_rebuild: bool = False) -> Chroma:
    global _vectorstore_singleton
    if _vectorstore_singleton is None or force_rebuild:
        _vectorstore_singleton = build_profitability_guide_vectorstore(force_rebuild=force_rebuild)
    return _vectorstore_singleton


def retrieve_profitability_guide_context(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    store = get_profitability_guide_vectorstore()
    results = store.similarity_search(query, k=top_k)
    return [
        {
            "content": document.page_content.strip(),
            "source": PROFITABILITY_GUIDE_PDF_PATH.name,
            "page": document.metadata.get("page"),
        }
        for document in results
        if document.page_content.strip()
    ]


def format_profitability_guide_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "None."

    lines = []
    for chunk in chunks:
        page = chunk.get("page")
        page_label = f"p.{int(page) + 1}" if isinstance(page, int) else "p.?"
        lines.append(f"- [{chunk.get('source', 'profitability guide')} {page_label}] {chunk.get('content', '')}")
    return "\n".join(lines)


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

    sections = [
        "Consulting profitability case methodology grounded in managerial accounting.",
        f"Evaluation target: {evaluation_target.strip()}" if evaluation_target.strip() else "",
        f"Case prompt: {case_prompt.strip()}" if case_prompt.strip() else "",
        f"Recent transcript:\n{recent_transcript}" if recent_transcript else "",
        f"Latest candidate recommendation: {candidate_final_recommendation}" if candidate_final_recommendation else "",
        (
            "Judge focus areas or coaching targets: " + "; ".join(focus_areas or [])
            if focus_areas
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


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    vectorstore = build_profitability_guide_vectorstore(force_rebuild=rebuild)
    print(
        f"Profitability guide vector store ready at {VECTORSTORE_DIR} "
        f"({vectorstore._collection.count()} chunks, rebuild={rebuild})."
    )
