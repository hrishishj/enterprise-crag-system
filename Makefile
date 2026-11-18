.PHONY: dev test lint types arch check legacy-test eval up down

dev:
	uv venv --python 3.12 && uv pip install -e ".[dev]"

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

types:
	uv run mypy -p crag -p evals

arch:
	uv run lint-imports

check: lint types arch test

eval:
	@echo "Eval harness arrives in Phase 1"

up:
	docker compose up -d --build

down:
	docker compose down
