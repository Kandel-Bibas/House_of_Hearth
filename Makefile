.PHONY: dev test migrate clean help

VENV := .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest

help:
	@echo "Targets:"
	@echo "  make dev      — run uvicorn (api) + Vite (ui) together"
	@echo "  make test     — run the full test suite"
	@echo "  make migrate  — run alembic upgrade head"
	@echo "  make clean    — remove .pyc files and pytest cache"

dev:
	@echo "Starting Finance Tracker — backend on :8000, frontend on :5173 (Ctrl-C to stop)"
	$(PYTHON) scripts/run-dev.py

test:
	$(PYTEST) -v

migrate:
	$(ALEMBIC) upgrade head

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage
