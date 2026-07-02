# RAG Design

## Overview

The system now has a small RAG layer for general profitability-case knowledge.

This RAG is not used by the whole graph. It is only used in:

- `baseline`
- `eval_case_performance`

The interviewer node and the judge node do not use this retrieval layer.


## Purpose

The goal is to ground the evaluation in external material about how to approach profitability cases.

This knowledge is different from the case data.

- `case_data` contains the facts of the specific case
- the RAG PDF contains general methodology for solving profitability cases

This separation matters because the case facts and the evaluation guidance do not play the same role.


## Current design

The RAG layer is local and simple.

- one knowledge base for profitability methodology
- built from one or more declared sources
- chunked locally
- retrieved with lexical matching
- no external vector database
- no extra deployment

The retrieval flow is:

1. load the profitability knowledge source
2. extract text
3. split into chunks
4. build a local index
5. retrieve the most relevant chunks for the evaluation step


## Where it is used

### `baseline`

The baseline can retrieve methodology context during the interview flow.

This gives the single-agent system access to external guidance when it asks questions or decides how to evaluate the candidate.

### `eval_case_performance`

This is the main place where RAG matters.

The node retrieves chunks from the profitability knowledge base and uses them together with:

- the transcript
- the case guidance
- the case data
- the expected recommendation
- the rubric

The objective is to assess whether the candidate approached the case in a sensible profitability-case way.


## Query design

The retrieval query is not based on the PDF title or on a fixed keyword list.

It is built from:

- the case prompt
- the recent transcript
- the evaluation target
- the current focus areas when available

This keeps the retrieval tied to the actual interview.


## Graph note

There is a commented placeholder for a future `retrieve_info` node in the LangGraph file.

It is not active yet.

For now, retrieval is called directly from the nodes that need it.


## When adding a PDF

When the profitability PDF is ready, it has to be declared in the case JSON.

The expected field is:

```json
{
  "profitability_knowledge_sources": [
    {
      "source_id": "profitability_pdf",
      "title": "Profitability Case Guide",
      "path": "../knowledge/profitability_guide.pdf",
      "source_kind": "profitability_methodology"
    }
  ]
}
```

### What to do

1. Add the PDF file to the project.
2. Add its path in `profitability_knowledge_sources`.
3. Keep the path relative to the case file or use an absolute path.
4. Make sure `pypdf` is available, because PDF reading depends on it.
5. Run the flow and check that retrieved context is not empty.

### Supported formats

The loader also supports:

- `.pdf`
- `.md`
- `.txt`
- `.json`

So if the PDF is messy, the same RAG layer can also work with a cleaned markdown or text file.
