# Decisions

The log of decisions made and questions still open. **Standing rule: don't silently resolve an open
question in code — propose it here, get a decision, then build.** Newest entries at the top.

## Format

Each entry: a date, the decision or open question, and a one-line reason. Mark open items **OPEN**
and resolved ones **DECIDED**.

---

## 2026-07-22 — DECIDED: both `.mus` and `.musx` are in scope

Settled by what shipped: `detect_version` handles both, `.mus` banner parsing and provenance stamps
are done, and `.musx` has a full container reader. Reason: the corpus is 238 `.mus` and 401 `.musx`
— dropping either would abandon a third of real files.

## 2026-07-22 — DECIDED: use community reverse-engineering as reference, not as source

Published community documentation (e.g. the MIT-licensed EnigmaXML documentation) may be read as a
reference for what the format is; implementations are written independently rather than ported.
Reason: keeps provenance simple while not re-deriving what is already public. Licenses of known
sources are recorded in `docs/REFERENCES.md`.

## 2026-07-21 — DECIDED: one module owns archive access

`container/` owns opening, validating, and reading `.musx` archives. `version/musx.py` is a client.
Reason: the two had parallel implementations of the same zip-safety logic, which can drift; a
single owner means one place to harden.

## 2026-07-21 — DECIDED: reject unsafe member names, allow unknown ones

The container reader raises only on genuinely dangerous names (absolute, `..` segments,
backslashes, control characters). A merely *unfamiliar* name is surfaced as data. Reason: rejecting
unrecognised archives would contradict the principle that unknown variants stay inspectable, and
would make a new Finale member name break version detection outright. The fixture generator keeps a
strict allowlist, because we control what gets committed.

## 2026-07-21 — DECIDED: container fixtures carry structure only

Committed `.musx` fixtures harvest member names, order, compression method and declared lengths
from the corpus, and regenerate every payload. Reason: `score.dat` is the musical work and the
corpus also embeds `graphics/*.jpg` which may be licensed artwork. Payload bytes never leave the
gitignored corpus.

## 2026-07-21 — DECIDED: version detection precedes record parsing

Version is detected from headers/metadata before any record parsing, and both formats are covered.
Whether each version needs *distinct record-parsing logic* remains unknown — that question opens
once record parsing begins.

## 2026-07-21 — DECIDED: defusedxml for all XML parsing

`.musx` metadata is attacker-controlled XML, and stdlib `ElementTree` is vulnerable to
entity-expansion and external-entity attacks. All XML parsing uses **`defusedxml`** — the project's
first runtime dependency. Reason: hand-hardening the stdlib parser is easy to get subtly wrong and
easy to regress.

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
- **OPEN — should `.musx` also produce `ProvenanceStamp` provenance?** `.musx`'s `NotationMetadata.xml`
  `created`/`modified` blocks carry `<year><month><day><application><platform>` — field for field,
  exactly what `ProvenanceStamp` (introduced for `.mus`) models. `version/musx.py` currently reads only
  `platform` out of those blocks, collapses `created`'s and `modified`'s platform with `or` into a
  single `MusxDetail.platform`, and discards the dates entirely. So the same data is modeled two
  incompatible ways one module apart: `.mus` keeps full per-stamp `ProvenanceStamp`s, `.musx` throws the
  dates away and flattens platform to one field. If `.musx` moved to `ProvenanceStamp` provenance too,
  `MusxDetail.platform` would presumably be dropped in favour of a platform on each stamp, matching
  `.mus`'s "each stamp carries its own — do not assume both agree" rule. Recommended default:
  unify, because leaving this alone means two representations of identical data drifting further
  apart with every change to either module. **Not done in this branch** — `MusxDetail` is a
  published type, and changing its shape (dropping `platform`, adding stamp-based `created`/
  `modified`) needs its own design pass, not a slip-in alongside a `.mus`-only slice. Owner to
  confirm.
- **OPEN — GUI framework and repo layout for the desktop frontend.** The frontend is DECIDED (see
  above); how to build and package it is not. Recommended default: keep the parser a standalone
  importable package and add the app as a separate package in the same repo, so the library never
  gains a GUI dependency. Framework unchosen. Owner to confirm.
- **OPEN — does each detected version need distinct record-parsing logic?** Version detection
  itself is DECIDED (see above) and covers both `.mus` and `.musx`. What remains unknown is whether
  the record layouts inside a given version differ enough to require separate parsing paths per
  version, or whether one parser can cover the range. Opens once record parsing begins.
- **OPEN — `.musx` major-version-to-year mapping.** The `major` field (15/16/17/18) has no
  established mapping to Finale's marketing years (2009/2011/2012/2014...), and nothing in the
  corpus bridges the two schemes. See `docs/ARCHITECTURE.md`.
