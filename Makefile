PYTHON ?= .venv/bin/python
MVP_ENV_FILE ?=

.PHONY: test lint db-up db-down migrate run check-delivery require-runtime-env

test:
	PYTHONPATH=src $(PYTHON) -m pytest

lint:
	PYTHONPATH=src $(PYTHON) -m ruff check src tests

require-runtime-env:
	@test -n "$(MVP_ENV_FILE)" || (echo "Задайте MVP_ENV_FILE вне репозитория." >&2; exit 1)
	sh ./scripts/validate_runtime_env.sh "$(MVP_ENV_FILE)"

db-up: require-runtime-env
	docker-compose --env-file "$(MVP_ENV_FILE)" up -d --wait database

db-down: require-runtime-env
	docker-compose --env-file "$(MVP_ENV_FILE)" down

migrate: require-runtime-env
	set -a; . "$(MVP_ENV_FILE)"; set +a; PYTHONPATH=src $(PYTHON) -m alembic upgrade head

run: require-runtime-env
	set -a; . "$(MVP_ENV_FILE)"; set +a; PYTHONPATH=src $(PYTHON) -m product_search.main

check-delivery:
	./scripts/check_delivery.sh
