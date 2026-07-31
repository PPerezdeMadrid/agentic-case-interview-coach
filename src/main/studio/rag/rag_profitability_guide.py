"""Persistent vector-store RAG over the profitability methodology PDF."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from huggingface_hub.constants import HF_HUB_CACHE
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

MAIN_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = Path(__file__).resolve().parents[3]
PROFITABILITY_GUIDE_PDF_PATH = SRC_ROOT / "database" / "Principles-of-Managerial-Accounting-profitability.pdf"
VECTORSTORE_DIR = MAIN_DIR / "database" / "vectorstore" / "profitability_guide"
RAG_SOURCE_METADATA_PATH = SRC_ROOT / "database" / "profitability_source_navigation.json"

COLLECTION_NAME = "profitability_guide"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_TOP_K = 4

_embeddings_singleton: FastEmbedEmbeddings | None = None
_vectorstore_singleton: Chroma | None = None


def _load_profitability_source_navigation() -> dict[str, str]:
    try:
        payload = json.loads(RAG_SOURCE_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Could not load profitability RAG metadata from {RAG_SOURCE_METADATA_PATH}."
        ) from exc

    guidance = str(payload.get("retrieval_guidance", "")).strip()
    citation_label = str(payload.get("citation_label", "")).strip()
    if not guidance or not citation_label:
        raise RuntimeError(
            f"Profitability RAG metadata in {RAG_SOURCE_METADATA_PATH} is missing "
            "'retrieval_guidance' or 'citation_label'."
        )
    return {"retrieval_guidance": guidance, "citation_label": citation_label}


_PROFITABILITY_SOURCE_NAVIGATION = _load_profitability_source_navigation()
PROFITABILITY_SOURCE_NAVIGATION_GUIDE = _PROFITABILITY_SOURCE_NAVIGATION["retrieval_guidance"]

# Human-readable citation for feedback/prose to name this source by, e.g.
# "Principles of Managerial Accounting by Dr. Patricia Goedl".
PROFITABILITY_CITATION_LABEL = _PROFITABILITY_SOURCE_NAVIGATION["citation_label"]


def get_embeddings() -> FastEmbedEmbeddings:
    global _embeddings_singleton
    if _embeddings_singleton is None:
        # Cap onnxruntime's thread pool to the CPUs actually allocated to this
        # job -- left unset, it sizes itself to the node's full core count and
        # tries to pin threads to cores outside the SLURM cgroup, spamming
        # pthread_setaffinity_np "Invalid argument" errors.
        threads = int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 1))
        # fastembed's own default cache_dir is a system tempdir, which on the
        # HPC cluster is job-scoped and wiped after the job ends -- every job
        # re-downloads the ONNX weights from HuggingFace instead of caching
        # them once. Point it at the same persistent HF cache (respects
        # HF_HOME, already set to /sharedscratch/$USER/huggingface by
        # server.bash) used for the LLM weights, so it downloads once and
        # every later job loads it from disk with no network call.
        _embeddings_singleton = FastEmbedEmbeddings(
            model_name=EMBEDDING_MODEL_NAME, threads=threads, cache_dir=str(HF_HUB_CACHE)
        )
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
            "citation": PROFITABILITY_CITATION_LABEL,
            "page": document.metadata.get("page"),
            "chunk_id": document.id,
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
        citation = chunk.get("citation") or chunk.get("source", "profitability guide")
        lines.append(f"- [{citation}, {page_label}] {chunk.get('content', '')}")
    return "\n".join(lines)


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    vectorstore = build_profitability_guide_vectorstore(force_rebuild=rebuild)
    print(
        f"Profitability guide vector store ready at {VECTORSTORE_DIR} "
        f"({vectorstore._collection.count()} chunks, rebuild={rebuild})."
    )
