PYTHON ?= python3
WORKBENCH_PORT ?= 5020

.PHONY: help langgraph workbench app

help:
	@printf "%s\n" "Available targets:"
	@printf "%s\n" "  make langgraph  Start the LangGraph development server for main"
	@printf "%s\n" "  make workbench  Start the workbench web app on port $(WORKBENCH_PORT)"
	@printf "%s\n" "  make app        Alias for make workbench"

langgraph:
	cd main/studio && langgraph dev

workbench:
	cd main/web && WORKBENCH_PORT=$(WORKBENCH_PORT) $(PYTHON) app.py

app: workbench
