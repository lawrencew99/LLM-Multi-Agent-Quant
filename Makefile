.PHONY: help install dev fmt lint type test up down demo clean

help:
	@echo "NewsAlpha — make targets"
	@echo "  install   sync runtime deps with uv"
	@echo "  dev       sync runtime + dev + ui deps"
	@echo "  fmt       format code with ruff"
	@echo "  lint      run ruff linter"
	@echo "  type      run mypy"
	@echo "  test      run pytest"
	@echo "  up        start docker services (postgres + qdrant + redis)"
	@echo "  down      stop docker services"
	@echo "  demo      run the hello-world LangGraph demo"
	@echo "  clean     remove caches and build artefacts"

install:
	uv sync

dev:
	uv sync --extra dev --extra ui --extra backtest

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint:
	uv run ruff check src tests

type:
	uv run mypy src/newsalpha

test:
	uv run pytest

up:
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 3
	docker compose ps

down:
	docker compose down

demo:
	uv run python -m newsalpha.demo

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
