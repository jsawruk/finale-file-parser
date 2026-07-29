# Decisions

The log of decisions made and questions still open. **Standing rule: don't silently resolve an open
question in code — propose it here, get a decision, then build.** Newest entries at the top.

## Format

Each entry: a date, the decision or open question, and a one-line reason. Mark open items **OPEN**
and resolved ones **DECIDED**.

---

## 2026-07-22 — DECIDED: cipher parameters taken as facts from MIT-licensed source

The `score.dat` cipher — seed `0x28006D45`, the BSD `rand()` LCG, the
`(upper + upper // 255)` output function, and the 128 KiB keystream reset — was read from
denigma's source (MIT), which credits Deguerre for the discovery. The implementation here is
written independently; the parameters are not.

Reason: the earlier decision was to use published *documentation* as reference and write
implementations independently. That proved insufficient — the transform is documented nowhere in
prose, only in code. An algorithm choice and a seed value are facts rather than creative
expression, and MIT would permit outright porting with attribution in any case.

Consequence: attribution to both denigma and Deguerre is required in `docs/REFERENCES.md` and in
`enigma/crypt.py`. `docs/formats/score-dat.md` records precisely what this project derived from the
corpus and what it did not.

## 2026-07-22 — DECIDED: one provenance type for both formats

`ProvenanceStamp` (renamed from `MusStamp`) carries date, application, and platform for both `.mus`
and `.musx`, plus `modified_by` and `app_version` which only `.musx` fills. `MusxDetail.platform`
was removed — platform now lives on each stamp, matching `.mus`'s rule that both stamps must not be
assumed to agree.

Reason: the formats recorded the same facts and the code modelled them twice, one module apart —
`.musx` discarded its dates entirely and collapsed two platforms into one field. Breaking the
published type was cheap at 0.0.1 and would only get more expensive.

`appRegion` is deliberately not modelled: `US` in all 802 corpus blocks, so it carries no
information yet.

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

## 2026-07-24 — DECIDED: port zlib's `contrib/blast` for legacy `.mus` payloads

**Context.** `.mus` files from Finale 2001-2005 (139 of the 238 corpus files) store their payload as a
PKWARE DCL ("implode") stream. No Python stdlib module reads this format, and no maintained pure-Python
implementation was found.

**Decision.** Port Mark Adler's `blast.c` (zlib `contrib/blast`) to Python as
`enigma/blast.py`, rather than shelling out to a tool or adding a dependency.

**Licensing.** `contrib/blast` is under the **zlib License**, which permits use and modification
provided the origin is not misrepresented and altered versions are marked as such. The module docstring
states plainly that it is a port of Adler's work, and `docs/REFERENCES.md` records the attribution —
the same treatment already given to denigma/Deguerre for the `score.dat` cipher.

**Why not a dependency.** The format is small and stable (the tables are fixed constants), the port is
~150 lines, and it must enforce this project's own allocation caps on untrusted input, which a
third-party library would not.

**Consequence.** `read_mus_payload()` decodes 238 of 238 corpus files. Correctness rests on the
upstream test vector rather than on our own reimplementation being self-consistent.


## 2026-07-27 — DECIDED: parts follow the instrument list, not the staff number

**Context.** `build_score` ordered parts by staff number. A `.musx` records the score's real staff
layout in `instUsed`, one record per slot, and that order is **not** always ascending: 10 of 401
corpus documents list staves in an order their numbers do not follow. Those scores exported with
their parts down the page in the wrong places — silently, since every part was still present. It
also forced 8 staff groups to be dropped as non-contiguous.

**Decision.** Order parts by `staff_order(document)`. A staff carrying music but holding no slot in
the list keeps a place after the listed ones rather than being dropped.

**Consequence.** 10 documents change part order; 388 do not. All 79 same-content pairs keep identical
part order across containers, because a `.mus` has no instrument-list record and falls back to
numeric order, and no paired document is one of the 10. Staff groups rise from 201 to 209 — every
group previously dropped for non-contiguity now survives.

- **RESOLVED 2026-07-27 — staff 32767 is not a part.** See the entry below.


## 2026-07-27 — DECIDED: staff 32767 is a reserved staff and is not exported

**Context.** Every one of the 401 corpus documents declares a staff numbered 32767 — 0x7FFF, the same
sentinel the format uses for "to the end" in `staffGroup.endMeas`. It has its own `staffSpec`, a
`gfhold` per measure, and real entries, so it is not a phantom of our reading, and it was exported as
a part named "Staff 32767" in every file this project produced.

**Evidence that it is not part of the score.** Each of these was measured over the whole corpus:

- it is **never** in the score's instrument list (0 of 401) — and `instUsed` is precisely the layout
  of the staves a score shows;
- it is **never** named by a staff group (0 of 401);
- its `staffSpec` is a template, not a description of a part: 401 documents hold only **two** distinct
  bodies, all with the same fixed `instUuid`, a one-line `customStaff`, and clefs, key signatures,
  measure numbers, repeats and repeat barlines all hidden;
- 376 of 398 give it a single repeated pitch, always in layer 1, and none carries a lyric;
- its entries are **disjoint** from every real staff in all 401 documents, so it is not an alias or a
  wildcard for one;
- it is the **only** staff in the corpus absent from the instrument list, so excluding it excludes
  nothing else.

**Decision.** `build_score` does not make a part for it. The exclusion is by staff id rather than by
"absent from the instrument list", because a `.mus` has no instrument-list record — excluding it only
where a list exists would drop the staff from `.musx` and keep it in `.mus`, and the two containers
would then disagree on every score. All 93 buildable `.mus` documents carry the same staff.

**What is deliberately not claimed.** What Finale uses it for. A hidden one-line staff of repeated
quarter notes fits a click track, a rhythmic-notation staff, or a chord-symbol carrier, and the
corpus does not decide between them. The decision rests only on it not being part of the score.

**Consequence.** No `Score` loses all its parts. Beams fall 84,620 → 84,593 (27 of them were on this
staff); articulations, lyrics and staff groups are unchanged.

- **RESOLVED 2026-07-27 — parts have gaps where a staff is empty.** Fixed; see the entry below. Was: `build_score` makes a measure only where a staff
  has entries, so a staff silent through a measure gets no `Measure` at all and its part's measure
  list skips a number. The reserved staff was hiding how much of this there is: it covered 1,375
  measures across 162 documents that no real staff occupies — typically measures 1 and 2 of a score
  whose real staves start at 3. Four of those carry a repeat barline that now has no part to be drawn
  on, which is why the repeat sweep counts 107 forward and 119 backward against a pool holding 109
  and 121. The fix is to emit a full-measure rest where a part is silent, which is its own slice.


## 2026-07-27 — DECIDED: every part gets every measure, silent bars included

**Context.** `build_score` made a `Measure` only where a staff had entries, so a part silent through
a bar skipped it and its measure numbering jumped. **6,362 measures were missing across 420 of 731
corpus parts** — 57% of parts. The output stayed well-formed, which is why it went unnoticed: a
reader meeting a gap in the numbering cannot tell a silent bar from a lost one.

**Decision.** A part covers every measure of the score, and a bar it rests through carries one
full-measure rest.

Three pieces make that work:

- **The measure list comes from `measSpec`**, not from where the music is. It runs 1..N with no gaps
  in all 398 buildable corpus documents and nothing sounds outside it. Using the measures that hold
  entries loses every bar in which the whole ensemble rests.
- **The key comes from the measure** (`effective_keys`, promoted to public), not from the staff's
  notes — so a part silent through the opening bars is not reported as being in C major there.
- **Clefs carry forward.** `clefs_by_measure` reads `gfhold`, and a measure a staff rests through has
  no `gfhold` at all; without carrying the last one forward a part loses its clef the moment it falls
  silent and re-announces it on returning. Before the first `gfhold`, the staff's `defaultClef`
  applies.

**Why a measure rest is its own thing.** `Event.is_measure_rest` is not "a rest that happens to last
a whole note": it is written as one symbol centred in the bar and its length follows the time
signature, so a 3/4 measure rest lasts 3/4 and has **no note value at all**. MusicXML spells that
`<rest measure="yes"/>` with a duration and no `<type>` — and asking `_note_type` for the type of a
3/4 event raises, which is the check that the two stay in step.

**Consequence.** All 398 documents now give every part the same contiguous 1..N measure list, with
6,362 measure rests. This also restores the 4 repeat barlines that reached no part after the
reserved-staff exclusion, so the repeat sweep matches the pool exactly again.

Carrying clefs forward cut the `.mus`/`.musx` clef disagreement from 22 measures to **10**, without
touching the clef reading itself: half of those 22 were one container having a `gfhold` where the
other did not, rather than the two disagreeing about a clef.


## 2026-07-28 — RESOLVED: the transposition octave is not missing from a `.mus`

**Context.** The project recorded that a `.mus` cannot supply a transposing staff's octave, and that
2,491 written pitches were therefore an octave wrong. The first half is now proven exhaustively; the
second was the wrong conclusion drawn from it.

**Finding.** The octave is **baked into every note's `harm_lev`**. Finale folds the octaves out of a
transposition into a residue in −4..+2 and folds the same octaves into `harm_lev`; the two are a
matched pair. A `.mus` stores the residue with an unshifted `harm_lev`, a `.musx` the full interval
with a `harm_lev` shifted to match. Measured across 30,000+ notes, the delta is exactly seven
diatonic steps per octave, with no exceptions. **Neither container needs an octave field**, which is
how Finale displays a `.mus` correctly.

Undoing the fold on the `.musx` side takes the containers from 27,931 identical / 2,493 octave-only
to **30,423 identical / 1 octave-only**.

**Decision.** Document it; change no code yet. Reconciling the two containers does not say which
frame is the true written pitch, and the obvious external check — where notes land on the staff —
cannot adjudicate: four candidate models each fit some intervals and none fits all, and a
transposing instrument has its own tessitura, so the non-transposing baseline is not a fair
comparison for the staves in question. Changing it would move the octave of every transposing staff
in the output.

See `docs/formats/transposition-octave.md` for the full evidence and for what would settle it.

- **RESOLVED 2026-07-28 — which octave frame is the true written pitch?** Both, depending on the
  residue. The independent witness turned out not to need a new file: the interval values identify
  the instruments (B♭ trumpet, F horn, E♭ alto/tenor/baritone sax, double bass, xylophone), and each
  has a published written range that owes nothing to Finale. `spell_note` undoes the fold for every
  **downward** transposition; an upward one shows no fold. Measuring each instrument against **its
  own** published range — not a compromise range shared by two instruments, which hid an error for
  a while — notes inside range go **82.0% → 94.4%**: baritone sax 7.3% → 100%, double bass
  69.8% → 99.7%, guitar 82.1% → 99.7%. Container octave-only differences **2,491 → 1**, and that
  one is a content difference between the files. The octave was never missing from a `.mus`.
