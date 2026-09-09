# =============================================================================
# ARCHIMEDES — developer tasks
#
#   make setup   install everything (Python venv + pnpm) and create .env
#   make dev     run api + worker + web with hot reload via docker compose
#   make test    run the Python test suite (offline — uses MOCK_LLM fixtures)
#   make lint    ruff + black + mypy + eslint
#
# Bare-metal (no docker): make api  +  make worker  +  make web
# =============================================================================
SHELL := /bin/bash
.DEFAULT_GOAL := help

API_DIR := services/api
WEB_DIR := apps/web

.PHONY: help setup venv web-install dev up down logs api worker web \
        test lint format migrate seed-sql seed-demo smoke build-images clean

help: ## show available targets
	@awk -F':.*## ?' '/^[a-zA-Z_-]+:.*## / { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: venv web-install ## install all dependencies and create .env
	@test -f .env || (cp .env.example .env && echo "→ created .env — now add your Nebius / Tavily / Supabase keys")
	@echo "→ Setup complete. Edit .env, then 'make dev' (docker) or 'make api' + 'make worker' + 'make web'."

venv: ## create the Python virtualenv and install API deps
	python3 -m venv $(API_DIR)/.venv
	$(API_DIR)/.venv/bin/pip install --upgrade pip
	$(API_DIR)/.venv/bin/pip install -r $(API_DIR)/requirements.txt

web-install: ## install web dependencies (pnpm)
	pnpm --dir $(WEB_DIR) install

dev: ## run the full stack via docker compose (api :8000, web :3000, worker)
	docker compose up --build

up: ## start the stack in the background
	docker compose up -d

down: ## stop the stack
	docker compose down

logs: ## tail stack logs
	docker compose logs -f

api: ## run the FastAPI server locally with hot reload
	cd $(API_DIR) && .venv/bin/uvicorn app.main:app --reload --port 8000

worker: ## run the local polling worker locally
	cd $(API_DIR) && .venv/bin/python worker/main.py --poll

web: ## run the Next.js dev server locally
	pnpm --dir $(WEB_DIR) dev

test: ## run Python tests (no credits needed — MOCK_LLM fixtures)
	cd $(API_DIR) && MOCK_LLM=true .venv/bin/python -m pytest -q

lint: ## ruff + black + mypy + eslint
	cd $(API_DIR) && .venv/bin/ruff check app worker tests
	cd $(API_DIR) && .venv/bin/black --check app worker tests
	cd $(API_DIR) && .venv/bin/mypy app --ignore-missing-imports
	pnpm --dir $(WEB_DIR) lint

format: ## auto-format Python and web code
	cd $(API_DIR) && .venv/bin/black app worker tests && .venv/bin/ruff check --fix app worker tests
	pnpm --dir $(WEB_DIR) exec prettier --write .

migrate: ## apply Supabase migrations (DATABASE_URL=... make migrate, or `supabase db push`)
	@if [ -n "$$DATABASE_URL" ]; then psql "$$DATABASE_URL" -f supabase/migrations/0001_init.sql; else supabase db push; fi

seed-sql: ## load demo data: DATABASE_URL=... make seed-sql (idempotent)
	psql "$$DATABASE_URL" -f supabase/seed.sql

seed-demo: ## seed the demo project through the running API (logged-in demo user)
	cd $(API_DIR) && .venv/bin/python ../../scripts/demo_seed.py

smoke: ## end-to-end smoke test against a running stack
	cd $(API_DIR) && .venv/bin/python ../../scripts/smoke_test.py

build-images: ## build the api, worker and web container images
	docker build -f $(API_DIR)/Dockerfile        -t archimedes-api:latest    $(API_DIR)
	docker build -f $(API_DIR)/Dockerfile.worker -t archimedes-worker:latest $(API_DIR)
	docker build                                 -t archimedes-web:latest    $(WEB_DIR)

clean: ## remove caches and the virtualenv
	rm -rf $(API_DIR)/.venv $(API_DIR)/.pytest_cache $(API_DIR)/.mypy_cache $(API_DIR)/.ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
