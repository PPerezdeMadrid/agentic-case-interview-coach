# RAG Knowledge Layer for `main02`

The `main02` flow now supports an optional retrieval layer on top of the existing case JSON structure.

## What it does

- Builds a chunked knowledge base from the existing `case_content` blocks.
- Optionally loads extra knowledge sources declared in each case JSON.
- Retrieves relevant chunks for the interviewer, judge, and evaluators.
- Keeps the existing block-based behavior as the default path.

## Why this design

- Works today with one source.
- Scales later to multiple PDFs or notes without changing the graph design.
- Lets you tune retrieval separately from prompting and case authoring.

## Case JSON extension

You can add a `knowledge_sources` array to any case file:

```json
{
  "knowledge_sources": [
    {
      "source_id": "verdex_casebook_pdf",
      "title": "Verdex PDF",
      "path": "../knowledge/verdex.pdf",
      "source_kind": "pdf_casebook",
      "visibility": "interviewer_only"
    }
  ]
}
```

## Supported source formats

- `.pdf`
- `.md`
- `.txt`
- `.json`

## Visibility values

- `candidate_visible`
- `interviewer_only`

Use `candidate_visible` only for source material that is safe to reveal to the candidate. Use `interviewer_only` for solutions, guidance, exhibits not yet shown, or evaluator notes.

## Current retriever

The current retriever is lexical and local:

- no external vector database
- no embedding dependency
- deterministic and easy to debug

This is intentional for the MVP. The integration point is `knowledge_base.py`, so embeddings can be added later without changing the graph nodes.

## Recommended next upgrade

If you later want a stronger RAG system:

1. Keep `knowledge_sources` as the source registry.
2. Replace lexical scoring with embeddings plus reranking.
3. Persist the index so PDFs are chunked only once.
4. Add retrieval diagnostics to compare prompts, chunks, and final reveal decisions.
