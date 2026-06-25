from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter


TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _read_knowledge_source(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")

    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=True, indent=2)

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF knowledge sources require the optional 'pypdf' dependency."
            ) from exc

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages).strip()

    raise RuntimeError(f"Unsupported knowledge source format: {path.suffix or '<no extension>'}")


def _resolve_knowledge_sources(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sources = case_data.get("knowledge_sources", [])
    if not isinstance(raw_sources, list):
        return []
    return [source for source in raw_sources if isinstance(source, dict)]


def _build_source_documents(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    source_path = Path(str(case_data.get("source_path", "")).strip()) if case_data.get("source_path") else None
    documents: list[dict[str, Any]] = []

    for source in _resolve_knowledge_sources(case_data):
        raw_path = str(source.get("path", "")).strip()
        if not raw_path:
            continue

        path = Path(raw_path)
        if not path.is_absolute() and source_path is not None:
            path = (source_path.parent / path).resolve()

        if not path.exists():
            continue

        try:
            content = _read_knowledge_source(path).strip()
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
            continue

        if not content:
            continue

        documents.append(
            {
                "source_id": str(source.get("source_id", path.stem)).strip() or path.stem,
                "source_name": str(source.get("title", path.name)).strip() or path.name,
                "source_kind": str(source.get("source_kind", "external_document")).strip() or "external_document",
                "visibility": str(source.get("visibility", "interviewer_only")).strip() or "interviewer_only",
                "content": content,
                "metadata": {
                    "path": str(path),
                    "format": path.suffix.lower().lstrip("."),
                },
            }
        )

    return documents


def _build_block_documents(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    case_content = case_data.get("case_content", [])
    if not isinstance(case_content, list):
        return []

    documents: list[dict[str, Any]] = []
    for block in case_content:
        if not isinstance(block, dict):
            continue

        content = str(block.get("content", "")).strip()
        if not content:
            continue

        block_id = str(block.get("block_id", "")).strip() or "unknown_block"
        title = str(block.get("title", "")).strip() or block_id
        visibility = "candidate_visible" if block.get("visible_to_candidate") is True else "interviewer_only"

        documents.append(
            {
                "source_id": block_id,
                "source_name": title,
                "source_kind": "case_block",
                "visibility": visibility,
                "content": content,
                "metadata": {
                    "block_id": block_id,
                    "block_type": str(block.get("block_type", "")).strip(),
                    "source_page": block.get("source_page"),
                },
            }
        )

    return documents


def build_case_knowledge_base(
    case_data: dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, Any]:
    documents = _build_block_documents(case_data) + _build_source_documents(case_data)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for document in documents:
        parts = splitter.split_text(document["content"])
        if not parts:
            parts = [document["content"]]

        for index, part in enumerate(parts):
            text = part.strip()
            if not text:
                continue

            tokens = _tokenize(text)
            if not tokens:
                continue

            term_counts: dict[str, int] = {}
            for token in tokens:
                term_counts[token] = term_counts.get(token, 0) + 1

            chunks.append(
                {
                    "chunk_id": f"{document['source_id']}::chunk_{index + 1}",
                    "source_id": document["source_id"],
                    "source_name": document["source_name"],
                    "source_kind": document["source_kind"],
                    "visibility": document["visibility"],
                    "content": text,
                    "term_counts": term_counts,
                    "token_count": len(tokens),
                    "metadata": document["metadata"],
                }
            )

    document_frequency: dict[str, int] = {}
    for chunk in chunks:
        for term in chunk["term_counts"]:
            document_frequency[term] = document_frequency.get(term, 0) + 1

    return {
        "chunks": chunks,
        "document_frequency": document_frequency,
        "chunk_count": len(chunks),
        "source_count": len(documents),
        "config": {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
    }


def retrieve_knowledge_context(
    knowledge_base: dict[str, Any],
    query: str,
    *,
    top_k: int = 3,
    visibility: str = "all",
) -> list[dict[str, Any]]:
    chunks = knowledge_base.get("chunks", [])
    if not isinstance(chunks, list) or not query.strip():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    total_chunks = max(int(knowledge_base.get("chunk_count", len(chunks))), 1)
    document_frequency = knowledge_base.get("document_frequency", {})
    if not isinstance(document_frequency, dict):
        document_frequency = {}

    scored_chunks = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue

        chunk_visibility = str(chunk.get("visibility", "all")).strip()
        if visibility != "all" and chunk_visibility != visibility:
            continue

        term_counts = chunk.get("term_counts", {})
        if not isinstance(term_counts, dict):
            continue

        score = 0.0
        overlap = 0
        for token in query_tokens:
            tf = int(term_counts.get(token, 0))
            if tf <= 0:
                continue
            overlap += 1
            df = int(document_frequency.get(token, 1))
            idf = math.log(1 + (total_chunks / max(df, 1)))
            score += tf * idf

        content = str(chunk.get("content", ""))
        normalized_query = query.strip().lower()
        if normalized_query and normalized_query in content.lower():
            score += 2.0

        if score <= 0:
            continue

        scored_chunks.append((score + (overlap * 0.2), chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


def format_retrieved_chunks(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "None."

    lines = []
    for chunk in chunks:
        source_name = str(chunk.get("source_name", "Unknown source")).strip() or "Unknown source"
        source_kind = str(chunk.get("source_kind", "unknown")).strip() or "unknown"
        visibility = str(chunk.get("visibility", "unknown")).strip() or "unknown"
        content = str(chunk.get("content", "")).strip()
        lines.append(f"- [{source_kind} | {visibility}] {source_name}: {content}")
    return "\n".join(lines)


def build_retrieval_query(
    case_prompt: str,
    transcript: list[str],
    focus_areas: list[str] | None = None,
) -> str:
    relevant_lines = [line.strip() for line in transcript[-6:] if isinstance(line, str) and line.strip()]
    focus_area_text = ", ".join(focus_areas or [])
    sections = [
        case_prompt.strip(),
        "\n".join(relevant_lines),
        focus_area_text,
    ]
    return "\n".join(section for section in sections if section)
