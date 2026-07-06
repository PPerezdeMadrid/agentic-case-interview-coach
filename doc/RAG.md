# RAG Design

## Overview

The project now has two retrieval paths under `src/main/studio/rag/`:

- a local lexical retrieval layer for profitability methodology
- a persistent vector-store RAG layer for `ConsultingCaseGuide-PPML.pdf`

This split exists because the two knowledge sources play different roles:

- case-specific profitability methodology can stay lightweight and local
- the shared consulting case guide benefits from persistent embeddings and semantic retrieval

## Code layout

- `src/main/studio/rag/knowledge_base.py`: lexical chunk-based retrieval for case-declared sources
- `src/main/studio/rag/rag_case_guide.py`: persistent Chroma-based retrieval for the guide PDF
- `src/main/studio/rag/case_guide_context.py`: logic for mapping graph state to PDF sections and retrieval queries

Compatibility wrappers still exist in `src/main/studio/`, but they only reexport from `rag/`.

## Profitability retrieval

The profitability layer:

- reads sources declared in case JSON
- supports `.pdf`, `.md`, `.txt`, and `.json`
- chunks content locally
- scores chunks lexically
- rebuilds in memory on each run

It is used where the graph needs methodology grounded in case-specific support material.

## Guide PDF retrieval

The guide layer:

- loads `src/database/ConsultingCaseGuide-PPML.pdf`
- splits it into chunks
- embeds it with `FastEmbedEmbeddings`
- stores vectors in Chroma under `src/database/vectorstore/consulting_case_guide/`
- reuses the stored index across runs

This layer is used to inject broader consulting-case methodology into evaluation and feedback prompts.

## Graph usage

`agentic.py` uses:

- profitability retrieval in `eval_case_performance_node`
- guide PDF retrieval in `judge_node`, `eval_case_performance_node`, `eval_dialog_quality_node`, and `give_feedback_node`

`baseline.py` also uses both retrieval paths, but with simpler guide-query logic.

## Query design

For the guide PDF, retrieval is driven by:

- the case prompt
- the active graph node
- `focus_areas`
- the latest candidate turn when available

The section-routing logic lives in `rag/case_guide_context.py`.

## Related doc

Detailed notes for the guide PDF implementation and the `rag/` refactor are in `../RAG_GUIDE_PDF.md`.
