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

<!-- State the license (e.g. MIT) or mark OPEN until the owner decides. Never default an unknown
     license to permissive silently. -->
OPEN — owner to confirm the project license before first public release.

## Open questions

<!-- Add architectural forks here as they arise, each with a recommended default and "owner to
     confirm". Move to a DECIDED entry above once resolved. -->
- (none yet)
