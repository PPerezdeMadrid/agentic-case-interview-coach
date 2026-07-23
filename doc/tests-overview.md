# Test Overview

This document summarizes how the project's tests are organized and what is evaluated in each file and section. The idea is not to describe every individual test, but to make the general structure clear so the suite remains easy to maintain even as cases are added or removed.

## General structure

Tests are currently separated by functional area:

- `src/main/studio/tests/test_agentic_graph.py`
- `src/main/studio/tests/test_api_connection.py`
- `src/main/web/tests/test_workbench.py`

The separation follows the project's architecture:

- `studio` covers the conversational graph logic and its variants, plus connectivity to the different LLMs it uses.
- `web` covers the dashboard layer, metrics, storage, and HTTP endpoints.

## `src/main/studio/tests/test_agentic_graph.py`

This file validates the behavior of the interview system in `agentic` mode and in `baseline` mode.

### File helpers and fixtures

The initial part of the file builds a minimal synthetic case to test the flow without depending on real external data:

- `make_runtime_case()`: creates the test case's blocks.
- `make_runtime_bundle()`: assembles scenario, case, and rubric.
- `make_state()`: generates a useful initial state for invoking specific graph nodes.

These helpers make it possible to test individual nodes and full runs with controlled, easy-to-reason-about data.

### `AgenticGraphTests` section

This section covers the behavior of the main `agentic` graph.

The coverage blocks here focus on:

- Construction of the graph's initial state.
- Interviewer node behavior on the first turn.
- Correct transcript visibility for the candidate.
- Use of the judge's `focus_areas` to guide the next turn.
- Judge round limit and forced evaluation.
- Context reconstruction when `case_prompt` is missing.
- End-to-end execution of the full graph, including transcript, final evaluation, and persistence to SQLite.

This section uses `Mock` and `patch` to isolate the LLM, context retrieval, and persistence, so that the graph logic can be verified without depending on external services.

### `BaselineGraphTests` section

This section covers the `baseline` variant, which shares part of the system logic but with a simpler flow.

It mainly validates:

- Injection of retrieved context into the baseline interviewer prompt.
- Storage of retrieved context within the state.
- Query reconstruction when `case_prompt` does not exist.

In summary, this part ensures the baseline keeps its own coverage and does not implicitly depend on the agentic graph's coverage.

## `src/main/studio/tests/test_api_connection.py`

This file does not test business logic: it is a connectivity smoke test that performs a real ping to each configured LLM endpoint -- the four OpenRouter clients actually wired into the agentic graph's roles (interviewer, candidate, judge, feedback), plus the two clients kept only as manual fallbacks (`openai_llm_server`, direct OpenAI; `lmstudio_llm_server`, local LM Studio) -- before the graph needs them.

The `APIConnectionTests` class is meant to be run manually before `make langgraph`, so that a downed server or a misconfigured API key is detected immediately instead of midway through a run inside LangGraph Studio. The `lmstudio_llm_server` check is skipped unless `LMSTUDIO_RUN_LOCAL_TESTS=1` is set, since it isn't wired to any active role and requires the LM Studio app running locally.

## `src/main/web/tests/test_workbench.py`

This file covers the web layer and the storage associated with the evaluation dashboard.

### File helpers and fixtures

The initial part defines utilities for creating a temporary SQLite database and populating it with a sample run:

- `create_runs_table(db_path)`: creates the dashboard's necessary tables.
- `insert_sample_run(db_path)`: inserts a synthetic run with transcript, scores, and traces.

The purpose of these helpers is to enable deterministic tests for run loading, metrics, traces, and HTTP APIs.

### `DashboardStoreTests` section

This section tests the data access and metrics calculation layer in `dashboard_store.py`.

The topics it covers are:

- Calculation of error metrics between expected, model, and human scores.
- Behavior of `exact_match_rate` in different scenarios.
- Handling of non-comparable pairs or non-numeric scores.
- Construction of a run's aggregated payload with expected scores, model scores, human scores, and metrics.
- Construction of the traces payload for the run's timeline view.

### `JudgeEvalStoreTests` section

This section tests `judge_eval.py`, the layer that lists and loads the judge's golden set results (e.g. `judge_golden_set_worldcup_results.json`) for the **Agents > Judge** page of the workbench.

It covers:

- Listing available golden sets and loading a cached result, including making the original `judge_input` accessible alongside the verdict.
- That requesting a golden set with no cached results raises `FileNotFoundError` instead of returning partial or fabricated data.

### `WorkbenchAppTests` section

This section tests the Flask HTTP layer using `test_client()`.

The coverage blocks here include:

- JSON response for run detail.
- Save and read flow for human evaluation via the API.
- Human evaluation endpoint contract when no prior evaluation exists.
- Response of the traces view or endpoint.
- Invalid payload validations for the API.

These tests do not focus on detailed HTML, but on verifying that the main endpoints respond with the expected structure and are correctly connected to `dashboard_store`.
