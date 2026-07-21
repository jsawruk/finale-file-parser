# CLAUDE.md

Instructions Claude Code should hold in **every** session for this repo. Keep this file short and
high-signal — it loads into every session, so every line competes for attention. Deep or procedural
material lives in `docs/`; read the relevant doc before working in that area.

## What this project is

A parser for Finale music notation files (.mus/.musx).

<!-- Replace the line above with one short paragraph: what it does and for whom. No marketing. -->

## Tech stack (current decisions)

- **Language / runtime:** Python (>=3.12), managed with **uv**.
- **Key libraries:** none yet — add each here with a one-line reason as you introduce it.
- Open questions live in `docs/DECISIONS.md` — don't silently resolve them in code.

## Conventions

- **Toolchain (non-negotiable):** `uv` (environment) · `ruff` (lint + format) · `mypy --strict`
  (types) · `pytest` (tests). Run everything through `make` (below), never ad-hoc.
- **Commits:** Conventional Commits — `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
  The subject describes the behavioural change, not the diff.
- **Branches/PRs:** one change → one branch → one pull request. Never commit directly to `main`.
- **Code shape:** small, pure functions; do I/O at the edges. If the project gains a canonical data
  representation, name it here and forbid parallel ones.

## Commands

```
make help      # list every target
make install   # sync dependencies (uv sync)
make test      # run the test suite (pytest)
make lint      # ruff check
make fmt       # ruff format
make check     # lint + format-check + typecheck + test  <- the pre-push gate
```

## Guardrails — do not violate

<!-- Highest-value section for an AI collaborator. Keep the universal ones; add project-specific
     invariants (licensing, access control, data handling, compliance). See docs/SECURITY.md. -->

- **Secrets:** never commit credentials, API keys, tokens, or a real `.env`. `.env.example` lists
  variables with placeholder values only.
- **No home-rolled crypto or auth.** Use vetted libraries.
- **Large binaries stay out of git** (datasets, model weights, media): use external storage,
  reference by path + content hash.
- **Flag, don't decide.** Anything with legal, security, licensing, or irreversible consequences is
  the owner's call — surface it in `docs/DECISIONS.md`, don't assume it.

## How to work in this repo

- **Plan first** for anything non-trivial: propose a short plan, get sign-off, then build.
- Build in the order in `docs/ROADMAP.md`. Ship the MVP path end-to-end before adding later features.
- When you make or change an architectural decision, record it in `docs/DECISIONS.md`.
- **At the end of every working session, update `.remember/now.md`** (what's in progress, hazards,
  next step) so the next session resumes instead of rediscovering.
- Read the relevant `docs/` file before working in its area: architecture → `docs/ARCHITECTURE.md`;
  security/licensing → `docs/SECURITY.md`.
