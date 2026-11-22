# Common tasks. `make help` lists them.

UV := uv run --project backend
MODAL := $(UV) modal
DEPLOY := deploy/modal_app.py
ENV_FLAG := $(if $(wildcard .env),--env-file .env,)

.PHONY: help install dev dev-api dev-web dev-ui test lint prefetch deploy stop logs

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-9s %s\n", $$1, $$2}'

install: ## Install the backend and frontend dependencies
	uv sync --project backend
	pnpm --dir frontend install

dev: ## Run the API (mock brain) and the app with hot reload on :5173
	$(MAKE) -j2 dev-api dev-web

dev-api:
	$(UV) $(ENV_FLAG) uvicorn --factory neuromarketing.api.app:create_app --reload --reload-dir backend/src --port 8000

dev-web:
	pnpm --dir frontend dev:backend

dev-ui: ## Run the app alone on :5173, with a mock API in the browser
	pnpm --dir frontend dev

test: ## Run the backend and frontend tests
	cd backend && uv run pytest
	pnpm --dir frontend test

lint: ## Lint and type-check everything
	cd backend && uv run ruff check src tests ../deploy && uv run ruff format --check src tests ../deploy && uv run mypy
	pnpm --dir frontend lint
	pnpm --dir frontend typecheck

prefetch: ## Download the models into the Modal Volume (skips when present)
	$(MODAL) run $(DEPLOY)::prefetch_models

deploy: prefetch ## Deploy to Modal with the settings and keys in .env
	$(MODAL) deploy $(DEPLOY)

stop: ## Stop the deployed app (data stays in its Volume)
	$(MODAL) app stop neuromarketing

logs: ## Follow the deployed app's logs
	$(MODAL) app logs neuromarketing
