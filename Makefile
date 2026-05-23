.PHONY: help dev stop reset migrate migration downgrade logs test lint pre-commit

help:
	@echo ""
	@echo "  make dev              Start all services"
	@echo "  make stop             Stop all services"
	@echo "  make reset            Wipe all data and restart fresh"
	@echo "  make migrate          Apply all pending migrations"
	@echo "  make migration m=''   Generate a new migration"
	@echo "  make downgrade        Rollback the last migration"
	@echo "  make logs             Tail api + worker logs"
	@echo "  make test             Run test suite with coverage"
	@echo "  make lint             Run flake8 linter"
	@echo "  make pre-commit       Run all pre-commit checks"
	@echo ""

dev:
	docker compose up -d
	@echo "API:          http://localhost:8012"
	@echo "API docs:     http://localhost:8012/docs"
	@echo "Demo:         http://localhost:8502"
	@echo "MinIO UI:     http://localhost:9001"
	@echo "PostgreSQL:   localhost:5435"

stop:
	docker compose down

reset:
	docker compose down -v
	docker compose up -d

migrate:
	docker compose exec api alembic upgrade head

migration:
	@if [ -z "$(m)" ]; then \
		echo "Usage: make migration m='describe your change'"; \
		exit 1; \
	fi
	docker compose exec api alembic revision --autogenerate -m "$(m)"

downgrade:
	docker compose exec api alembic downgrade -1

logs:
	docker compose logs -f api worker

test:
	docker compose exec api pytest tests/ -v \
		--cov=. \
		--cov-report=term-missing \
		--cov-fail-under=80

lint:
	docker compose exec api flake8 .

pre-commit:
	./pre-commit.sh
