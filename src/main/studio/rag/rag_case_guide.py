"""Persistent vector-store RAG over the Consulting Case Interview Guide PDF.

This module embeds the guide PDF once with a local embedding model and
persists the index to disk under `database/vectorstore/`, so subsequent runs
just load it.
"""
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
CASE_GUIDE_PDF_PATH = SRC_ROOT / "database" / "ConsultingCaseGuide-PPML.pdf"
VECTORSTORE_DIR = MAIN_DIR / "database" / "vectorstore" / "consulting_case_guide"
RAG_SOURCE_METADATA_PATH = SRC_ROOT / "database" / "case_guide_source_navigation.json"

COLLECTION_NAME = "consulting_case_guide"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_TOP_K = 4

_embeddings_singleton: FastEmbedEmbeddings | None = None
_vectorstore_singleton: Chroma | None = None


def _load_case_guide_source_navigation() -> dict[str, str]:
    try:
        payload = json.loads(RAG_SOURCE_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Could not load case guide RAG metadata from {RAG_SOURCE_METADATA_PATH}."
        ) from exc

    guidance = str(payload.get("retrieval_guidance", "")).strip()
    citation_label = str(payload.get("citation_label", "")).strip()
    if not guidance or not citation_label:
        raise RuntimeError(
            f"Case guide RAG metadata in {RAG_SOURCE_METADATA_PATH} is missing "
            "'retrieval_guidance' or 'citation_label'."
        )
    return {"retrieval_guidance": guidance, "citation_label": citation_label}


_CASE_GUIDE_SOURCE_NAVIGATION = _load_case_guide_source_navigation()

# Short description each node's own prompt can quote when deciding whether it needs
# to consult this source -- not a query, just "what's in here".
CASE_GUIDE_SOURCE_DESCRIPTION = _CASE_GUIDE_SOURCE_NAVIGATION["retrieval_guidance"]

# Human-readable citation for feedback/prose to name this source by, e.g.
# "Consulting Case Interview Guide by Paloma Pérez de Madrid".
CASE_GUIDE_CITATION_LABEL = _CASE_GUIDE_SOURCE_NAVIGATION["citation_label"]


def get_embeddings() -> FastEmbedEmbeddings:
    """Return a cached local embedding model"""
    # no API key / network calls per query
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
    """Ingest the case-guide PDF into a persisted Chroma vector store"""
    # If a populated store already exists at `persist_dir` and `force_rebuild`
    # is False, it is loaded as-is instead of re-embedding the PDF.
    embeddings = get_embeddings()
    persist_dir.mkdir(parents=True, exist_ok=True)

    if force_rebuild:
        import shutil

        shutil.rmtree(persist_dir, ignore_errors=True) # Delete the existing vector store if force_rebuild is True
        persist_dir.mkdir(parents=True, exist_ok=True) # Create the directory again after deletion

    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )

    if not force_rebuild and store._collection.count() > 0: # it already has data, so we can skip rebuilding
        return store

    documents = _load_and_split_case_guide(pdf_path, chunk_size, chunk_overlap)
    if not documents:
        raise RuntimeError(f"No extractable text found in {pdf_path}")

    # Assign unique IDs to each chunk for persistence
    ids = [f"{pdf_path.stem}::chunk_{index + 1}" for index in range(len(documents))]
    store.add_documents(documents, ids=ids)
    return store


def get_case_guide_vectorstore(force_rebuild: bool = False) -> Chroma:
    """Return the cached, process-wide case-guide vector store, building it on first use"""
    global _vectorstore_singleton
    if _vectorstore_singleton is None or force_rebuild:
        _vectorstore_singleton = build_case_guide_vectorstore(force_rebuild=force_rebuild)
    return _vectorstore_singleton


def retrieve_case_guide_context(query: str, *,top_k: int = DEFAULT_TOP_K,) -> list[dict[str, Any]]:
    """Return the top-k case-guide chunks relevant to `query`"""
    if not query.strip():
        return []

    print(f"RAG being used, consulting {CASE_GUIDE_PDF_PATH.name} file")
    store = get_case_guide_vectorstore()
    results = store.similarity_search(query, k=top_k)

    return [
        {
            "content": document.page_content.strip(),
            "source": CASE_GUIDE_PDF_PATH.name,
            "citation": CASE_GUIDE_CITATION_LABEL,
            "page": document.metadata.get("page"),
            "chunk_id": document.id,
        }
        for document in results
        if document.page_content.strip()
    ]


def format_case_guide_context(chunks: list[dict[str, Any]]) -> str:
    # Just a simple bullet list of the retrieved chunks, with page numbers and a citeable source label
    if not chunks:
        return "None."

    lines = []
    for chunk in chunks:
        page = chunk.get("page")
        page_label = f"p.{int(page) + 1}" if isinstance(page, int) else "p.?"
        citation = chunk.get("citation") or chunk.get("source", "case guide")
        lines.append(f"- [{citation}, {page_label}] {chunk.get('content', '')}")
    return "\n".join(lines)


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    vectorstore = build_case_guide_vectorstore(force_rebuild=rebuild)
    print(
        f"Case guide vector store ready at {VECTORSTORE_DIR} "
        f"({vectorstore._collection.count()} chunks, rebuild={rebuild})."
    )
