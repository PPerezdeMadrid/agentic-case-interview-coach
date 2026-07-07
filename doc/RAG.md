# RAG Design

## Overview

The project now has two retrieval paths under `src/main/studio/rag/`:

- a persistent vector-store retrieval layer for profitability methodology
- a persistent vector-store RAG layer for `ConsultingCaseGuide-PPML.pdf`

This split exists because the two knowledge sources play different roles:

- case-specific profitability methodology can use a dedicated persisted guide index
- the shared consulting case guide benefits from persistent embeddings and semantic retrieval

## Code layout

- `src/main/studio/rag/rag_profitability_guide.py`: persistent Chroma-based retrieval for profitability methodology
- `src/main/studio/rag/rag_case_guide.py`: persistent Chroma-based retrieval for the guide PDF
- `src/main/studio/rag/case_guide_context.py`: logic for turning graph state into a natural-language retrieval query for the guide PDF

## Profitability retrieval

The profitability layer:

- loads `src/database/Principles-of-Managerial-Accounting-profitability.pdf`
- splits it into chunks
- embeds it with `FastEmbedEmbeddings`
- stores vectors in Chroma under `src/database/vectorstore/profitability_guide/`
- builds retrieval queries with a short natural-language description of what the profitability source covers, loaded from `src/database/rag_sources/profitability_source_navigation.json`

It is used where the graph needs methodology grounded in case-specific support material.

Current source note:

- the profitability RAG may use `src/database/Principles-of-Managerial-Accounting-profitability.pdf`
- this source is documented as licensed under `CC BY 4.0`
- in practice, only the textbook text should be indexed; third-party or separately licensed embedded assets should be excluded where relevant

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

The guide-query construction logic lives in `rag/case_guide_context.py`.
