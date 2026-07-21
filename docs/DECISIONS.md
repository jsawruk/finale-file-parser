# Decisions

The log of decisions made and questions still open. **Standing rule: don't silently resolve an open
question in code — propose it here, get a decision, then build.** Newest entries at the top.

## Format

Each entry: a date, the decision or open question, and a one-line reason. Mark open items **OPEN**
and resolved ones **DECIDED**.

---

## 2026-07-20 — DECIDED: output data model — internal IR, MusicXML as the first exporter

Parsing produces a project-internal **intermediate representation (IR)**; output formats are
exporters layered on top, with **MusicXML** as the first. Every supported input converges on the
same IR (`.mus` directly; `.musx` via EnigmaXML), so format-specific quirks stay in the readers and
never leak into the exporters. Reason: multiple inputs and a likely-growing set of outputs make a
hub-and-spoke shape cheaper than coupling any reader to any writer.

Consequence: MusicXML's expressive limits must not constrain the IR. If Finale represents something
MusicXML cannot, the IR keeps it and the exporter drops it — the loss happens at the edge, on the
way out, and is documented there.

## 2026-07-20 — DECIDED: scope includes a desktop frontend

Beyond the parser library, the project will ship a **desktop application** providing (a) a hex
viewer that decodes binary entries and displays their structure values, and (b) a rendering of the
corresponding notation. Reason: reverse-engineering an undocumented format is far faster when you
can see bytes and the notation they produce side by side — the viewer is a research instrument, not
just a deliverable.

Consequence: the library must stay independently usable and must not take a GUI dependency. See the
open question on GUI framework and repo layout.

## 2026-07-20 — DECIDED: third-party reference documents are vendored into `docs/` under fair use

Four out-of-print reference documents are committed to `docs/` (the ETF specification, the 1996
Enigma Entry Pool document, the Cahill thesis, and the LilyPond ETF notes). All are cited with
author, original URL, and archive URL in `docs/REFERENCES.md`.

Owner's determination: these works are **no longer accessible through their original channels**,
are of value to other researchers, and are reproduced here for **research and scholarship** under
fair use. All works are properly attributed. **The project will comply promptly with any takedown
request** from a rights holder.

Consequence for future sessions: do not remove these files as a "licensing cleanup" — this is a
settled decision, not an oversight. Any *new* vendored document must meet the same bar: out of
print, properly cited with original and archive URLs, and added to `REFERENCES.md` at the same time
as the file.

## 2026-07-20 — DECIDED: toolchain

Python managed with **uv**; **ruff** for lint + format; **mypy --strict** for types; **pytest** for
tests. One toolchain, declared in the project manifest and `CLAUDE.md`, run through `make`. Reason:
a single enforced toolchain removes a class of back-and-forth and keeps every session consistent.

## 2026-07-20 — DECIDED: license posture

**MIT** — confirmed by the owner, matching the `LICENSE` file already in the repo. Reason: a
permissive license suits a format-interoperability library that other tools need to embed freely.

## Open questions

<!-- Add architectural forks here as they arise, each with a recommended default and "owner to
     confirm". Move to a DECIDED entry above once resolved. -->
- **OPEN — format coverage: `.musx` only, or `.mus` too?** They are different formats (`.musx` is a
  zip container; legacy `.mus` is a monolithic binary). Recommended default: target `.musx` first
  and treat `.mus` as a later, separate reader behind the same public API. Owner to confirm.
- **OPEN — how much to rely on existing community reverse-engineering work** (e.g. the `musx`
  ecosystem and Finale plug-in documentation), and under what license those findings arrive.
  Recommended default: use published documentation as reference, don't copy code. Owner to confirm.
  (Licenses of the known community sources are recorded in `docs/REFERENCES.md` — the code-bearing
  ones are MIT, the Finale Lua scripts CC0-1.0.)
- **OPEN — GUI framework and repo layout for the desktop frontend.** The frontend is DECIDED (see
  above); how to build and package it is not. Recommended default: keep the parser a standalone
  importable package and add the app as a separate package in the same repo, so the library never
  gains a GUI dependency. Framework unchosen. Owner to confirm.
- **OPEN — format versioning.** Finale's long release history means `.mus` and `.musx` almost
  certainly cover several on-disk variants; the PRONOM and Library of Congress records list distinct
  Enigma Binary signatures, which supports this. Recommended default: detect the writing version
  before parsing records, and treat version coverage as an explicit dimension of the test corpus.
  Owner to confirm.
