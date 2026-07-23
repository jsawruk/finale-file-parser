# finale-file-parser — one command surface (Python).
#
# The environment is set ONCE here, so the command Claude Code (or CI, or you) runs is always a
# clean `make <target>`. One permission covers all of them and nothing is hardcoded to a machine.
# Override the runner with:  make test PY="python -m"   (if you are not using uv)

PY ?= uv run
CODE ?= src tests scripts

.PHONY: help install hooks test lint fmt typecheck check clean

help:
	@echo "Targets:"
	@echo "  install    create the venv, install dependencies (uv sync), and enable git hooks"
	@echo "  hooks      point git at .githooks/ (blocks direct pushes to main)"
	@echo "  test       run the test suite (pytest)"
	@echo "  lint       ruff check"
	@echo "  fmt        auto-format with ruff"
	@echo "  typecheck  mypy --strict"
	@echo "  check      lint + format-check + typecheck + test  (the pre-push gate)"
	@echo "  clean      remove caches and build artifacts"

install: hooks
	uv sync

# Git will not use committed hooks on its own — core.hooksPath is local config, so every fresh
# clone starts unprotected until this runs. It is wired into `install` so that happens by default.
hooks:
	@git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo; skipping hooks"; exit 0; }
	@chmod +x .githooks/* 2>/dev/null || true
	@git config core.hooksPath .githooks
	@echo "git hooks enabled (core.hooksPath=.githooks) — direct pushes to main are blocked"

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
