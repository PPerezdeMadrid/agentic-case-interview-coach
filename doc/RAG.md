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
- builds retrieval queries with a short natural-language description of what the profitability source covers, loaded from `src/database/profitability_source_navigation.json`

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

## Query design: each node scouts for itself

There is no shared "RAG node" that writes retrieval queries on behalf of the rest of the
graph. Instead, every node that can use RAG (`judge_node`, `eval_case_performance_node`,
`eval_dialog_quality_node`, `give_feedback_node` in `agentic.py`; `baseline_node` and
`evaluate_case_performance` in `baseline.py`) makes its own scouting decision, in its own
voice, before doing its main task:

1. The node builds the same situation context (transcript, case prompt, rubric, etc.) it
   would use for its main call anyway.
2. It sends that situation to its own role LLM (judge scouts with `judge_llm`, feedback
   scouts with `feedback_llm`, baseline scouts with its single model), under its own
   system prompt (`JUDGE_GRAPH_SYSTEM_PROMPT`, `CASE_EVAL_SYSTEM_PROMPT`, etc.), plus a
   short description of the RAG source(s) it has access to -- `CASE_GUIDE_SOURCE_DESCRIPTION`
   and/or `PROFITABILITY_SOURCE_NAVIGATION_GUIDE` -- and an instruction to decide whether it
   needs an excerpt right now and, if so, write one short question for it.
3. An empty query means "I don't need this source this round" and retrieval is skipped
   entirely -- RAG is conditional per turn, not a fixed step every node always runs.
4. A non-empty query is embedded and searched; the retrieved excerpts are then injected
   into the node's main call, same as before.

`eval_case_performance_node` has access to both sources and makes one combined scouting
decision (`CaseAndProfitabilityRagScoutingDecision`) rather than two separate calls. Every
other RAG-capable node only has case-guide access and uses the single-source
`CaseGuideRagScoutingDecision` schema via the shared `_scout_case_guide` helper in
`node.py` -- that helper is plumbing only (call the LLM, parse the field, retrieve if
non-empty); the prompt and situation it's given always come from the calling node itself.

The scouting LLM is always the node's own role LLM (judge scouts with `judge_llm`, feedback
with `feedback_llm`, baseline with its single model) -- there is no separate model or
override for scouting.

The baseline graph's case-guide retrieval (`get_baseline_case_guide_context`) stays
intentionally simple: it uses the case prompt itself as the query, with no LLM decision at
all, to keep that arm of the agentic-vs-baseline comparison "dumb" by design. Baseline's
profitability retrieval does go through the scouting pattern above.
