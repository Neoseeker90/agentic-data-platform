.PHONY: install lint typecheck test test-integration migrate up down clean

install:
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy packages/ services/

test:
	uv run pytest packages/ services/ -v --cov --cov-report=term-missing

test-integration:
	uv run pytest tests/integration/ -v -m integration

up:
	docker compose up -d

down:
	docker compose down

migrate:
	./scripts/migrate.sh

dev:
	uv run uvicorn agent_api.main:app \
		--reload \
		--port 8000 \
		--app-dir services/agent_api/src \
		--reload-dir services/agent_api/src \
		--reload-dir packages

seed-docs:
	uv run python scripts/seed_docs.py

run-eval:
	uv run python scripts/run_eval.py $(ARGS)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
