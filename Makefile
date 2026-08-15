# finale-file-parser — one command surface (Python).
#
# The environment is set ONCE here, so the command Claude Code (or CI, or you) runs is always a
# clean `make <target>`. One permission covers all of them and nothing is hardcoded to a machine.
# Override the runner with:  make test PY="python -m"   (if you are not using uv)

PY ?= uv run
CODE ?= src tests scripts

.PHONY: help install hooks test test-sweeps lint fmt typecheck check check-full clean

help:
	@echo "Targets:"
	@echo "  install    create the venv, install dependencies (uv sync), and enable git hooks"
	@echo "  hooks      point git at .githooks/ (blocks direct pushes to main)"
	@echo "  check      lint + format + types + tests, no corpus sweeps (~1 min)"
	@echo "  check-full check plus the corpus sweeps (~9 min); run before pushing"
	@echo "  test-sweeps  the corpus sweeps on their own"
	@echo "  test       run the test suite (pytest, parallel; JOBS=0 for serial)"
	@echo "  lint       ruff check"
	@echo "  fmt        auto-format with ruff"
	@echo "  typecheck  mypy --strict"
	@echo "  check      lint + format-check + typecheck + test  (the pre-push gate)"
	@echo "  spec         regenerate docs/formats/finale-formats.{html,pdf}"
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

# `-n auto` fans the suite across cores; `--dist loadfile` keeps every test in a
# file on one worker, which matters because the corpus sweeps hang their work off
# module-scoped fixtures — splitting a file would recompute one on each worker
# and cost more than it saves. Override with:  make test JOBS=0   (serial)
JOBS ?= auto
PYTEST_ARGS ?= $(if $(filter 0,$(JOBS)),,-n $(JOBS) --dist loadfile)

# The 28 *_corpus_sweep.py files read every one of the 639 corpus documents.
# They hold this project's hardest-won evidence and they cost about nine
# minutes; everything else runs in ten seconds. Splitting them out is what makes
# a gate worth running between edits.
SWEEPS = --ignore-glob=*_corpus_sweep.py

test:
	$(PY) pytest $(PYTEST_ARGS) $(SWEEPS)

test-sweeps:
	$(PY) pytest $(PYTEST_ARGS)

lint:
	$(PY) ruff check $(CODE)

fmt:
	$(PY) ruff format $(CODE)

typecheck:
	$(PY) mypy $(CODE)

# Two gates, because one that takes nine minutes is a gate people skip.
#
# `check` is the one to run between edits: lint, format, types and every test
# that does not read the corpus. About a minute.
#
# `check-full` adds the corpus sweeps and is the gate before a push. The hook in
# .githooks/ only blocks direct pushes to main -- it does not run tests -- so
# this one is a habit rather than an enforcement. Keep it: the sweeps are where
# a wrong offset or a dropped record actually shows up, and several of this
# project's real defects were caught by nothing else.
#
# Repeats the commands rather than depending on the targets so the order and
# output stay fixed -- but they must pass PYTEST_ARGS too, or the gate everyone
# actually runs is the one place that never gets the parallelism.
check:
	$(PY) ruff check $(CODE)
	$(PY) ruff format --check $(CODE)
	$(PY) mypy $(CODE)
	$(PY) pytest $(PYTEST_ARGS) $(SWEEPS)

check-full:
	$(PY) ruff check $(CODE)
	$(PY) ruff format --check $(CODE)
	$(PY) mypy $(CODE)
	$(PY) pytest $(PYTEST_ARGS)

# The specification is generated from the parser: offsets and constants are
# imported from the reading code, so the document cannot drift from it. The
# PDF step needs Chrome and is skipped with a message when it is absent.
spec:
	PYTHONPATH=scripts $(PY) python -m format_spec

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
