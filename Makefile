.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

.PHONY: help
help: ## Show the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create the virtualenv and install both halves
	python3 -m venv $(BACKEND)/.venv
	$(BACKEND)/.venv/bin/pip install --upgrade pip
	$(BACKEND)/.venv/bin/pip install -e "$(BACKEND)[dev]"
	cd $(FRONTEND) && npm install

.PHONY: dev
dev: ## Run the API with secrets loaded from 1Password
	./scripts/dev.sh

.PHONY: web
web: ## Run the frontend dev server
	cd $(FRONTEND) && npm run dev

.PHONY: test
test: ## Run the backend test suite
	cd $(BACKEND) && .venv/bin/python -m pytest -q

.PHONY: lint
lint: ## Lint and typecheck both halves
	cd $(BACKEND) && .venv/bin/python -m ruff check app tests
	cd $(FRONTEND) && npx tsc --noEmit

.PHONY: format
format: ## Apply formatters
	cd $(BACKEND) && .venv/bin/python -m ruff check app tests --fix
	cd $(FRONTEND) && npx prettier --write "src/**/*.{ts,tsx,css}"

.PHONY: build
build: ## Production build of the frontend
	cd $(FRONTEND) && npm run build

.PHONY: up
up: ## Start the full stack in Docker
	docker compose up --build

.PHONY: down
down: ## Stop the stack and drop its volumes
	docker compose down -v

.PHONY: migrate
migrate: ## Apply database migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a migration: make revision m="add x"
	cd $(BACKEND) && .venv/bin/alembic revision --autogenerate -m "$(m)"
