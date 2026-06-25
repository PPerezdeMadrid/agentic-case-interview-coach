# Scenario, Case, and Rubric Integration Plan

## Current State

The repository already has three distinct data layers:

1. `scenarios/`
   Synthetic candidate scenarios with:
   - `case_id`
   - candidate performance profile
   - behavior rules
   - answer style
   - ground-truth expected scores and feedback

2. `database/*cases*/`
   Case content with:
   - candidate-visible prompt blocks
   - interviewer-only guidance
   - expected analysis / hidden solution content
   - final recommendation prompts

3. `database/Rubric/rubric.json`
   Shared evaluation rubric for the judge.

The main runtime in `src/main/studio/agentic_mvp.py` is still mostly generic:
   - interviewer uses generic prompts
   - candidate uses a generic candidate prompt
   - judge uses a generic rubric prompt
   - case/scenario/rubric files are not yet injected into runtime state


## Recommended Canonical Model

Keep the three layers separate and linked by IDs.

### 1. Case

Purpose:
- Source of truth for the business case
- Drives interviewer behavior
- Provides hidden expected reasoning for judge

Recommended ownership:
- `database/harvard_cases/*.json`
- `database/duke_cases/*.json`
- `database/agsm_cases/*.json`

Recommended semantics:
- candidate-visible prompt
- hidden interviewer guidance
- hidden expected analysis
- hidden solution / recommendation logic
- optional staged data reveals


### 2. Scenario

Purpose:
- Defines how the candidate behaves on a given case
- Defines expected evaluation outcome for testing

Recommended ownership:
- `scenarios/*.json`

Recommended semantics:
- references one `case_id`
- references one `rubric_id`
- defines `candidate_profile`
- defines `ground_truth`
- defines optional simulation settings


### 3. Rubric

Purpose:
- Shared evaluation policy for the judge
- Reused across all scenarios

Recommended ownership:
- `database/Rubric/rubric.json`

Recommended semantics:
- scoring dimensions
- scale labels
- scoring criteria per dimension


## Target Runtime Flow

At runtime:

1. Load one `scenario`
2. Resolve the referenced `case`
3. Load the referenced `rubric`
4. Inject each artifact into graph state
5. Route each agent to the subset it should see

Visibility model:

- Candidate sees:
  - transcript
  - candidate-visible case blocks only
  - scenario candidate profile

- Interviewer sees:
  - transcript
  - full case
  - judge guidance
  - revealed block history

- Judge sees:
  - full transcript
  - full rubric
  - hidden expected analysis / solution blocks
  - scenario ground truth


## Recommended File-Level Responsibilities

### `scenarios/*.json`

Keep the current structure, but add:

```json
{
  "rubric_id": "consulting_case_default_v1",
  "simulation_contract": {
    "candidate_can_see_hidden_case_blocks": false,
    "judge_uses_ground_truth": true,
    "interviewer_mode": "case_driven",
    "max_judge_rounds": 2
  }
}
```

Reason:
- keeps candidate behavior and expected outcome with the scenario
- avoids duplicating rubric content
- makes runtime behavior explicit


### `database/*cases*/<case>.json`

Current `block_type` is useful but should become more operational.

Recommended normalized block types:
- `candidate_prompt`
- `interviewer_guidance`
- `expected_analysis`
- `data_reveal`
- `final_question`
- `solution`

Recommended new fields per block:

```json
{
  "block_id": "retailer_prompt_001",
  "block_type": "candidate_prompt",
  "stage": "opening",
  "visible_to_candidate": true,
  "trigger": "initial"
}
```

Recommended stage values:
- `opening`
- `diagnosis`
- `analysis`
- `recommendation`

Reason:
- interviewer logic can advance by stage
- candidate info reveals can be controlled
- judge can compare transcript against expected stage outcomes


### `database/Rubric/rubric.json`

Keep it global.

Do not duplicate rubric criteria inside each scenario.

Optional addition:

```json
{
  "rubric_id": "consulting_case_default_v1",
  "version": "1.0"
}
```


## Recommended State Model

Extend `InterviewState` with runtime-loaded artifacts:

```python
scenario_id: str
case_id: str
rubric_id: str
scenario_data: dict
case_data: dict
rubric_data: dict
revealed_block_ids: list[str]
current_case_stage: str
```

Reason:
- removes hidden file I/O from nodes
- makes runs reproducible
- keeps agent visibility enforceable


## Recommended Module Split

### 1. `src/main/studio/loaders.py`

Responsibilities:
- load scenario by id/path
- resolve case by `case_id`
- load rubric by `rubric_id`
- validate presence and basic shape

Suggested functions:

```python
def load_scenario(path: str) -> dict: ...
def load_case(case_id: str) -> dict: ...
def load_rubric(rubric_id: str) -> dict: ...
def load_simulation_bundle(scenario_path: str) -> dict: ...
```


### 2. `src/main/studio/case_runtime.py`

Responsibilities:
- filter visible blocks for candidate
- return interviewer guidance for current stage
- manage reveal history
- identify final recommendation trigger

Suggested functions:

```python
def get_candidate_visible_blocks(case_data: dict, revealed_block_ids: list[str]) -> list[dict]: ...
def get_hidden_guidance_blocks(case_data: dict, stage: str) -> list[dict]: ...
def advance_case_stage(state: dict) -> str: ...
```


### 3. `src/main/studio/judge_runtime.py`

Responsibilities:
- prepare rubric text
- prepare expected-analysis context
- map judge output to rubric dimensions

Suggested functions:

```python
def build_judge_context(case_data: dict, rubric_data: dict, scenario_data: dict) -> str: ...
```


## Agent Prompt Strategy

### Candidate

Use the existing template in `prompts/candidate_llm_prompt.md` as the main structured prompt.

Inject:
- `candidate_profile`
- transcript
- latest interviewer message
- candidate-visible case content only

This is better than the current generic `CANDIDATE_SYSTEM_PROMPT` alone because it makes candidate quality controllable by scenario.


### Interviewer

Stop using generic opening questions as the primary source of case content.

Instead:
- opening message comes from the case's candidate-visible opening block
- follow-up questions are guided by:
  - current case stage
  - hidden interviewer guidance blocks
  - judge guidance
  - transcript so far


### Judge

Judge should evaluate from three sources:
- transcript
- rubric
- hidden expected analysis / solution content

And optionally cross-check against:
- scenario `ground_truth.expected_scores`
- scenario `expected_feedback_points`

Important:
- rubric is the evaluation policy
- ground truth is the expected benchmark for that synthetic run


## Proposed Implementation Order

### Phase 1

- Add loader layer
- Extend `InterviewState`
- Pass `scenario_data`, `case_data`, and `rubric_data` into the graph

### Phase 2

- Update candidate node to use scenario candidate profile
- Update interviewer node to use case opening and hidden guidance
- Track `revealed_block_ids`

### Phase 3

- Update judge node to use rubric + expected analysis + scenario ground truth
- Return dimension-level scoring, not just a single overall score

### Phase 4

- Normalize case block types and stage fields across the case dataset
- Add validation scripts for scenario-case-rubric compatibility


## Recommended Design Decisions

1. Do not merge case, scenario, and rubric into one file.
   Separation is useful and already mostly present in the repo.

2. Do not store full rubric criteria inside each scenario.
   Reference by `rubric_id`.

3. Keep `ground_truth` inside scenarios.
   It belongs to synthetic evaluation, not to the case itself.

4. Let the interviewer be case-driven, not generic-prompt-driven.
   The case dataset already contains the right material.

5. Let the candidate be scenario-driven.
   Candidate quality should come from the scenario profile, not only from a shared generic prompt.

6. Let the judge be rubric-driven but case-aware.
   The rubric defines how to score; the hidden case solution defines what good reasoning looks like in that case.


## Immediate Next Step

Implement a first integration slice:

- create `loaders.py`
- extend `InterviewState`
- load one scenario, its case, and the rubric into state
- replace the hardcoded opening interviewer question with the case opening block

That is the smallest useful change that connects the existing datasets to the actual runtime.


## Alternative Plan Without Editing `scenarios/` or `database/`

This version assumes:
- no schema change in `scenarios/*.json`
- no field changes in `database/*cases*/`
- no edits to `database/Rubric/rubric.json`

The integration happens entirely in runtime code.


## Principle

Treat the existing JSON files as read-only source data.

Instead of normalizing the files themselves:
- normalize them in memory
- derive missing runtime fields through adapters
- keep compatibility with the current dataset


## Runtime-Only Architecture

### 1. Read-Only Data Sources

Use the current files as-is:

- `scenarios/*.json`
- `database/harvard_cases/*.json`
- `database/duke_cases/*.json`
- `database/agsm_cases/*.json`
- `database/Rubric/rubric.json`

No migration step is required.


### 2. Add an Adapter Layer

Create a thin translation layer that converts existing JSON shapes into a runtime model.

Suggested file:

`src/main/studio/adapters.py`

Suggested responsibilities:
- map scenario JSON into a runtime candidate config
- map case blocks into normalized runtime block categories
- map rubric JSON into judge-ready text / structures

Suggested functions:

```python
def adapt_scenario(raw_scenario: dict) -> dict: ...
def adapt_case(raw_case: dict) -> dict: ...
def adapt_rubric(raw_rubric: dict) -> dict: ...
```


## How the Adapters Would Work

### Scenario Adapter

Input:
- current scenario file

Output:
- runtime object with stable keys the graph can rely on

Example derived fields:

```python
{
    "scenario_id": raw["scenario_id"],
    "case_id": raw["case_id"],
    "rubric_id": "default_consulting_rubric",
    "candidate_profile": raw["candidate_profile"],
    "ground_truth": raw["ground_truth"],
}
```

Notes:
- `rubric_id` is derived in code, not added to the scenario file
- any optional runtime defaults live in code


### Case Adapter

Input:
- current case JSON with `case_content`

Output:
- runtime object with grouped blocks

Example derived structure:

```python
{
    "opening_block": {...},
    "candidate_visible_blocks": [...],
    "guidance_blocks": [...],
    "expected_analysis_blocks": [...],
    "final_question_blocks": [...],
    "solution_blocks": [...],
}
```

Mapping rule examples:
- `block_type == "prompt"` -> opening or candidate-visible prompt
- `block_type == "guidance"` -> interviewer guidance
- `block_type == "expected_analysis"` -> judge hidden benchmark
- `block_type == "final_recommendation"` -> either final question or solution, depending on content

If current data is ambiguous, resolve that ambiguity in code with heuristics, not by rewriting the JSON.


### Rubric Adapter

Input:
- current rubric JSON

Output:
- runtime object with:
  - score scale
  - dimensions
  - criteria by score
  - compact judge prompt rendering

This avoids touching the rubric file while still making it easier for `judge_node` to consume.


## Recommended Modules

### `src/main/studio/loaders.py`

Responsibilities:
- locate files
- read raw JSON
- call adapters
- return one simulation bundle

Suggested API:

```python
def load_simulation_bundle(scenario_path: str) -> dict: ...
```

Returned bundle:

```python
{
    "scenario": adapted_scenario,
    "case": adapted_case,
    "rubric": adapted_rubric,
}
```


### `src/main/studio/runtime_defaults.py`

Responsibilities:
- hold defaults that are not present in the source JSON

Examples:

```python
DEFAULT_RUBRIC_ID = "default_consulting_rubric"
DEFAULT_MAX_JUDGE_ROUNDS = 2
DEFAULT_CASE_STAGE = "opening"
```

This keeps assumptions visible and centralized.


## State Design for the No-Edit Plan

Extend `InterviewState` only in Python state, not in the JSON data:

```python
scenario_data: dict
case_data: dict
rubric_data: dict
revealed_block_ids: list[str]
current_case_stage: str
max_judge_rounds: int
```

This gives the graph a clean internal model while the files stay unchanged.


## Node Changes Under This Plan

### Candidate Node

Keep `scenarios/*.json` unchanged.

At runtime:
- load scenario
- adapt candidate profile
- render `prompts/candidate_llm_prompt.md`
- pass only:
  - adapted candidate profile
  - transcript
  - visible case content


### Interviewer Node

Keep `database/*cases*/` unchanged.

At runtime:
- use the case adapter to find the opening block
- use guidance blocks as hidden interviewer context
- use visible candidate blocks to decide what can be revealed
- derive recommendation-stage prompts from existing `final_recommendation` blocks


### Judge Node

Keep rubric and case files unchanged.

At runtime:
- use adapted rubric dimensions
- use expected-analysis blocks as hidden benchmark
- use scenario `ground_truth` for comparison / eval harness


## Benefits of This Plan

1. Zero dataset churn.
   Useful if the JSON files are already part of experiments and should remain stable.

2. Backward compatibility.
   You can improve runtime behavior without reworking existing assets.

3. Lower migration risk.
   No need to bulk-edit case files that may have inconsistent formatting.

4. Clear separation of concerns.
   Data remains archival; adapters carry operational logic.


## Tradeoffs of This Plan

1. More logic moves into code.
   Runtime adapters will contain heuristics that would otherwise be explicit in the JSON.

2. Ambiguities stay in the source data.
   For example, some `final_recommendation` blocks may function either as question or solution depending on content.

3. Validation becomes more important.
   Since semantics are inferred, adapter tests are needed.


## Recommended Implementation Order for the No-Edit Plan

1. Add `loaders.py`
   Read raw scenario, case, and rubric files.

2. Add `adapters.py`
   Convert raw JSON into stable runtime objects.

3. Extend `InterviewState`
   Store the adapted bundle in graph state.

4. Update `interviewer_node`
   Replace `CONSULTANCY_QUESTIONS` with adapted case opening content.

5. Update `candidate_node`
   Use adapted scenario profile plus candidate-visible case context.

6. Update `judge_node`
   Use adapted rubric plus expected-analysis blocks.

7. Add adapter tests
   Validate that a few representative cases are parsed into the expected runtime structure.


## Recommendation

If you want the safest path right now, this is the better first implementation plan.

It gives you:
- no manual data migration
- no edits to experimental scenario files
- no edits to case JSON assets
- a cleaner path to integrate the existing repo into the graph

Later, if the runtime model proves stable, you can decide whether it is worth normalizing the source JSON files themselves.
