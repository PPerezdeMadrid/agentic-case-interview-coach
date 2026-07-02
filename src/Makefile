PYTHON ?= python3
WORKBENCH_PORT ?= 5020

.PHONY: help langgraph workbench app test run-all run-all-baseline run-all-agentic

help:
	@printf "%s\n" "Available targets:"
	@printf "%s\n" "  make langgraph  Start the LangGraph development server for main"
	@printf "%s\n" "  make workbench  Start the workbench web app on port $(WORKBENCH_PORT)"
	@printf "%s\n" "  make app        Alias for make workbench"
	@printf "%s\n" "  make test       Run studio and workbench test suites"
	@printf "%s\n" "  make run-all    Run baseline and agentic across all scenarios"
	@printf "%s\n" "  make run-all-baseline  Run baseline across all scenarios"
	@printf "%s\n" "  make run-all-agentic   Run agentic across all scenarios"

langgraph:
	cd main/studio && langgraph dev

workbench:
	cd main/web && WORKBENCH_PORT=$(WORKBENCH_PORT) $(PYTHON) app.py

app: workbench

test:
	cd main/studio && $(PYTHON) -m unittest discover -s tests
	cd main/web && $(PYTHON) -m unittest discover -s tests

run-all:
	$(PYTHON) run_all_scenarios.py --graph both

run-all-baseline:
	$(PYTHON) run_all_scenarios.py --graph baseline

run-all-agentic:
	$(PYTHON) run_all_scenarios.py --graph agentic
