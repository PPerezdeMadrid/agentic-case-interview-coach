# --- Local (venv) configuration ---
PYTHON ?= python3
VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python

# --- HPC (conda) configuration ---
CONDA ?= $(if $(CONDA_EXE),$(CONDA_EXE),conda)
CONDA_ENV ?= coach
PYTHON_VERSION ?= 3.11
CONDA_RUN := $(CONDA) run -n $(CONDA_ENV) --no-capture-output

# --- Shared configuration ---
WORKBENCH_PORT ?= 5020
REQUIREMENTS_FILE ?= main/studio/requirements.txt
RUNNER_STATE_FILE ?= .make.runner.mk

-include $(RUNNER_STATE_FILE)

# Selecciona el intérprete para los targets de ejecución.
# Por defecto usa el venv local. setup-hpc persiste RUNNER=hpc en RUNNER_STATE_FILE.
RUNNER ?= local
ifeq ($(RUNNER),hpc)
	RUN := $(CONDA_RUN)
	PY  := $(CONDA_RUN) python
else
	RUN :=
	PY  := $(VENV_PYTHON)
endif

.PHONY: help setup setup-local setup-hpc env-hpc langgraph workbench app test run-all run-all-baseline run-all-agentic

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
	@printf "%s\n" ""
	@printf "%s\n" "make setup-hpc persists RUNNER=hpc for later commands in $(RUNNER_STATE_FILE)"

# --- Setup: local (venv) ---
setup-local:
	test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install -r $(REQUIREMENTS_FILE)
	printf "%s\n" "RUNNER := local" > $(RUNNER_STATE_FILE)

# Alias por compatibilidad con lo de siempre
setup: setup-local

# --- Setup: HPC (conda) ---
env-hpc:
	@$(CONDA) env list | grep -qE "^$(CONDA_ENV)[[:space:]]" || \
		$(CONDA) create -n $(CONDA_ENV) python=$(PYTHON_VERSION) -y

setup-hpc: env-hpc
	$(CONDA_RUN) python -m ensurepip --upgrade || true
	$(CONDA_RUN) python -m pip install --upgrade pip
	$(CONDA_RUN) python -m pip install -r $(REQUIREMENTS_FILE)
	printf "%s\n" "RUNNER := hpc" > $(RUNNER_STATE_FILE)
	printf "%s\n" "RUNNER := hpc" > $(RUNNER_STATE_FILE)

# --- Run targets (usan RUNNER: local por defecto, hpc opcional) ---
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
