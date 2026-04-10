.PHONY: help install run dev migrate migrate-up migrate-down migrate-current migrate-history

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt

run: ## Run the server
	python server.py

dev: ## Run the server with auto-reload
	uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# --- Database Migrations ---

migrate: ## Generate a new migration (usage: make migrate m="description")
	alembic revision --autogenerate -m "$(m)"

migrate-up: ## Apply all pending migrations
	alembic upgrade head

migrate-down: ## Rollback one migration
	alembic downgrade -1

migrate-current: ## Show current migration revision
	alembic current

migrate-history: ## Show migration history
	alembic history --verbose
