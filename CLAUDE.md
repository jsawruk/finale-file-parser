# CLAUDE.md

Instructions Claude Code should hold in **every** session for this repo. Keep this file short and
high-signal — it loads into every session, so every line competes for attention. Deep or procedural
material lives in `docs/`; read the relevant doc before working in that area.

## What this project is

A library for reading Finale music notation files (`.mus`, `.musx`) and exposing their musical
content — notes, rhythms, staves, and score structure — as plain Python data. Finale was
discontinued in 2024 and its format is proprietary and undocumented, so this project works from
reverse engineering and existing community research. It is aimed at people who need to migrate,
analyse, or archive scores that currently only exist as Finale files.

## Tech stack (current decisions)

- **Language / runtime:** Python (>=3.12), managed with **uv**.
- **Key libraries:** `defusedxml` — all XML parsing, because `.musx` metadata is untrusted input.
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
make check      # lint + format-check + typecheck + tests, no corpus sweeps (~1 min)
make check-full # the above plus the 28 corpus sweeps (~9 min)  <- run before pushing
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
- **Every score fixture must be cleared for use.** Test fixtures must be music we authored
  ourselves, public domain, or properly licensed. Never commit a `.mus`/`.musx` file obtained from a
  third party without an appropriate license. Record the license and provenance of every fixture.
- **Untrusted input.** Every input file is hostile until parsed: bounds-check every offset and
  length read from the file, never `eval`/`pickle` file contents, and cap allocations driven by
  file-supplied sizes. Malformed input must raise a clear error, never crash the interpreter or
  hang.
- **Format knowledge is documented, not implicit.** When you determine what a byte range or record
  means, write it down in `docs/ARCHITECTURE.md` with the evidence — a magic number decoded in code
  with no explanation is unmaintainable.

## How to work in this repo

- **Plan first** for anything non-trivial: propose a short plan, get sign-off, then build.
- Build in the order in `docs/ROADMAP.md`. Ship the MVP path end-to-end before adding later features.
- When you make or change an architectural decision, record it in `docs/DECISIONS.md`.
- **At the end of every working session, update `.remember/now.md`** (what's in progress, hazards,
  next step) so the next session resumes instead of rediscovering.
- Read the relevant `docs/` file before working in its area: architecture → `docs/ARCHITECTURE.md`;
  security/licensing → `docs/SECURITY.md`.
