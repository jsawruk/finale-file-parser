# Architecture

How the system is shaped. Keep this current as the design settles — a fresh session reads this before
working on structure.

## Overview

The system consists of a parser library that reads Finale `.mus` and `.musx` files and exports
MusicXML, plus a frontend desktop application providing two functions:

- A hex viewer that decodes binary entries and shows the structure values
- A rendering of the corresponding music notation

Because parsing supports multiple inputs, all data flows into a single intermediate representation
(IR). The library stays independently usable and takes no GUI dependency.

## Modules

<!-- List the top-level modules under src/ and the single responsibility of each. -->

- `src/` — the main source directory.
- `src/finale_file_parser/version/` — identifies which Finale version wrote a file, before any
  record parsing. `models.py` (types), `family.py` (magic → family), `mus.py` (banner parsing),
  `musx.py` (archive metadata), `detect.py` (public entry).
- `src/finale_file_parser/container/` — owns all `.musx` archive access. `models.py`
  (`ContainerEntry`, `CorruptContainerError`), `names.py` (member-name safety), `musx.py`
  (`open_musx`, `MusxContainer`). `version/musx.py` is a client of this module; nothing else
  opens archives directly.
- `src/finale_file_parser/enigma/` — decodes a `.musx`'s `score.dat` into EnigmaXML and parses that
  EnigmaXML into a navigable document. `crypt.py` (the cipher, pure — no I/O), `models.py`
  (`CorruptScoreError`), `score.py` (`score_xml`, composing `container.open_musx` with the cipher
  and a capped inflate), `document.py` (`parse_enigma`, `EnigmaDocument`, `Pool`, `Record` — the
  uniform record/pool model), `music.py` (`read_entry`, `Entry`, `Note`, `Duration` — the first
  typed layer over the generic `entry`/`note` records). See "Known format facts — score.dat",
  "Known format facts — EnigmaXML structure", and "Known format facts — entries and pitch" below.

### Known format facts — version

- `.mus` begins with `ENIGMA BINARY FILE` at offset 0, identical across Finale 2001–2012. The
  writing version is an ASCII banner at offset `0x20`, e.g.
  `Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.`
  Evidence: 238 corpus files; see `docs/superpowers/specs/2026-07-21-version-detection-design.md`.
- That banner field is fixed-size and is **not** zero-filled on rewrite, so a shorter banner can
  leave a tail of the previous, longer one behind (observed: `logy` from the Finale 2004 Coda
  banner surviving into a 2005 file). Always cut at the first NUL.
- `.mus` carries two provenance stamps (date, application, platform) at fixed offsets: created —
  date `0x66`, application tag `0x70`, platform tag `0x74`; modified — date `0x8C`, application tag
  `0x96`, platform tag `0x9A`. The date is `[year - 1900, month, day]` as three `u8`. Present in
  238/238 corpus files, with `created <= modified` in all of them. **Platform is recoverable from
  `.mus`, not `.musx`-only** (see the correction note in
  `docs/superpowers/specs/2026-07-21-version-detection-design.md`, which had claimed otherwise).
  Corpus tally: `MAC` in 136 files, `WIN` in 102.
- Both formats produce the same provenance type, `ProvenanceStamp` (date, application, platform,
  plus `modified_by` and `app_version`) — see the 2026-07-22 "one provenance type for both formats"
  decision in `docs/DECISIONS.md`. `.musx`'s stamps are a strict superset of `.mus`'s: `.mus` always
  leaves `modified_by` and `app_version` at their defaults, `.musx` fills both. `MusxDetail.platform`
  was removed; platform now lives on each stamp, matching `.mus`'s rule that both stamps must not be
  assumed to agree.
- 89 of the 136 `MAC` `.mus` files (0 of the 102 `WIN` files) end in a **macOS plist trailer**
  occupying the last 1-3% of the file (938-1694 bytes) — apparently appended OS-level metadata.
  Not parsed; recorded so the next investigation starts from it.
- **A hypothesis that did not survive testing:** `.mus` was suspected to share `.musx`'s
  record-type numbering (`10001`, `10002`, ...). Scanning all 238 files for those values as aligned
  little-endian `u16` gave occurrence rates close to the chance baseline expected in files dense
  with small integers and zero runs. The hypothesis is **not supported** — recorded here so it is
  not re-derived from the same coincidence.
- `.mus` has **no member table** — it is a monolithic binary with no directory and no confirmed
  record framing, unlike `.musx`. There is no container abstraction to build for it; locating any
  internal record pools remains open-ended research.
- `.musx` is a zip with `mimetype` = `application/vnd.makemusic.notation`. Version data lives in
  `NotationMetadata.xml` as plaintext, with separate `created` and `modified` blocks. **`modified`
  is the layout authority** — 267 of 401 corpus files were created by major=16 but last written by
  major=18, and **370 of 401 diverge between the `created` and `modified` majors at all** (not only
  the 16-to-18 case). (The 2026-07-21 design spec recorded the first figure as 264; a direct corpus
  measurement pinned in
  `tests/version/test_corpus_sweep.py::test_musx_modified_over_created_divergence_still_holds`
  found 267 (and asserts 370 alongside it). The spec is left as originally written per this
  project's practice of not rewriting a spec's history; this figure is corrected here since
  `ARCHITECTURE.md` is the current source of truth.)
- `score.dat` is obfuscated high-entropy data. Version detection never reads it.
- The `.musx` `major` version number (15/16/17/18) has no established mapping to Finale's
  marketing years (2009/2011/2012/2014...). Nothing in the corpus bridges the two schemes, so
  version labels report the raw major/maint/build instead of a year. Open question.
- `scripts/build_version_fixtures.py` strips `NotationMetadata.xml` down to only the root
  `version` attribute and the `created`/`modified` subtrees, building the output tree fresh so any
  field not explicitly listed is absent by construction. Every attribute on every element within
  those subtrees is also stripped (an allowlist of zero attributes — none are read by version
  detection, so none are kept), and every `<modifiedBy>` is blanked rather than dropped. This is
  deliberate: the corpus metadata carries `title`, `subtitle`, `composer`, `arranger`, `lyricist`,
  `copyright` (including a MakeMusic notice restricting commercial redistribution), and
  `modifiedBy` — non-empty in 28 of the 802 `created`/`modified` blocks across the corpus (14
  files), where it holds real people's initials — plus attributes such as `<created author="...">`
  that could carry the same kind of identifying data. `modified_by` is exposed through
  `ProvenanceStamp` for parsing, but every committed fixture's `<modifiedBy>` stays blanked. Do not
  loosen this filter to pass through more fields or attributes.

### Known format facts — the .musx container

Evidence: all 401 corpus archives, surveyed 2026-07-21. See
`docs/superpowers/specs/2026-07-21-musx-container-design.md`.

- A `.musx` is a zip. `mimetype` is always the **first** member and always **stored
  uncompressed** (401/401) — the ODF/EPUB convention. Member order is structural; do not
  assume alphabetical. This is an *observed* fact, asserted of the fixtures and the corpus by
  tests — `open_musx` deliberately does not enforce `mimetype`'s position or its compression
  method, so a future Finale variant that reorders members stays inspectable rather than being
  rejected outright.
- Members observed: `mimetype`, `META-INF/container.xml`, `NotationMetadata.xml`, `score.dat`,
  `presets/<n>.preset`, `graphics/<n>.jpg`. Archives embed images, so container content is not
  limited to notation.
- Member count 5-10; per-archive uncompressed total 89 KB - 420 KB; `score.dat` 86 KB - 413 KB.
- 22 distinct **ordered sequences of member names**. This is measured by name and order only —
  not by (name, size, compress method) — because size and method vary between archives that share
  the same name sequence, which would otherwise inflate the count. Comparing *sorted* name sets
  instead of ordered sequences gives 18 and discards ordering, which is meaningful here: this
  distinction caused a real bug during implementation.
- `score.dat` is high-entropy obfuscated data and barely compresses. It is extracted, never
  interpreted, at this layer.
- No corpus archive has duplicate or unsafe member names, so the reader's safety checks cannot be
  exercised by real files — they are covered by synthetic hostile input and verified by mutation.

### Known format facts — score.dat

Full reference, evidence, and derivation: `docs/formats/score-dat.md`. Headline: `score.dat` is
encrypted with a keystream from a fixed-seed BSD `rand()` linear congruential generator that resets
every 128 KiB; the decrypted plaintext is a gzip stream that inflates roughly 28× into EnigmaXML.
Verified against all 401 corpus archives: 401/401 decode, every result is schema `version="18.0"`.
The cipher parameters are not this project's discovery — see the attribution in
`docs/REFERENCES.md` and the DECIDED entry in `docs/DECISIONS.md`.

### Known format facts — EnigmaXML structure

Full reference and derivation: `docs/superpowers/specs/2026-07-22-enigma-document-design.md`.
Verified against all 401 corpus archives (`tests/enigma/test_document_corpus_sweep.py`).

- The `<finale>` root holds seven pools, always in this order when present: `header`, `mappings`,
  `options`, `others`, `details`, `entries`, `texts`. Any pool may be absent or empty; `parse_enigma`
  models an absent pool the same as an empty one.
- Records are recursive, not typed: `Record` has `tag`, `attrs` (all attributes, verbatim), `text`
  (the element's own direct text), and `fields` (child elements, keyed by local name — a scalar
  `str`, a nested `Record`, or a tuple of either when the tag repeats). A chord's notes are nested
  `note` fields inside an `entry` record — the same recursive rule reaches the musical core with no
  special-cased "note" type.
- Fields nest arbitrarily deep; the corpus and the fixtures both exercise nesting 4 levels deep
  (e.g. `others/widget/layerTwo/layerThree/leafValue`).
- `EnigmaDocument.version` is the **schema** version reported on the `<finale>` root (`"18.0"`
  across the entire corpus), not the writing application's version — that lives in
  `.musx`'s `NotationMetadata.xml`, read separately by `finale_file_parser.version`.
- The `texts` pool carries copyright, title, and composer text (`<fileInfo type="title">…`,
  `<expression>`, `<verse>`). Because of this, **no decoded corpus EnigmaXML is ever committed**;
  `tests/fixtures/enigma/*.xml` are hand-written synthetic documents with invented placeholder
  values, and `tests/enigma/test_fixtures.py` mechanically asserts no committed fixture contains a
  `fileInfo` element at all.
- **No fixed key set uniquely identifies a record** without also tracking `part`: `cmper=1` alone
  spans 54 distinct tags across the corpus, and `measSpec` additionally has per-`part` variants
  that share a `cmper` with the score-level record and with each other, distinguished only by the
  `part` attribute. Dropping any attribute to build a key would silently lose data (verified by
  mutation: removing `part` from the model fails a test). This is why the document model preserves
  every record uniformly (`Pool.of_tag` linear lookup, all attributes kept verbatim) as its
  baseline, with keyed lookup layered on top once the full key-attribute set per pool was mapped
  (below).

### Known format facts — keyed lookup

Full reference and derivation: `docs/superpowers/specs/2026-07-23-enigma-keyed-lookup-design.md`.
Verified against all 401 corpus archives — **3.1 million records, zero collisions**
(`tests/enigma/test_keyed_lookup_corpus_sweep.py`).

Five of the seven pools — `options`, `others`, `details`, `entries`, `texts` — are keyed
subclasses of `Pool` (`OptionsPool`, `OthersPool`, `DetailsPool`, `EntriesPool`, `TextsPool`) that
build an index at construction and add `get`/`all_with` (or `for_entry`) lookup on top of the
inherited `.records`/`.of_tag`. `header`/`mappings` stay plain `Pool` (with a `.record` singleton
convenience) — they hold exactly one record each, so there is nothing to key.

Each pool's full identity, measured exact and unique over the whole corpus:

| Pool | Identity | Records checked |
|---|---|---|
| `options` | tag alone (one record per option type) | 13,691 |
| `others` | tag + `cmper` + `inci` + `part` | 1,739,819 |
| `details` | tag + (`cmper1`+`cmper2` **or** `entnum`) + `inci` + `part` | 1,065,174 |
| `entries` | `entnum` (single tag `entry`) | 228,957 |
| `texts` | tag + `number` **xor** `type` | 67,438 |

- **`part` is Finale's linked-parts discriminant**: a score record (no `part` attribute) plus
  per-part variants (`part="1"`, `part="2"`, ...) share one `cmper` (or `cmper1`/`cmper2`, or
  `entnum`). `get(...)` with `part` omitted addresses the score record; passing `part` addresses
  that specific variant. `all_with(tag, cmper[, cmper2])` returns the whole linked set — score
  record plus every part variant, in document order — so nothing is dropped even though `get`
  itself returns a single record.
- **`get` returns the one exact `Record | None`** for a full identity — safe only because that
  identity is unique across all 3.1M corpus records. `inci` defaults to `0` (Finale's own default
  when the attribute is absent); key arguments normalize to `str` so `get(t, 1)` and `get(t, "1")`
  agree, matching how the model stores every attribute as a string.
- **A duplicate full identity raises `MalformedEnigmaError`** at index-build time, for any of the
  five keyed pools — the index build *is* the uniqueness check. The corpus has zero duplicates, so
  a duplicate identity in a real file would indicate a malformed document; the pool does not
  silently keep one of the colliding records.
- **Cross-pool link resolution — what a `cmper` on one record *refers to* on another pool — is not
  part of this slice.** `get`/`all_with` retrieve a record by its own identity only; following a
  reference to another pool's record is deferred (see Roadmap).

### Known format facts — entries and pitch

Full reference and derivation: `docs/eeppd.txt` (the Enigma Entry Pool description). Verified
against all 401 corpus archives (`tests/enigma/test_music_corpus_sweep.py`): every `entry` in the
corpus reads through `read_entry` without raising.

- `dura` is the entry's **written** note value in Enigma Duration Units (EDU); a whole note is
  4096. It decodes to a base power-of-two `NoteValue` plus a count of augmentation dots — the same
  decomposition notated on the page (e.g. `1536` is a dotted quarter: `1024 + 512`). **Tuplet
  scaling is a separate detail, not modelled here**: a tuplet's written `dura` is the undivided
  note value, not the sounded duration after the tuplet ratio is applied.
- An entry is a **rest** exactly when `numNotes == 0`; `read_entry` raises `MalformedEntryError` if
  `numNotes` disagrees with the actual number of nested `note` fields, so `is_rest ⟺ notes == ()`
  holds by construction rather than by convention.
- Pitch is **not** absolute in the record: `harmLev` is a diatonic displacement from the current
  key's tonic (0 at the tonic's octave, ±7 per octave), and `harmAlt` is an alteration relative to
  that key (0 natural, ±1 sharp/flat), not the accidental actually printed. Recovering an absolute
  spelled pitch (e.g. "F#4") needs the key in force at that point in the score — `harmLev`/`harmAlt`
  alone are key-independent. See `docs/eeppd.txt`'s Note Record section for the bit-level source of
  this fact.
- **This model stops at the cross-pool boundary.** `read_entry` only reads the `entries` pool's own
  fields; it does not resolve the key (which lives elsewhere, reached via
  `gfhold → frameSpec → measSpec` linkage — see Roadmap) needed to spell a pitch absolutely, or the
  tuplet ratio needed to scale a written duration to its sounded length.

## Data flow

<!-- Describe the path of the core operation, input to output, naming the key types. -->

```
.mus  ────────────────▶ parser ──▶ IR ──▶ MusicXML
.musx ──▶ EnigmaXML ──▶ parser ──▶ IR ──▶ MusicXML
```

Both inputs converge on the same IR, so format-specific handling stays inside the readers and never
reaches the exporters. Key types are named here as they are defined.
