# finale-file-parser — one command surface (Python).
#
# The environment is set ONCE here, so the command Claude Code (or CI, or you) runs is always a
# clean `make <target>`. One permission covers all of them and nothing is hardcoded to a machine.
# Override the runner with:  make test PY="python -m"   (if you are not using uv)

PY ?= uv run
CODE ?= src tests scripts

.PHONY: help install test lint fmt typecheck check clean

help:
	@echo "Targets:"
	@echo "  install    create the venv and install dependencies (uv sync)"
	@echo "  test       run the test suite (pytest)"
	@echo "  lint       ruff check"
	@echo "  fmt        auto-format with ruff"
	@echo "  typecheck  mypy --strict"
	@echo "  check      lint + format-check + typecheck + test  (the pre-push gate)"
	@echo "  clean      remove caches and build artifacts"

install:
	uv sync

test:
	$(PY) pytest

lint:
	$(PY) ruff check $(CODE)

fmt:
	$(PY) ruff format $(CODE)

typecheck:
	$(PY) mypy $(CODE)

check:
	$(PY) ruff check $(CODE)
	$(PY) ruff format --check $(CODE)
	$(PY) mypy $(CODE)
	$(PY) pytest

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
