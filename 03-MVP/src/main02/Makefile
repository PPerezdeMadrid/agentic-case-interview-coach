PYTHON ?= python3
APP_PORT ?= 5020

.PHONY: help env app graph

help:
	@printf "%s\n" "Targets available:"
	@printf "%s\n" "  make env    Open a shell with .venv activated on mac/Linux"
	@printf "%s\n" "              Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1"
	@printf "%s\n" "              Windows CMD: .\\.venv\\Scripts\\activate.bat"
	@printf "%s\n" "  make app    Start the main02 web dashboard on port $(APP_PORT)"
	@printf "%s\n" "  make graph  Start LangGraph Studio dev server for main02"

env:
	@if [ -f .venv/bin/activate ]; then \
		printf "Opening a new shell with .venv activated. Exit that shell to return.\n"; \
		$$SHELL -lc '. .venv/bin/activate && exec $$SHELL -i'; \
	elif [ -f .venv/Scripts/activate ]; then \
		printf "Windows Git Bash detected. Run: source .venv/Scripts/activate\n"; \
	elif [ -f .venv/Scripts/Activate.ps1 ]; then \
		printf "Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1\n"; \
		printf "Windows CMD: .\\.venv\\Scripts\\activate.bat\n"; \
	else \
		printf ".venv not found in %s\n" "$$(pwd)"; \
		exit 1; \
	fi

app:
	cd web && $(PYTHON) app.py

graph:
	cd studio && langgraph dev
