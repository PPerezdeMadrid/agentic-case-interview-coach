You are working inside my dissertation repository.

Project context:
I am building a multi-agent system for consulting case interview training. The system uses:
1. a Structured Case Dataset extracted from consulting casebooks,
2. a rubric based on the Management Consulted Case Interview Scoring Guide 2025,
3. a Synthetic Candidate Response Dataset,
4. a smaller Synthetic Case Interview Conversation Dataset.

The goal of this task is to create a controlled Python pipeline that generates synthetic student/candidate responses from my existing structured case JSON files and rubric JSON.

Current repository structure:

data_processed/
  agsm_cases/
    agsm_02_distilled_spirits.json
    agsm_03_airline_expansion.json
    agsm_04_health_care_costs.json
    ...
  duke_cases/
  harvard_cases/
  img/
  case_metadata.json
  casebooks.json

Rubric/
  Management-Consulted-Case-Interview-Scoring-Guide-2025.pdf
  rubric.json

script/
  extract_casebook.py
  review_server.py
  rewrite_harvard_output_cases.py
  structure_harvard_cases.py
  output/
  review_static/

Task:
Create a new generation pipeline for synthetic candidate responses.

Please do NOT modify the existing extraction scripts unless absolutely necessary.
Create new files under:

script/synthetic_dataset/

Expected new files:
1. script/synthetic_dataset/generate_atomic_responses.py
2. script/synthetic_dataset/assemble_conversations.py
3. script/synthetic_dataset/validate_synthetic_dataset.py
4. script/synthetic_dataset/synthetic_config.json
5. script/synthetic_dataset/README.md

Output folders:
Create these if they do not exist:

data_processed/synthetic_responses/
data_processed/synthetic_conversations/

Main input files:
- Case JSONs from:
  - data_processed/agsm_cases/
  - data_processed/duke_cases/
  - data_processed/harvard_cases/
- Rubric JSON:
  - Rubric/rubric.json

Important:
The case JSONs follow this general structure:

{
  "case_id": "...",
  "case_title": "...",
  "source": {...},
  "case_metadata": {...},
  "case_content": [
    {
      "block_id": "...",
      "block_type": "prompt | background | guidance | expected_analysis | data | exhibit | final_recommendation",
      "title": "...",
      "visible_to_candidate": true/false,
      "image": null,
      "source_page": 0,
      "content": "..."
    }
  ]
}

Rubric sections:
The rubric JSON contains these sections:
- case_opening
- case_structure
- case_math_answer
- case_creative_answer
- final_recommendation
- overall_structure
- overall_problem_solving
- overall_communication

Atomic responses should only use:
- case_opening
- case_structure
- case_math_answer
- case_creative_answer
- final_recommendation

Conversation-level scoring should use all sections, including:
- overall_structure
- overall_problem_solving
- overall_communication

Score scale:
- 1 = Needs improvement
- 2 = Developing
- 3 = Average
- 4 = Excellent
- not_tested = Insufficient evidence or section not covered

PART 1 — generate_atomic_responses.py

Build a script that:
1. Loads all case JSON files from the selected input folders.
2. Loads Rubric/rubric.json.
3. Detects which interview stages are relevant for each case.
4. Generates synthetic candidate responses for each relevant stage and target score.
5. Saves the dataset as JSONL and JSON.

Default output:
- data_processed/synthetic_responses/atomic_responses.jsonl
- data_processed/synthetic_responses/atomic_responses.json

The script should support CLI arguments:

python script/synthetic_dataset/generate_atomic_responses.py \
  --case-dirs data_processed/agsm_cases data_processed/duke_cases data_processed/harvard_cases \
  --rubric Rubric/rubric.json \
  --config script/synthetic_dataset/synthetic_config.json \
  --output-jsonl data_processed/synthetic_responses/atomic_responses.jsonl \
  --output-json data_processed/synthetic_responses/atomic_responses.json

Atomic response output schema:

{
  "response_id": "string",
  "case_id": "string",
  "case_title": "string",
  "casebook": "string_or_null",
  "dataset_type": "atomic_response",
  "conversation_stage": "case_opening | case_structure | case_math_answer | case_creative_answer | final_recommendation",
  "rubric_section": "same_as_conversation_stage",
  "target_score": 1,
  "expected_score": 1,
  "expected_label": "Needs improvement | Developing | Average | Excellent",
  "response_category": "needs_improvement | developing | average | excellent",
  "student_response": "string",
  "expected_strengths": ["string"],
  "expected_weaknesses": ["string"],
  "missing_elements": ["string"],
  "recommended_interviewer_followup": "string",
  "ideal_feedback_focus": ["string"],
  "source_case_blocks_used": ["block_id"],
  "generation_notes": {
    "uses_hidden_guidance": true,
    "candidate_should_not_see_hidden_guidance": true,
    "stage_detection_reason": "string"
  }
}

Stage detection logic:
Use the case_content blocks to decide which stages apply.

Rules:
- case_opening applies if the case has a candidate-visible prompt.
- case_structure applies if the case has guidance, expected_analysis, or any framework-related content.
- case_math_answer applies only if there is evidence of quantitative work:
  - block_type == "data"
  - titles/content containing words like "calculation", "market size", "revenue", "cost", "profit", "margin", "price", "volume", "units", "table", "numbers", "financials", "%"
- case_creative_answer applies if content suggests brainstorming:
  - words like "brainstorm", "ideas", "risks", "opportunities", "growth options", "recommend initiatives", "qualitative", "creative"
- final_recommendation applies if there is either:
  - block_type == "final_recommendation"
  - solution guidance
  - expected final answer
  - recommendation-related content

Do not force stages that are not present.
If uncertain, skip the stage unless synthetic_config.json says otherwise.

Generation method:
For now, implement generation in a modular way.

Create a function:

generate_response(case, rubric, stage, target_score, config) -> dict

Inside it, write the logic so that it can later be connected to an LLM API, but for now it should support two modes:

1. template mode
2. llm-ready prompt mode

Template mode:
Generate realistic but simple synthetic responses using templates based on:
- case title
- prompt
- stage
- target score
- rubric criteria

llm-ready prompt mode:
Instead of calling an API, create and store the prompt that would be sent to an LLM in a field called "llm_generation_prompt" if config["include_generation_prompt"] is true.

Do not add actual API calls unless there is already an API client configured in the repo. Keep it local and deterministic.

Important candidate visibility rule:
The student_response must never directly copy hidden guidance, expected_analysis, key findings, or solution text.
The generator may use hidden blocks to understand what a good or bad answer should look like, but the generated candidate answer should sound like a student speaking in an interview.

For example:
Bad:
"The solution is that product line B has the highest contribution margin according to interviewer guidance."

Good:
"I would compare the product lines based on revenue, margins, growth potential, and overlap with the current portfolio. If one product has higher margin and lower overlap, I would prioritize that."

Response quality by score:
Score 1:
- confused, vague, wrong, unstructured, or off-track
- may miss the business objective
- may give unsupported claims
- should still sound realistic

Score 2:
- partially relevant
- has some good instincts
- weak structure or incomplete reasoning
- may miss key dimensions

Score 3:
- mostly good
- clear but not perfect
- may miss prioritisation, synthesis, or one important detail

Score 4:
- strong
- structured
- case-specific
- hypothesis-driven
- clear and concise
- uses evidence appropriately, but must not unrealistically know hidden information unless it would have been revealed

PART 2 — validate_synthetic_dataset.py

Build a validator script that checks:
- all required fields exist
- response_id is unique
- case_id is not empty
- dataset_type == "atomic_response"
- conversation_stage is valid
- rubric_section is valid
- target_score and expected_score are in [1,2,3,4]
- expected_label matches the score
- student_response is not empty
- expected_strengths is a list
- expected_weaknesses is a list
- missing_elements is a list
- ideal_feedback_focus is a list
- recommended_interviewer_followup is not empty
- source_case_blocks_used is a list
- no response contains obvious placeholder text like "TODO", "lorem ipsum", or empty strings

Also add basic leakage checks:
- If hidden guidance content appears verbatim inside student_response, flag it.
- If expected_analysis content appears verbatim inside student_response, flag it.
- If final solution text appears verbatim inside student_response, flag it.

The leakage check does not need to be perfect. Use simple string overlap / substring logic.

The script should print:
- total responses
- number of validation errors
- number of warnings
- errors grouped by response_id
- stage distribution
- score distribution
- case distribution

CLI example:

python script/synthetic_dataset/validate_synthetic_dataset.py \
  --input data_processed/synthetic_responses/atomic_responses.jsonl \
  --cases data_processed/agsm_cases data_processed/duke_cases data_processed/harvard_cases

PART 3 — assemble_conversations.py

Build a script that creates a smaller Synthetic Case Interview Conversation Dataset from the atomic responses.

Input:
- data_processed/synthetic_responses/atomic_responses.jsonl

Output:
- data_processed/synthetic_conversations/synthetic_conversations.json
- data_processed/synthetic_conversations/synthetic_conversations.jsonl

Conversation schema:

{
  "conversation_id": "string",
  "case_id": "string",
  "case_title": "string",
  "dataset_type": "synthetic_conversation",
  "candidate_profile": "strong_candidate | weak_candidate | mixed_candidate | good_structure_bad_math | bad_structure_good_intuition | confused_candidate",
  "turns": [
    {
      "turn_id": 1,
      "speaker": "interviewer",
      "stage": "case_opening",
      "message": "string"
    },
    {
      "turn_id": 2,
      "speaker": "candidate",
      "stage": "case_opening",
      "rubric_section": "case_opening",
      "message": "string",
      "source_response_id": "string",
      "expected_score": 3
    }
  ],
  "expected_scores": {
    "case_opening": 3,
    "case_structure": 2,
    "case_math_answer": "not_tested",
    "case_creative_answer": "not_tested",
    "final_recommendation": 3,
    "overall_structure": 2,
    "overall_problem_solving": 2,
    "overall_communication": 3
  },
  "expected_final_feedback": "string",
  "source_atomic_response_ids": ["string"]
}

Conversation assembly rules:
- Use available atomic responses from the same case_id.
- Do not mix responses from different cases.
- Use interviewer messages that are simple and realistic.
- A conversation should include at least:
  - case_opening
  - case_structure
  - final_recommendation
- Include math or creative stages only if available for that case.
- If a stage is not included, mark its score as "not_tested".
- Generate 1 to 3 conversations per case depending on config.

Candidate profiles:
1. strong_candidate
   - mostly score 4
   - maybe one score 3
2. weak_candidate
   - mostly score 1 or 2
3. mixed_candidate
   - combination of 2, 3, and 4
4. good_structure_bad_math
   - case_structure 4
   - case_math_answer 1 or 2
5. bad_structure_good_intuition
   - case_structure 1 or 2
   - final_recommendation 3 or 4
6. confused_candidate
   - mostly score 1
   - unclear communication

Overall score estimation:
Create a simple deterministic heuristic:
- overall_structure:
  mainly based on case_structure and whether the conversation is coherent
- overall_problem_solving:
  average of case_structure, case_math_answer if tested, case_creative_answer if tested, final_recommendation
- overall_communication:
  based on clarity of the generated responses and candidate profile

Keep it simple and document the heuristic in README.md.

PART 4 — synthetic_config.json

Create a config file like this:

{
  "random_seed": 42,
  "responses_per_score": 1,
  "scores": [1, 2, 3, 4],
  "atomic_stages": [
    "case_opening",
    "case_structure",
    "case_math_answer",
    "case_creative_answer",
    "final_recommendation"
  ],
  "skip_missing_sections": true,
  "include_generation_prompt": true,
  "generation_mode": "template",
  "max_cases": null,
  "casebooks_to_include": ["agsm", "duke", "harvard"],
  "conversation_profiles": [
    "strong_candidate",
    "weak_candidate",
    "mixed_candidate",
    "good_structure_bad_math",
    "bad_structure_good_intuition",
    "confused_candidate"
  ],
  "conversations_per_case": 2,
  "output_format": ["json", "jsonl"]
}

PART 5 — README.md

Write clear documentation explaining:
- what the synthetic dataset is for
- how it relates to the structured case dataset
- how it relates to the rubric
- how to run generation
- how to run validation
- how to assemble conversations
- output file locations
- limitations of the synthetic generation approach
- warning that generated responses should be manually spot-checked

The README should include these commands:

python script/synthetic_dataset/generate_atomic_responses.py \
  --case-dirs data_processed/agsm_cases data_processed/duke_cases data_processed/harvard_cases \
  --rubric Rubric/rubric.json \
  --config script/synthetic_dataset/synthetic_config.json \
  --output-jsonl data_processed/synthetic_responses/atomic_responses.jsonl \
  --output-json data_processed/synthetic_responses/atomic_responses.json

python script/synthetic_dataset/validate_synthetic_dataset.py \
  --input data_processed/synthetic_responses/atomic_responses.jsonl \
  --cases data_processed/agsm_cases data_processed/duke_cases data_processed/harvard_cases

python script/synthetic_dataset/assemble_conversations.py \
  --input data_processed/synthetic_responses/atomic_responses.jsonl \
  --config script/synthetic_dataset/synthetic_config.json \
  --output-json data_processed/synthetic_conversations/synthetic_conversations.json \
  --output-jsonl data_processed/synthetic_conversations/synthetic_conversations.jsonl

Coding requirements:
- Use only standard Python libraries unless requirements.txt already includes something useful.
- Use pathlib.
- Use argparse.
- Use json and jsonlines-style writing manually if needed.
- Make scripts robust to missing fields.
- Print useful progress messages.
- Do not crash the full pipeline because one case is malformed; skip it and log a warning.
- Keep functions small and readable.
- Add docstrings.
- Make outputs deterministic using random_seed.
- Do not overwrite existing files unless the script is explicitly run with --overwrite.
- If output files already exist and --overwrite is not passed, raise a clear error.

Quality requirements:
- The generated dataset should be useful for testing:
  - Judge Agent scoring
  - Interviewer Agent follow-up decisions
  - Feedback Agent coaching
  - full LangGraph conversation flow

Do not generate overly perfect or generic responses.
Responses should sound like realistic students:
- some are vague,
- some are overconfident,
- some are confused,
- some have decent structure but weak business judgement,
- some are strong but not robotic.

End result:
After implementation, I should be able to run the three scripts and obtain:
1. an atomic synthetic response dataset,
2. a validation report in the terminal,
3. a synthetic conversation dataset.
```

---

También le puedes añadir este bloque final a Codex para que te lo haga **más seguro y revisable**:

```text
Before coding, inspect 2-3 existing case JSON files from data_processed/agsm_cases/ to understand their exact structure.

Then implement the pipeline incrementally:
1. first create config and loaders,
2. then stage detection,
3. then atomic response generation,
4. then validation,
5. then conversation assembly,
6. then README.

After writing the code, run it on only 2 cases first using --max-cases 2 or the config max_cases field.
Show me:
- the generated file paths,
- the number of responses generated,
- a sample atomic response,
- a sample synthetic conversation,
- any validation warnings.
```

Y si quieres una versión más agresiva para que Codex use LLM generation después, añade esto:

```text
Design the generation function so that replacing the local template generator with an LLM call later is easy.

Use this internal interface:

class SyntheticResponseGenerator:
    def generate_atomic_response(self, case, rubric, stage, target_score):
        ...

Implement TemplateSyntheticResponseGenerator now.
Leave a clearly marked TODO for LLMSyntheticResponseGenerator, but do not implement any external API call yet.
```

Codex que lo haga en **template mode**. Cuando el pipeline funcione y valide bien, ya le pides una segunda iteración para conectar generación LLM. Así evitas que te haga una cosa enorme, opaca y difícil de depurar.
