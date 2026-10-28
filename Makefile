.PHONY: setup demo reset test check evaluate verify browser
UV_CACHE_DIR ?= /tmp/parcelresolve-uv-cache
export UV_CACHE_DIR
PORT ?= 8873
EVAL_OUTPUT ?= evaluation/runs/run-$(shell date -u +%Y%m%dT%H%M%S%N)

setup:
	uv sync --frozen
	npm ci --ignore-scripts
	npm run build

demo: setup
	.venv/bin/python -m parcelresolve.cli seed
	.venv/bin/python -m uvicorn parcelresolve.api:create_app --factory --host 127.0.0.1 --port $(PORT)

reset:
	.venv/bin/python -m parcelresolve.cli reset

test:
	.venv/bin/python -m pytest -q

check:
	.venv/bin/ruff check parcelresolve tests
	.venv/bin/ruff format --check parcelresolve tests
	.venv/bin/mypy parcelresolve
	npm run typecheck
	npm run build

evaluate:
	.venv/bin/python -m parcelresolve.evaluation --output $(EVAL_OUTPUT) --seeds 7 19 41

verify: check test evaluate

browser:
	npm run browser:check
