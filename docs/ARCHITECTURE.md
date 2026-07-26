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
  typed layer over the generic `entry`/`note` records), `location.py` (`locate_entries`,
  `EntryLocation`, `MalformedScoreError` — the first cross-pool link resolution, placing every
  entry in its staff/measure and computing the raw key signature in force), `key.py` (`decode_key`,
  `KeySignature`, `Mode`, `UnsupportedKeyError` — decodes the raw `keySig.key` integer into fifths,
  mode, and tonic). See "Known format facts — score.dat", "Known format facts — EnigmaXML
  structure", "Known format facts — entries and pitch", "Known format facts — score linkage", and
  "Known format facts — key signatures" below.
- The same package holds the legacy `.mus` readers, which produce the same types from the other
  container: `mus_payload.py` (`read_mus_payload`, `read_mus_streams` — the two eras' codecs),
  `mus_entries.py` (`read_mus_entries` — the entry pool), `mus_others.py` (`read_mus_others`,
  `MusOther` — the `others` pool as tagged, self-identifying records). See the three "Known format
  facts — … `.mus` …" sections below.

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

### Known format facts — the legacy `.mus` payload

Full reference, evidence, and the false starts: `docs/formats/mus-binary-notes.md`. Headline: a `.mus`
file is a plaintext header followed by a **compressed** payload, and the codec depends on the era.

| banner year | files | payload | offset |
| --- | --- | --- | --- |
| 2001–2005 | 139 | single **PKWARE DCL "implode"** stream, `lit=0`, `dict=4` | `0x20A` |
| 2011–2012 | 99 | **chain of consecutive zlib streams**, ~4 per file | first at `0x216` (2 files `0x20A`) |

Verified against every `.mus` in the corpus: **238/238 decode**. Inflation is 0.82×–2.75× for DCL and
5.87×–8.63× for the concatenated zlib chain; decoded payloads run 32,816–699,585 bytes.

Two practical notes that cost real time to learn:

- **Locate zlib streams by header, not by offset.** The preamble ahead of the first stream is
  variable-length. `enigma/mus_payload.py` validates a candidate with zlib's own rule — low nibble 8,
  and the two header bytes a multiple of 31 — rather than matching the literal `78 9c` pair, which
  would miss any file written at another compression level.
- **A raw inflate at an arbitrary offset can hit a DEFLATE *stored* block** and return a verbatim copy
  of its input, which looks exactly like a large successful decode. Any offset-scanning decoder needs
  to reject that explicitly.

The decoded payload is **not** EnigmaXML and is not yet parsed into records; that is the next step.
`docs/eeppd.txt` and `docs/etfspec.pdf` give the record *semantics*, but their ETF field order and
widths do not transfer to the binary layout — see the notes for the two experiments that establish it.

The PKWARE DCL format knowledge is not this project's discovery — see the attribution in
`docs/REFERENCES.md` and the DECIDED entry in `docs/DECISIONS.md`.

### Known format facts — staff names and file info

**A staff does not carry its own name.** `staffSpec.fullName` holds a number, and reaching the string
takes *two* hops:

```
staffSpec.fullName → others.textBlock[cmper] → textID → texts.blockText[number] → the text
```

Going straight from `fullName` to `blockText` resolves **nothing** — all 24 named staves in the sampled
corpus fail that way, because the two numbers live in different spaces. That failure is silent: the
exporter simply falls back to "Staff N", which looks like valid output.

The text is Enigma's tagged markup (`^fontid(9)^size(12)^nfx(0)Voice`) and also carries **inserts** —
`^title()`, `^partname()` — which are placeholders resolved at render time, not literal text.
`plain_text` strips both, so a block consisting only of inserts correctly yields an empty string.

**Most staves are unnamed:** 24 of 84 in the sample carry a name. `staff_names` omits the rest rather
than returning blanks, so a caller can tell "unnamed" from "named blank" and choose its own fallback.

`fileInfo` records in the texts pool hold **title, composer, copyright and description** as literal
strings, with no indirection and no markup.

## The IR and exporters

`docs/DECISIONS.md` (2026-07-20) settles the shape: readers produce a **format-neutral IR**, exporters
consume one, and neither knows the other. The dependency runs one way only:

```
container ──▶ enigma ──▶ enigma/to_ir ──▶  ir  ◀── export/musicxml
                                          (knows nobody)
```

`finale_file_parser/ir.py` imports nothing from `enigma` or `container`. A `.mus` reader added later
produces the same `Score` and every exporter keeps working — which is the whole point of paying for the
extra hop rather than exporting from `EnigmaDocument` directly.

The decision's other consequence shapes the types: **MusicXML's limits must not constrain the IR.**
Durations are exact `Fraction`s of a whole note, not MusicXML integer divisions, and a `Voice` keeps its
source layer number rather than a MusicXML voice index. The exporter picks a divisions value per part by
taking the LCM of the durations' denominators — a triplet eighth is 1/12 of a whole note, so a
power-of-two divisions count truncates it to zero.

**Naming collision worth knowing about:** `ir.TimeSignature` and `enigma.timesig.TimeSignature` are
different types — conventional beats/beat-type versus Enigma's beats/division-EDU. The IR types are
deliberately *not* flattened into the package root for that reason; import them from
`finale_file_parser.ir`.

### Known format facts — clefs

Enigma keeps a document-wide table of clef definitions (`clefOptions.clefDef`, **18 entries in every
corpus document**) and refers to them by index. Two things carry an index:

- `staffSpec.defaultClef` — the staff's clef. **Omitted when it is 0**, so an absent field means
  treble, not "missing"; skipping those staves would drop every treble-clef staff.
- `gfhold.clefID` — the clef at that (staff, measure). Present on **every** corpus `gfhold`
  (4,214/4,214), so it is the *effective* clef rather than only a change marker, and unlike the key
  signature there is **no inheritance to apply**.

A definition gives a Maestro font character plus placement, or — when `isShape` is set — a `shapeID`
and no character. The two are mutually exclusive.

`ClefSign` derives the kind from the character: 38 (`&`) → G and 63 (`?`) → F are **confirmed by
use**; 66 (`B`) → C appears in the table but no corpus staff selects it, so it is inferred from the
font. Shape clefs report `SHAPE` (percussion, in practice) rather than being guessed into a sign, and
anything unrecognised stays `UNKNOWN`. Across the sampled corpus every measure resolves to G, F or
SHAPE — no UNKNOWN — over clef indices 0, 3 and 16 only.

### Known format facts — time signatures

Enigma stores no numerator and denominator. A `measSpec` carries **`beats`** (how many divisions the
measure has) and **`divbeat`** (how long each division is, in EDU). That is how compound meters fall
out naturally: 6/8 is *two dotted-quarter divisions*, stored as `beats=2, divbeat=1536`, not six
eighths.

`TimeSignature` keeps that representation and derives the conventional pair. A division that is three
times a power of two is compound, so the numerator multiplies by 3 and the denominator comes from the
undotted unit. Reporting `beats` directly as the numerator would call 6/8 "2/8".

Every one of the 2,622 corpus `measSpec` records carries both fields, so unlike the key signature
there is **no inheritance to apply**. Signatures observed: 4/4, 3/4, 2/4, 2/2, 6/8, 9/8, 3/8, 1/4, 1/8.

**A display time signature is only valid when `useDisplayTimesig` is set.** `dispBeats` and
`dispDivbeat` are present on *every* measure but hold a default when the flag is clear — reading them
unconditionally reports a display signature for 1,937 of 2,622 measures that do not have one, usually
claiming 4/4 over a bar that is really 3/4. Only 76 measures genuinely set the flag.

### Known format facts — layers

A `gfhold` holds up to four frames, which are Finale's **layers**. `EntryLocation.layer` records which
slot placed an entry (1–4).

**Each layer independently fills its measure**, so anything summing durations must group by
`(staff, measure, layer)`. Grouping by `(staff, measure)` alone makes a two-layer measure appear to
hold exactly twice its time signature — measured on the corpus, 78 measures at exactly 2× and 4 at
exactly 3×, matching their layer counts.

With layer grouping, **1,420 of 1,423 layer-measures sum to exactly their time signature** once tuplet
scaling and grace notes are applied, against 1,248 of 1,333 without it. The 3 that remain sit *below*
capacity (5/6, 1/2) — a layer holding fewer notes than the measure allows, which is ordinary notation.

Layers are distinct from Finale's **voice 1 / voice 2** within a layer (`eeppd.txt`'s `CNTLRBIT`
"V2 launch" and `CNTLBIT`). No voice-2 marker has been located in EnigmaXML entry records yet, and the
measure sums above do not require one, so it remains unmodelled.

### Known format facts — the `.mus` entry pool

`read_mus_entries(path)` returns the same `Entry`/`Note`/`Duration` objects the `.musx` path builds,
so `spell_note`, `decode_key` and the rest attach unchanged. Layout is Coda's, from `docs/eeppd.txt`,
confirmed field-by-field against paired `.musx` files.

The pool is a flat array of fixed **38-byte slots**, each tagged with the entry it belongs to:

```
0-3   entnum        the entry this slot belongs to
4-5   slot index    0 for an entry's first slot, then 1, 2, ...
6-37  payload
```

First slot: `prev(4) next(4) dura(2) pos(2) flag(4) extflag(2) count(2)` then two note records.
Continuation slots carry five more notes each, from offset 6. A note is `TCD(2) + flag(4)`.

Three details that are easy to get wrong, each caught by comparing against ground truth:

- **The TCD's alteration nibble is sign-and-magnitude**, bit 3 being the sign — not two's complement.
  `eeppd.txt` calls it "a signed quantity … -8 to +7", which reads as two's complement; under that
  reading `0x9` decodes to −7 where the corpus says −1.
- **`FLOATREST` decides whether an entry has pitch content, not `NOTEBIT`.** A floating rest stores a
  placeholder note with a count of 1; a rest dragged off the midline clears `FLOATREST` and stores a
  *real* note record for its vertical position. Using `NOTEBIT` misclassifies 74 corpus entries.
- **Notes do not run at a fixed stride from the entry start.** Note 3 onward lives in the next slot,
  after that slot's own 6-byte tag.

Verified across every 2011/2012 `.mus` with a confirmed `.musx` pair — **30,420 entries**: entry
numbers, durations and rest flags all agree exactly, and note pitches agree on every document without
a transposing staff.

**Transposing staves place `harm_lev` in a different octave.** On a staff with a transposition, the
two containers disagree by whole octaves, and `harm_lev_octave_shift(interval)` converts a `.mus`
value to the `.musx` convention. Measured across every confirmed pair, 30,891 notes over seven
distinct transpositions:

| staff transposition interval | shift |
| --- | --- |
| 0, 1, 4 | 0 |
| 5, 7, 8 | −7 |
| 12 | −14 |

i.e. `-7 * ((interval + 2) // 7)`. **The boundary is the surprising part** — the octave moves at
interval 5, not 7 — so a plain "divide by 7" passes the 0/7/12 cases and silently breaks 5 and 8. The
rule is empirical; *why* it breaks at 5 is not understood.

`read_mus_entries` does not apply it, because the entry pool carries no staff information — the
transposition lives in the `others` pool, which is not yet readable from `.mus`. Apply it where the
staff is known.

With the shift applied, 30,888 of 30,891 notes agree exactly. The three that do not are pinned in the
corpus sweep: one entry stores two notes in `.mus` and one in `.musx` with an adjacent entry off by an
octave (a revision made to the `.musx` afterwards), and two notes on one octave-transposed staff are
off by a single step, cause unknown.

**Scope:** the 2011/2012 era, where each pool is its own zlib stream; 97 of 99 corpus files place the
entry pool in a standalone stream and the other 2 lay the payload out as three streams rather than
four. DCL-era files (2001–2005) pack every pool into one stream with no known delimiters. Both
unsupported cases raise `CorruptScoreError` rather than guessing.

### Known format facts — the `.mus` others pool

`read_mus_others(path)` returns every `others` record as a `MusOther(tag, cmper, part, payload)`.
The pool is a flat run of **self-identifying, variable-length records**: each carries its own key, so
addressing one needs nothing outside it. Little-endian:

```
0-1    tag       record type (numeric; .musx names the same types)
2-3    cmper     the (n) in an ETF ^XX(n)
4-5    part      0 for the score, then 1, 2, ... per linked part
6-9    length    payload size in bytes
10-    payload   `length` bytes, then a four-byte trailer
```

so one record occupies **`14 + length`** bytes. Records of one tag sit together in a section, and
sections may be separated by two-byte zero padding.

**This answers the long-open `cmper` question.** There is no directory, no key array and no
positional convention, and the search for them failed for a mundane reason: every earlier attempt
located a section by searching for payload values known from the paired `.musx` and then read
*forward*, while the key sits ten bytes *behind* that anchor. Two ~95% near-misses came from reading
the neighbouring record's header as part of the anchored one. See `docs/formats/mus-binary-notes.md`
for the full account, the retractions it forces, and the candidate tag-id table.

Verified against paired `.musx` files. The walk tiles stream 1 exactly in **84 of 91** pairs
(211,554 records), and on same-content pairs:

| check | result |
| --- | --- |
| `frameSpec` (tag 146) `(cmper, part)` sequence | 76 of 77 documents exact |
| `frameSpec` `startEntry`/`endEntry` payload | 7,919 of 7,922 records |
| `measSpec` (tag 176) `beats`, `divbeat` payload | 3,799 of 3,799 records |
| `measSpec` `width` payload | 3,750 of 3,799, every miss in one document |

`width` is layout, not music: re-spacing a score between the two saves changes every measure width
and no `beats`/`divbeat`. Only these two tags are confirmed by payload content; the rest of the tag
table is key-sequence matching and is recorded as leads.

**Scope and refusals.** The 2011/2012 era only, as with the entry pool. Seven corpus documents halt
part-way through one record type whose length field the walk mis-reads; `read_mus_others` raises
`CorruptScoreError` for those rather than returning a truncated pool, because a partial pool is
indistinguishable from a complete one at the call site.

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
  `gfhold → frameSpec → measSpec` linkage, now done by `location.py` — see "Known format facts —
  score linkage" above and Roadmap) needed to spell a pitch absolutely, or the tuplet ratio needed
  to scale a written duration to its sounded length.

### Known format facts — score linkage

Full reference and derivation: `docs/superpowers/specs/2026-07-23-entry-location-design.md` and
`docs/superpowers/plans/2026-07-23-entry-location.md`. Verified against all 401 corpus archives
(`tests/enigma/test_location_corpus_sweep.py`): every entry in the corpus is located exactly once.

- **An entry names no staff, measure, or key of its own.** Reaching them needs a chain across three
  pools: a `details` `gfhold` (`cmper1` = staff, `cmper2` = measure) holds up to four frame fields
  `frame1`..`frame4` — Finale's layers/voices; each present field is a `frameSpec` (`others`)
  `cmper`. A `frameSpec`'s `startEntry` begins the `entries` pool's own `next`-chain (each entry's
  `next` **attribute**, not a field) that walks forward to `endEntry`, and that chain *is* the
  entry's placement — the entry never carries its own staff/measure. An `others` `measSpec`
  (`cmper` = measure) carries the `keySig` (a nested `{key: <int>}` record) in force for that
  measure.
- **All four frame slots must be resolved**, not only `frame1` — 299 of 6,332 corpus `gfholds` carry
  `frame2`/`frame3`, and skipping them leaves layer-2+ entries unlocated. An absent, empty, or `"0"`
  frame slot is an unused layer, not a broken link — Finale usually omits it, but Enigma may also
  write `"0"`; either way it names no `frameSpec` and is skipped.
- **A frame `cmper` can resolve to more than one `frameSpec` *incidence*.** `others`' identity is
  `tag + cmper + inci + part`, and 73 of 67,558 corpus frame cmpers (20 of 401 files) carry two
  incidences — `inci="0"` and `inci="1"` — where exactly one carries `startEntry`/`endEntry` and
  the other has neither (only unrelated fields, e.g. `startTime`). `OthersPool.get` defaults to
  `inci=0`, which for these 73 is the *empty* incidence — resolving a frame must use
  `all_with(tag, cmper)` (every incidence sharing that cmper) and walk whichever one(s) actually
  carry a chain, not just the default. An incidence with neither `startEntry` nor `endEntry` is a
  legitimate empty layer; one with only one of the two is still malformed.
- **The key is per measure, and inherited**: not every measure carries a `keySig` (449 of 2,622
  omit it in the corpus survey) — a measure without one inherits the effective key of the prior
  measure, computed by walking measures in `cmper` order and carrying the last seen `keySig.key`
  forward (a measure before the first `keySig` defaults to `0`).
- **The key is exposed RAW (an `int`), not decoded — decoding it is a separate slice.** The
  standard scheme is fifths-style: a signed accidental count, e.g. `-1` = F major (one flat), `+2`
  = D major (two sharps). Decode hints and traps to carry into that slice: enharmonic equivalents
  (e.g. C# major vs. Db major) are **distinct** key values, not the same one spelled two ways; a
  raw signature alone does **not** fix major vs. minor (relative major/minor share a signature);
  and a transposing instrument's written key differs from concert pitch — the raw value is
  whatever is written for that staff/part, not necessarily concert.
- **This is the first cross-pool link resolution** — earlier slices (keyed lookup, typed entries)
  only retrieve a record by its own identity; `locate_entries` is the first to follow what a
  `cmper` on one record *refers to* on another pool. `MalformedScoreError` (distinct from
  `MalformedEnigmaError`) covers a broken chain: an entry no frame places (an orphan), a frame
  pointing at a missing `frameSpec`, a non-integer `keySig.key`/`startEntry`/`endEntry`, an entry
  placed by more than one frame, or a `next`-chain that exceeds a cycle guard.

### Known format facts — key signatures

Full reference and derivation: `docs/superpowers/specs/2026-07-24-key-decode-design.md`. The
encoding is documented nowhere read; it was reverse-engineered from the corpus and verified against
all 401 archives (`tests/enigma/test_key_corpus_sweep.py`), decoded by `enigma/key.py`.

- **Encoding:** `key = (mode << 8) | (fifths & 0xFF)`. The **low byte, signed**, is `fifths` — the
  accidental count, sharps positive, flats negative, the MusicXML convention (`+2` = D major, `-1`
  = F major). The **high byte** is `mode`: `0` = major, `1` = minor.
- **Corroboration** (the encoding is inferred, so the evidence matters): all 13 distinct corpus raw
  values decompose to `mode ∈ {0,1}` and `fifths ∈ [-7,7]` with no remainder; `keySig` carries no
  field but `key`, so mode has nowhere to live but that integer; the scheme matches MusicXML, which
  Finale exports; and deriving the tonic from (fifths, mode) via the circle of fifths reproduces
  music theory for every value (`-3` major → E♭; raw `256` → A minor).
- **Inferred vs proven:** `mode = 1` → minor is **inferred**, not proven — no corpus file's key is
  independently known; the inference rests on the bit pattern, minor being the common second mode,
  and the high-byte-1 values being ordinary minor keys. The `±6`/`±7` enharmonic keys are modelled
  (the signed byte covers them, and `+6` = raw byte 6 vs `-6` = raw byte 250 stay distinct) but
  **unseen** — the corpus exercises only fifths `-5…+3`.
- **`decode_key` raises `UnsupportedKeyError`** on `mode ≥ 2` (a church mode or custom/linear key we
  have not reverse-engineered) or `fifths` outside `-7…+7`, including a negative raw value — rather
  than guess, since a wrong key would silently misspell every pitch that resolves through it. The
  corpus has 0 such values.

### Known format facts — pitch spelling and transposition

Full reference and derivation: `docs/superpowers/specs/2026-07-24-pitch-spelling-design.md`. Turns
`decode_key` (tonic + fifths), `read_entry`'s `harm_lev`/`harm_alt`, and a staff's transposition into
an absolute spelled pitch (letter + accidental + octave), for both the **written** (what a player
reads) and **concert** (sounding) pitch. Implemented in `enigma/pitch.py`; verified against all 401
corpus archives, and against the 50,024 transposing-staff notes surveyed during design (every one
spells with 0 invariant violations — see below).

- **`harm_lev` is a diatonic scale degree** from the key's tonic, octaves included (`harm_lev = 0` is
  the tonic nearest middle C; `+7` is one octave up). **`harm_alt` is a chromatic alteration**
  relative to what the key signature already dictates for that letter (`0` = follow the key; e.g.
  F♮ in D major is `harm_lev = 2, harm_alt = −1`).
- **Spelling rule:** tonic letter + `harm_lev` → letter and octave (`LETTERS = "CDEFGAB"`, C-indexed
  so the octave boundary falls at C, as scientific pitch requires); the key's accidental for that
  letter (from the sharp order `F C G D A E B` or flat order `B E A D G C F`) + `harm_alt` →
  alteration.
- **Transposition is stored on `staffSpec.transposition.keysig`** as two signed integers:
  `interval` — diatonic steps the **written** pitch sits above concert (`0` = unison, `7` = an
  octave) — and `adjust` — the **written** key signature's shift on the circle of fifths (sharps
  positive). The written key is the concert key with `fifths += adjust` (mode unchanged, tonic
  re-derived). The concert pitch is the written pitch dropped `interval` diatonic steps and
  `T = ((7 · adjust) mod 12) + 12 · (interval ÷ 7)` semitones (a key-signature shift of `adjust`
  fifths moves the tonic `(7 · adjust) mod 12` semitones; the `12 · (interval ÷ 7)` term accounts
  for whole-octave transpositions). For a concert (non-transposing) staff (`interval = 0, adjust =
  0`) this is the identity.
- **Corroboration** (the `interval`/`adjust` decode is inferred, so the evidence matters): six
  distinct non-zero corpus signatures all reproduce a textbook instrument's transposition exactly —

  | `interval` | `adjust` | interval above concert | instrument |
  |---|---|---|---|
  | 1 | 2 | major 2nd (+2 sharps) | B♭ trumpet / clarinet |
  | 4 | 1 | perfect 5th (+1 sharp) | F horn |
  | 5 | 3 | major 6th (+3 sharps) | E♭ alto sax |
  | 8 | 2 | major 9th (+2 sharps) | B♭ tenor sax |
  | 12 | 3 | major 13th (+3 sharps) | E♭ baritone sax |
  | ±7 | 0 | octave (`noKeyOpt`) | bass / piccolo family |

  The octave rows (`interval = ±7, adjust = 0`) anchor `interval` as diatonic steps (7 = an octave)
  and `adjust` as a key shift that is 0 for a pure octave; "each added sharp is a perfect fifth" (a
  key shift of `adjust` fifths moves the tonic `(7 · adjust) mod 12` semitones) then reproduces every
  other row. The written-storage argument: `measSpec` carries a single **concert** key per measure
  (keyed by measure only, shared across every staff), so the written key is never stored directly —
  it must be derived by transposing the concert key, which is only meaningful if the stored
  `harm_lev`/`harm_alt` are the written pitch relative to the written key.
- **Inferred vs proven:** as with `mode = 1 ⇒ minor` in `decode_key`, **the instrument decode and the
  written-storage claim are inferred but strongly corroborated, not proven** — no corpus file's
  instrument or stored-pitch convention is independently known; the confidence rests on six distinct
  signatures all landing on real instruments, the octave anchor, the fifths-to-semitones law, and
  Finale's documented behaviour of storing written pitch.
- **`noKeyOpt` appears only on octave transpositions** (where `adjust = 0` already leaves the key
  signature unchanged) and **`setToClef` is display-only**; `read_transposition` does not consume
  either flag.

## Data flow

<!-- Describe the path of the core operation, input to output, naming the key types. -->

```
.mus  ────────────────▶ parser ──▶ IR ──▶ MusicXML
.musx ──▶ EnigmaXML ──▶ parser ──▶ IR ──▶ MusicXML
```

Both inputs converge on the same IR, so format-specific handling stays inside the readers and never
reaches the exporters. Key types are named here as they are defined.
