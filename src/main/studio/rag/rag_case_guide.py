"""Persistent vector-store RAG over the Consulting Case Interview Guide PDF.

Unlike the in-memory TF-IDF retrieval in `knowledge_base.py` (rebuilt from
scratch on every run from small per-case sources), this module embeds the
guide PDF once with a local embedding model and persists the index to disk
under `database/vectorstore/`, so subsequent runs just load it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

SRC_ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = SRC_ROOT / "database"
CASE_GUIDE_PDF_PATH = DATABASE_DIR / "ConsultingCaseGuide-PPML.pdf"
VECTORSTORE_DIR = DATABASE_DIR / "vectorstore" / "consulting_case_guide"

COLLECTION_NAME = "consulting_case_guide"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_TOP_K = 4

_embeddings_singleton: FastEmbedEmbeddings | None = None
_vectorstore_singleton: Chroma | None = None


def get_embeddings() -> FastEmbedEmbeddings:
    """Return a cached local embedding model (no API key / network calls per query)."""
    global _embeddings_singleton
    if _embeddings_singleton is None:
        _embeddings_singleton = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    return _embeddings_singleton


def _load_and_split_case_guide(
    pdf_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Case guide PDF not found: {pdf_path}")

    pages = PyPDFLoader(str(pdf_path)).load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(pages)


def build_case_guide_vectorstore(
    *,
    pdf_path: Path = CASE_GUIDE_PDF_PATH,
    persist_dir: Path = VECTORSTORE_DIR,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    force_rebuild: bool = False,
) -> Chroma:
    """Ingest the case-guide PDF into a persisted Chroma vector store.

    If a populated store already exists at `persist_dir` and `force_rebuild`
    is False, it is loaded as-is instead of re-embedding the PDF.
    """
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

    documents = _load_and_split_case_guide(pdf_path, chunk_size, chunk_overlap)
    if not documents:
        raise RuntimeError(f"No extractable text found in {pdf_path}")

    ids = [f"{pdf_path.stem}::chunk_{index + 1}" for index in range(len(documents))]
    store.add_documents(documents, ids=ids)
    return store


def get_case_guide_vectorstore(force_rebuild: bool = False) -> Chroma:
    """Return the cached, process-wide case-guide vector store, building it on first use."""
    global _vectorstore_singleton
    if _vectorstore_singleton is None or force_rebuild:
        _vectorstore_singleton = build_case_guide_vectorstore(force_rebuild=force_rebuild)
    return _vectorstore_singleton


def retrieve_case_guide_context(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Return the top-k case-guide chunks relevant to `query`."""
    if not query.strip():
        return []

    store = get_case_guide_vectorstore()
    results = store.similarity_search(query, k=top_k)

    return [
        {
            "content": document.page_content.strip(),
            "source": CASE_GUIDE_PDF_PATH.name,
            "page": document.metadata.get("page"),
        }
        for document in results
        if document.page_content.strip()
    ]


def format_case_guide_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "None."

    lines = []
    for chunk in chunks:
        page = chunk.get("page")
        page_label = f"p.{int(page) + 1}" if isinstance(page, int) else "p.?"
        lines.append(f"- [{chunk.get('source', 'case guide')} {page_label}] {chunk.get('content', '')}")
    return "\n".join(lines)


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    vectorstore = build_case_guide_vectorstore(force_rebuild=rebuild)
    print(
        f"Case guide vector store ready at {VECTORSTORE_DIR} "
        f"({vectorstore._collection.count()} chunks, rebuild={rebuild})."
    )
