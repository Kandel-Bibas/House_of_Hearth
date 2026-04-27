.PHONY: dev test migrate clean help

VENV := .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest

help:
	@echo "Targets:"
	@echo "  make dev      — run uvicorn (Plan 5 will add Vite alongside)"
	@echo "  make test     — run the full test suite"
	@echo "  make migrate  — run alembic upgrade head"
	@echo "  make clean    — remove .pyc files and pytest cache"

dev:
	@echo "Starting Finance Tracker on http://localhost:8000 (Ctrl-C to stop)"
	$(UVICORN) api.main:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PYTEST) -v

migrate:
	$(ALEMBIC) upgrade head

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage
