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
REQUIREMENTS_FILE ?= main/studio/requirements.txt
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

.PHONY: help setup setup-local setup-hpc env-hpc langgraph workbench app test run-all run-all-baseline run-all-agentic experiment

help:
	@printf "%s\n" "Available targets:"
	@printf "%s\n" "  make setup-local  Create $(VENV_DIR) if needed and install requirements (venv)"
	@printf "%s\n" "  make setup-hpc    Create conda env '$(CONDA_ENV)' if needed and install requirements"
	@printf "%s\n" "  make setup        Alias for make setup-local"
	@printf "%s\n" "  make langgraph    Start the LangGraph development server for main"
	@printf "%s\n" "  make workbench    Start the workbench web app on port $(WORKBENCH_PORT)"
	@printf "%s\n" "  make app          Alias for make workbench"
	@printf "%s\n" "  make test         Run studio and workbench test suites"
	@printf "%s\n" "  make run-all      Run baseline and agentic across all scenarios"
	@printf "%s\n" "  make run-all-baseline  Run baseline across all scenarios"
	@printf "%s\n" "  make run-all-agentic   Run agentic across all scenarios"
	@printf "%s\n" "  make experiment CASE=<case_id> N=<repeat> [GRAPH=agentic|baseline|both] [LABEL=...]"
	@printf "%s\n" "                    Run every scenario of a case N times each"
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
	$(PY) run_all_scenarios.py --graph both

run-all-baseline:
	$(PY) run_all_scenarios.py --graph baseline

run-all-agentic:
	$(PY) run_all_scenarios.py --graph agentic

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
