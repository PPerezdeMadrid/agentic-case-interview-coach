# --- Local (venv) configuration ---
PYTHON ?= python3
VENV_DIR ?= .venv
VENV_PYTHON := $(abspath $(VENV_DIR))/bin/python

# --- HPC (conda) configuration ---
CONDA ?= $(if $(CONDA_EXE),$(CONDA_EXE),conda)
CONDA_ENV ?= coach
PYTHON_VERSION ?= 3.11
CONDA_RUN := $(CONDA) run -n $(CONDA_ENV) --no-capture-output

# --- Shared configuration ---
WORKBENCH_PORT ?= 5020
REQUIREMENTS_FILE ?= requirements.txt
RUNNER_STATE_FILE ?= .make.runner.mk
# LangGraph CLI (it does not come from requirements.txt). The [inmem] extra enables 'langgraph dev'.
LANGGRAPH_CLI ?= langgraph-cli[inmem]

-include $(RUNNER_STATE_FILE)

# Selects the interpreter for run targets.
# By default it uses the local venv. setup-hpc persists RUNNER=hpc in RUNNER_STATE_FILE.
RUNNER ?= local
ifeq ($(RUNNER),hpc)
	RUN := $(CONDA_RUN)
	PY  := $(CONDA_RUN) python
else
	RUN :=
	PY  := $(VENV_PYTHON)
endif

.PHONY: help setup setup-local setup-hpc env-hpc langgraph workbench app test run-all run-all-baseline run-all-agentic experiment rag-ablation judge-eval interviewer-eval baseline-eval

help:
	@printf "%s\n" "Available targets:"
	@printf "%s\n" "  make setup-local  Create $(VENV_DIR) if needed and install requirements (venv)"
	@printf "%s\n" "  make setup-hpc    Create conda env '$(CONDA_ENV)' if needed and install requirements"
	@printf "%s\n" "  make setup        Alias for make setup-local"
	@printf "%s\n" "  make langgraph    Start the LangGraph development server for main"
	@printf "%s\n" "  make workbench    Start the workbench web app on port $(WORKBENCH_PORT)"
	@printf "%s\n" "  make app          Alias for make workbench"
	@printf "%s\n" "  make test         Run studio and workbench test suites"
	@printf "%s\n" "  make run-all      Run baseline and agentic across all scenarios [N=<repeat>] [LABEL=...]"
	@printf "%s\n" "  make run-all-baseline  Run baseline across all scenarios [N=<repeat>] [LABEL=...]"
	@printf "%s\n" "  make run-all-agentic   Run agentic across all scenarios [N=<repeat>] [LABEL=...]"
	@printf "%s\n" "  make experiment CASE=<case_id> N=<repeat> [GRAPH=agentic|baseline|both] [LABEL=...]"
	@printf "%s\n" "                    Run every scenario of a case N times each"
	@printf "%s\n" "  make rag-ablation BATCH=<batch_dir_name> [LIMIT=<n>]"
	@printf "%s\n" "                    Replay a batch's stored transcripts through the judge eval nodes"
	@printf "%s\n" "                    with RAG disabled, and compare eval_case/eval_dialog scores against"
	@printf "%s\n" "                    that batch's original (with-RAG) scores for the same transcript"
	@printf "%s\n" "  make judge-eval [GOLDEN_SET=worldcup] [LIMIT=<n>]"
	@printf "%s\n" "                    Run a judge golden-set CSV (database/node_eval/judge_eval/) against the"
	@printf "%s\n" "                    real judge LLM and score enough_evidence accuracy; read the result"
	@printf "%s\n" "                    on the workbench's Agents > Judge page"
	@printf "%s\n" "  make interviewer-eval [INTERVIEWER_GOLDEN_SET=evidence_handling] [LIMIT=<n>]"
	@printf "%s\n" "                    Run an interviewer golden-set CSV (database/node_eval/interviewer_eval/,"
	@printf "%s\n" "                    one of socratic_function|evidence_handling|guardrail|turn_control)"
	@printf "%s\n" "                    against the real interviewer LLM; read the result on the workbench's"
	@printf "%s\n" "                    Agents > Interviewer page"
	@printf "%s\n" "  make baseline-eval [BASELINE_GOLDEN_SET=evidence_handling] [LIMIT=<n>]"
	@printf "%s\n" "                    Run a baseline golden-set CSV (database/node_eval/baseline_eval/,"
	@printf "%s\n" "                    same 4 golden sets as interviewer-eval, plus 'worldcup' -- baseline's"
	@printf "%s\n" "                    ready_for_evaluation call graded on the judge golden set, built via"
	@printf "%s\n" "                    node_eval/baseline_eval/build_baseline_worldcup_golden_set.py) against"
	@printf "%s\n" "                    the real baseline LLM; read the agentic-vs-baseline comparison on the"
	@printf "%s\n" "                    workbench's Agents > Judge / Agents > Interviewer pages"
	@printf "%s\n" ""
	@printf "%s\n" "make setup-hpc persists RUNNER=hpc for later commands in $(RUNNER_STATE_FILE)"

# --- Setup: local (venv) ---
setup-local:
	test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r $(REQUIREMENTS_FILE)
	$(VENV_PYTHON) -m pip install "$(LANGGRAPH_CLI)"
	printf "%s\n" "RUNNER := local" > $(RUNNER_STATE_FILE)
	@printf "%s\n" "Setup complete. Remember to configure your .env file."

# Alias for backward compatibility
setup: setup-local

# --- Setup: HPC (conda) ---
env-hpc:
	@$(CONDA) env list | grep -qE "^$(CONDA_ENV)[[:space:]]" || \
		$(CONDA) create -n $(CONDA_ENV) python=$(PYTHON_VERSION) pip -y

setup-hpc: env-hpc
	$(CONDA_RUN) python -m ensurepip --upgrade || true
	$(CONDA_RUN) python -m pip install --upgrade pip
	$(CONDA_RUN) python -m pip install -r $(REQUIREMENTS_FILE)
	$(CONDA_RUN) python -m pip install "$(LANGGRAPH_CLI)"
	printf "%s\n" "RUNNER := hpc" > $(RUNNER_STATE_FILE)
	@printf "%s\n" "Setup complete. Remember to configure your .env file."

# --- Run targets (use RUNNER: local by default, hpc optional) ---
langgraph:
	cd main/studio && $(RUN) langgraph dev --no-browser

workbench:
	cd main/web && WORKBENCH_PORT=$(WORKBENCH_PORT) $(PY) app.py

app: workbench

test:
	cd main/studio && $(PY) -m unittest discover -s tests
	cd main/web && $(PY) -m unittest discover -s tests

run-all:
	$(PY) run_all_scenarios.py --graph both --repeat $(N) --label "$(LABEL)"

run-all-baseline:
	$(PY) run_all_scenarios.py --graph baseline --repeat $(N) --label "$(LABEL)"

run-all-agentic:
	$(PY) run_all_scenarios.py --graph agentic --repeat $(N) --label "$(LABEL)"

# --- Experiment: run every scenario of one case N times each ---
# Usage: make experiment CASE=01-energy-company N=10 [GRAPH=agentic] [LABEL=exp1]
GRAPH ?= agentic
N ?= 4
LABEL ?=

experiment:
	@if [ -z "$(CASE)" ]; then \
		printf "%s\n" "Usage: make experiment CASE=<case_id> N=<repeat_count> [GRAPH=agentic|baseline|both] [LABEL=...]"; \
		exit 1; \
	fi
	$(PY) run_all_scenarios.py --graph $(GRAPH) --case $(CASE) --repeat $(N) --label "$(LABEL)"

# --- RAG ablation eval: replay a batch's transcripts through the judge with RAG disabled ---
# Usage: make rag-ablation BATCH=<batch_dir_name> [LIMIT=<n>]
BATCH ?=
LIMIT ?=

rag-ablation:
	@if [ -z "$(BATCH)" ]; then \
		printf "%s\n" "Usage: make rag-ablation BATCH=<batch_dir_name> [LIMIT=<n>]"; \
		exit 1; \
	fi
	$(PY) rag_ablation_eval.py --batch $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

# --- Judge golden-set eval: score enough_evidence accuracy against the real judge LLM ---
# Usage: make judge-eval [GOLDEN_SET=worldcup] [LIMIT=<n>]
GOLDEN_SET ?= worldcup

judge-eval:
	$(PY) main/studio/node_eval/judge_eval/run_judge_golden_set.py \
		--csv database/node_eval/judge_eval/judge_golden_set_$(GOLDEN_SET).csv \
		$(if $(LIMIT),--limit $(LIMIT),)

# --- Interviewer golden-set eval: grade move accuracy against the real interviewer LLM ---
# Usage: make interviewer-eval [INTERVIEWER_GOLDEN_SET=evidence_handling] [LIMIT=<n>]
INTERVIEWER_GOLDEN_SET ?= evidence_handling

interviewer-eval:
	$(PY) main/studio/node_eval/interviewer_eval/run_interviewer_golden_set.py \
		--csv database/node_eval/interviewer_eval/interviewer_golden_set_$(INTERVIEWER_GOLDEN_SET).csv \
		$(if $(LIMIT),--limit $(LIMIT),)

# --- Baseline golden-set eval: grade the fused interviewer/judge/grader node against ---
# --- the same fixtures interviewer-eval uses, for a direct agentic-vs-baseline comparison ---
# Usage: make baseline-eval [BASELINE_GOLDEN_SET=evidence_handling] [LIMIT=<n>]
BASELINE_GOLDEN_SET ?= evidence_handling

baseline-eval:
	$(PY) main/studio/node_eval/baseline_eval/run_baseline_golden_set.py \
		--csv database/node_eval/baseline_eval/baseline_golden_set_$(BASELINE_GOLDEN_SET).csv \
		$(if $(LIMIT),--limit $(LIMIT),)
