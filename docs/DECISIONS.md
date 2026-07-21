# Decisions

The log of decisions made and questions still open. **Standing rule: don't silently resolve an open
question in code — propose it here, get a decision, then build.** Newest entries at the top.

## Format

Each entry: a date, the decision or open question, and a one-line reason. Mark open items **OPEN**
and resolved ones **DECIDED**.

---

## 2026-07-20 — DECIDED: toolchain

Python managed with **uv**; **ruff** for lint + format; **mypy --strict** for types; **pytest** for tests. One toolchain, declared in the project manifest and `CLAUDE.md`, run through
`make`. Reason: a single enforced toolchain removes a class of back-and-forth and keeps every
session consistent.

## 2026-07-20 — DECIDED: license posture

**MIT** — confirmed by the owner, matching the `LICENSE` file already in the repo. Reason: a
permissive license suits a format-interoperability library that other tools need to embed freely.

## Open questions

<!-- Add architectural forks here as they arise, each with a recommended default and "owner to
     confirm". Move to a DECIDED entry above once resolved. -->
- **OPEN — format coverage: `.musx` only, or `.mus` too?** They are different formats (`.musx` is a
  zip container; legacy `.mus` is a monolithic binary). Recommended default: target `.musx` first
  and treat `.mus` as a later, separate reader behind the same public API. Owner to confirm.
- **OPEN — output data model.** Whether to expose a bespoke Python model or emit an existing
  interchange format (MusicXML / MEI). Recommended default: a small internal model first, with
  exporters layered on top so we don't couple parsing to any one output. Owner to confirm.
- **OPEN — how much to rely on existing community reverse-engineering work** (e.g. the `musx`
  ecosystem and Finale plug-in documentation), and under what license those findings arrive.
  Recommended default: use published documentation as reference, don't copy code. Owner to confirm.
