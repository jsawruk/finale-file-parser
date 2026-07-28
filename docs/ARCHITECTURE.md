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
  `MusOther` — the `others` pool as tagged, self-identifying records), `mus_details.py`
  (`read_mus_details`, `MusDetailRecord` — the `details` pool, the same shape with a two-cmper key),
  and `mus_document.py` (`read_mus_document` — the adapter that turns those pools into an
  `EnigmaDocument`, which is what lets one IR builder and one exporter serve both containers). See
  the "Known format facts — … `.mus` …" sections below.

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

### Known format facts — the `.mus` details pool

`read_mus_details(path)` returns every `details` record as a
`MusDetailRecord(tag, cmper1, cmper2, inci, payload)`. The pool has the **same shape as `others`** and
differs in exactly one way, for the obvious reason — a `details` record is keyed by a *pair* of
cmpers, so its header carries one more field:

```
0-1    tag       record type (numeric; .musx names the same types)
2-3    cmper1    first key component (staff, for gfhold)
4-5    cmper2    second key component (measure, for gfhold)
6-7    inci      incidence — identified by position only, see below
8-11   length    payload size in bytes
12-    payload   `length` bytes, then a four-byte trailer
```

so one record occupies **`16 + length`** bytes, against the `others` pool's `14 + length`.

`gfhold` (**tag 1044**) is why this pool matters: it ties a measure on a staff to the entry frames
that fill it. Its 20-byte payload holds `clefID` at +0, `clefPercent` at +4 and `frame1` at +6.

Verified against paired `.musx` files. The walk tiles stream 2 exactly in **84 of 91** pairs
(167,463 records), and on the 80 same-content pairs carrying `gfhold`:

| check | result |
| --- | --- |
| `gfhold` key sequence | 80 of 80 documents — the `.musx` sequence restricted to the keys `.mus` holds |
| `clefPercent` at payload +4 | every record |
| `frame1` at payload +6 | every record |
| `clefID` at payload +0 | 8,110 exact, 272 defaulted (below), **0 unexplained** |

**`.mus` writes `clefID` 0 for "use the staff's `defaultClef`"**, and a `.musx` export materialises
the resolved clef into the record. This refines the earlier note that every `gfhold` carries a
`clefID` with no inheritance — true of `.musx`, not of `.mus`.

**`inci` is named by position, not evidence.** It sits exactly where Enigma's third key component
belongs, but it is zero in all 77,384 corpus records examined and no corpus document repeats a
`(tag, cmper1, cmper2)` key, so nothing yet distinguishes an incidence counter from a reserved
field. The reader keeps the value rather than dropping it.

Locating `gfhold` cost a third repeat of the same mistake: the previously recorded offsets (staff at
+20, measure+1 at +22, both ~160/164) were the **next record's key pair**, read from an anchor that
sat 16 bytes inside the record. See `docs/formats/mus-binary-notes.md`.

### Known format facts — reading a `.mus` as an EnigmaDocument

`read_mus_document(path)` translates the `.mus` pools into the `Record` model `parse_enigma` builds
from a `.musx`, so every module over that model reads a `.mus` unchanged. `read_mus_entry_records`
is the same idea one level down: the entry pool's primitive is now a `Record`, and
`read_mus_entries` is that composed with `read_entry` — one decode of entry semantics, not one per
container.

**It is an MVP and translates only the record types whose payloads are decoded**: `frameSpec`
(startEntry, endEntry), `measSpec` (keySig.key, beats, divbeat), `gfhold` (clefID, frame1, frame2),
`clefOptions` (the clef table), `tupletDef`, and entries. A record type it does not understand is **absent** from the document rather than
present and wrong. `enigma.UNTRANSLATED` names each remaining gap and its consequence.

**The clef table** comes from `others` tag 109 under cmper `0xFFFE`, Enigma's sentinel for a
document-wide option. Its entry stride is set by the banner year — 2011 uses 18 bytes, 2012 uses 20
and moves `clefYDisp` and `shapeID` — which is the same era split `mus_payload` uses to choose a
codec. All four fields match the paired `.musx` on 1,512 of 1,512 entries. Deriving the stride from
the payload length instead would be ambiguous: 324 and 360 are both divisible by 18 and 20, and
reading a 360-byte table as 20 entries of 18 rather than 18 of 20 puts every field two bytes out.

Three translations are omissions rather than values, and all three matter:

- **A `measSpec` key of 0 becomes no `keySig` element at all.** An absent key means "inherit the
  previous measure's"; writing `key="0"` would silently make every inheriting measure C major.
  Verified: a `.musx` never writes `key="0"`, and `.mus` stores 0 exactly where the `.musx` omits it.
- **A `gfhold` frame of 0 is an empty layer and is omitted**, rather than sending `locate_entries`
  after a `frameSpec` numbered 0.
- **A clef entry's `clefChar` or `shapeID` of 0 is omitted**, because absent means "there is no
  character/shape" — which is what makes `Clef.sign` report UNKNOWN or SHAPE instead of inventing a
  G clef.

**Validation is IR against IR** — the same document built from both containers, compared field by
field (`tests/enigma/test_mus_to_ir_corpus_sweep.py`). Over 81 same-content pairs:

| result | count |
| --- | --- |
| parts, measures and events, one for one | **no differences** |
| key signatures and time signatures | **no differences** |
| written duration, dots, ties, grace notes | **no differences** |
| sounded duration and tuplet ratio | **no differences** |
| pitch | 4,140 differ; 4,138 on transposing staves (`staffSpec` untranslated), 2 are known content revisions |
| clef | 22 measures differ, all instrument-derived (see below); was 327 before the clef table was decoded |

The structural row is the load-bearing one: a difference there would mean entries placed in the
wrong measure, which produces plausible output nobody notices.

**Every remaining difference is instrument-derived**, and there is no instrument table to find: only
two record types are keyed per staff in the whole `.mus` (`staffSpec` and `gfhold`), so there is no
third place for one to hide. The `.musx` materialises these values from its `instUuid`, which has no
`.mus` counterpart.

The transposition's **key alteration** is recovered (`staffSpec` +20, low nibble, sign-and-magnitude
as `eeppd.txt` documents for a note TCD), and that is all the *written* pitch needs — `transpose_key`
uses `adjust` alone. So every note letter and accidental is now right, and only the octave is wrong,
on exactly the staves where `harm_lev_octave_shift` is non-zero. The **`interval` is left absent**,
which is correct for the written pitch and wrong for the concert pitch `spell_note` returns
alongside it: a `.mus` cannot supply that.

**Why it cannot.** Finale normalises a staff's transposition into a residue of −4..+2 and keeps the
octave count separately; the `.mus` stores only the residue, so intervals 0 and 7 both store
`0x0000`, 1 and 8 both `0x0042`, 5 and 12 both `0x0F83`. The octave is absent from the file rather
than hidden in it — which is also why `harm_lev_octave_shift`'s boundary sits at interval 5: its
`+ 2` is the normalisation boundary, not a fitted constant. See `harm_lev_octave_shift` and
`docs/formats/mus-binary-notes.md`.

`tupletDef` (details tag 1072) is keyed by **entry**, not by a (staff, measure) pair: entry-attached
details pack the 32-bit `entnum` into the two key fields, high word first. Its four fields all have
a single value corpus-wide, so the layout rests on ETF's field order plus the end-to-end duration
check rather than on an offset sweep.

One document fails to build: its `.mus` frame chain references an entry its pool does not hold. It
is the same document whose `.musx` carries three `frameSpec` records its `.mus` does not, so the two
containers disagree about its frames rather than the adapter mis-reading them.

### Known format facts — the reserved staff 32767

Every corpus document declares a staff numbered **32767** (0x7FFF, the sentinel the format also uses
for "to the end" in `staffGroup.endMeas`). It is real data — its own `staffSpec`, a `gfhold` per
measure, its own entries — but it is not part of the score:

| check | result over 401 documents |
| --- | --- |
| in the score's instrument list (`instUsed`) | never |
| named by a staff group | never |
| distinct `staffSpec` bodies | **two**, all with one fixed `instUuid` |
| display features | one-line `customStaff`; clefs, key signatures, measure numbers, repeats and repeat barlines all hidden |
| its music | a single repeated pitch in 376 of 398, always layer 1, never a lyric |
| entries shared with a real staff | none — disjoint in all 401 |

It is also the only staff in the corpus absent from the instrument list. `build_score` therefore
makes no part for it; see `docs/DECISIONS.md` for why the exclusion is by staff id rather than by
absence from the list (a `.mus` has no such list, and the containers must agree). What Finale uses it
for is **not** established — a hidden one-line staff of repeated quarter notes would fit a click
track, rhythmic notation or a chord-symbol carrier equally well.

Its entries are still placed by `locate_entries`, so nothing below the IR is lost.

### Known format facts — staff groups

A `staffGroup` detail record spans a run of staves and says how they are joined — the braces and
brackets down the left edge of a score. Its field order is **documented**: `etfspec.pdf` describes
the ETF `NG` record as `startInst endInst fullNameID fullXadj fullYadj | bracketType bracPos bracTop
bracBot bracFlag | flag abrvNameID …`, and the `.mus` binary lays those out in exactly that order.
Six offsets were confirmed independently against the paired `.musx`, each with one candidate, and
each landed where the spec predicts.

**`startInst` and `endInst` are staff numbers, not slots in the instrument list.** The two readings
agree wherever a document numbers its slots and staves alike, which is most of them; the 31 corpus
documents where they differ are the ones that decide, and there all 75 groups name a staff.

The staves a group covers are the run **in instrument-list order** (`instUsed`), not the numeric
range between its endpoints. Those differ in 14 of 230 corpus groups, because a score may lay its
staves out in an order its staff numbers do not follow.

Bracket shapes are an enum with partial evidence:

| id | reading | evidence |
| --- | --- | --- |
| 3 | `brace` | `etfspec.pdf`: "bracket type: 3 (piano brace)". All 132 span exactly two staves, none nests, none is named. |
| 6 | `bracket` | The only id that ever contains another group (14 of 78), the only one spanning more than two staves (34 of 78), the only one carrying a name (31 of 78). |
| 8 | *unmapped* | All 20 sit nested inside another group and none is named — a sub-group marker, but MusicXML's `square` and `brace` are both consistent with that. |

The id-6 argument is about the grammar of a score rather than what this repertoire contains: a brace
cannot span five staves or wrap another group, and a bracket can. Id 8's groups are still exported,
with their extent and barline; only the symbol is withheld.

`groupBarlineStyle` is `group` where barlines run through the whole group and absent otherwise; only
the positive is read. In a `.mus` it is bit `0x0400` of the flag word at +20 — the only exact
candidate against the paired corpus, and independently the bit `etfspec.pdf`'s worked example sets
when it reads `flag: 1088 = 0x0440 (barline through all staves…)`.

Corpus: 209 group records, 201 reaching the IR across 155 documents. The 8 that do not are groups
whose staves are not contiguous once parts are ordered by staff number — `build_score` orders parts
numerically, so bracing them would join a run of parts the score does not group. Ordering parts by
the instrument list instead would fix those 8 and is a change to every part's position, so it is its
own slice.

`.mus` gaps: the instrument list itself is unidentified (**no** paired document distinguishes a
right guess from a wrong one, since all of them number slots and staves alike), so staves fall back
to numeric order; and a group's name resolves through the `textBlock → blockText` chain a `.mus`
does not supply, the same missing chain as staff names.

### Known format facts — repeats

Repeats live in two places at once, and reconstructing one bracket needs both.

The **barlines** are flags on `measSpec`: `forRepBar` means a forward repeat at that measure's left
barline, `bacRepBar` a backward repeat at its right. Nothing else is stored about a forward repeat —
it is only ever a barline. A backward one also gets a `repeatBack` record keyed by measure, whose
`actuate` is Finale's "Total Passes"; the corpus has 25 measures where it is not the default 2.

The **endings** need three records and one flag:

| what | where |
| --- | --- |
| the bracket opens here | `repeatEndingStart(measure)` |
| which passes it is taken on | `repeatPassList(measure)` → one `act` per pass |
| how far it extends | `measSpec.barEnding` |

That last one does not mean what it looks like it means. **`barEnding` is not set on every measure a
bracket covers**: in a four-measure first ending the corpus flags the first measure and the fourth
and leaves the two between them clear. So a bracket runs to *the last flagged measure at or after
its start and before the next bracket starts* — not to the end of a run of consecutive flags.
Reading it as a run stops a four-measure bracket after one measure, and without the next-start
boundary a bracket swallows the ending that follows it.

The rule was checked against the two independent things that ought to agree with it: the measure
carrying the backward repeat (71 brackets, no disagreement) and `nextEnd` where a
`repeatEndingStart` supplies one. The other 67 brackets are single measures with no backward
repeat — a final "2." ending, which MusicXML closes with `discontinue` rather than `stop`.

Corpus: 109 forward repeats, 121 backward, 142 brackets, across 109 documents. Each matches the raw
element count in the pool exactly, so nothing is invented or lost on the way to the IR.

In a `.mus` all three flags sit in **one byte at `measSpec` +10**, on adjacent bits — `barEnding`
0x02, `bacRepBar` 0x04, `forRepBar` 0x08. Each was found by testing every (byte, bit) in the payload
against the paired `.musx`: each has exactly one candidate agreeing on all 1,025 measures of the 20
paired documents that use repeats. That they land on three adjacent bits of one byte is the
corroboration the correlation alone would not give. The byte's high nibble is the barline style
(1 normal, 2 double), **not read**: the paired corpus holds 11 double barlines and no final one,
which is too thin to commit to. The records are tags **203** (`repeatBack`), **204**
(`repeatEndingStart`) and **206** (`repeatPassList`); 204 and 206 share a key set, and the payload
separates them — 206 is 12 bytes opening with the pass number, 204 is 24 bytes of bracket geometry.

Not read, deliberately: `repeatBack.target`, `trigger`, `action`, and the `textRepeatAssign` family
(D.C., D.S., Fine, To Coda). Those describe *jumps* rather than repeat barlines and MusicXML spells
them differently. `repeatEndingText` — a bracket's custom label, used by three corpus documents — is
also unread; the text is derived from the pass numbers instead.

### Known format facts — beams

**Enigma does not store beams.** It stores one bit per entry — `BEATBIT` in `eeppd.txt`, surfaced by
EnigmaXML as a `beam` field — meaning *this entry starts a beam group*. Everything else follows from
the durations: consecutive beamable entries belong to the group opened by the last entry carrying
the bit.

Confirmed against the corpus: a measure of eight eighth notes carries the bit on the first and the
fifth — exactly two groups of four. It matches the `.mus` `BEATBIT` on 30,819 of 30,820 paired
entries, the one exception being the `.mus`/`.musx` revision the entry-pool sweep already pins.

`enigma/beams.py` turns that into what MusicXML asks for, which is more: each note carries one
`<beam>` per level — an eighth has one, a sixteenth two — saying whether that level begins,
continues or ends there. Where a level covers a single note the beam becomes a **hook**, the stub on
the sixteenth of a dotted-eighth pair; it points forward if the note opens the group and backward
otherwise. 93% of corpus groups are one duration throughout and need no hooks; the other 6.6% are
why they exist.

Three decisions worth knowing. Dots are divided out before counting beams, so a dotted eighth (3/16)
beams once like the eighth it is. A group of one gets **no** beam, because a lone eighth is written
with a flag. And a rest breaks a group — MusicXML can beam over one, but Enigma's bit says where
groups *start*, not where they survive a rest, so that is the reading the data supports.

Because beams are computed rather than stored, the two containers agreeing (30,072 of 30,074 events)
shows they feed the same bit and the same durations into the same rule.

### Known format facts — articulations

Two records again. An `articAssign` entry detail names an `articDef`, and the definition says what
the mark is — not by name, but as a **character in a music font**:

```
articAssign(entnum) -> articDef -> charMain
```

So the meaning comes from the character, as `clef.py` reads a clef from `clefChar`. Five characters
sit at the same ASCII positions in every music font the corpus uses — Maestro, Engraver Font Set and
Broadway Copyist all write `.` staccato, `>` accent, `-` tenuto, `^` marcato, `,` breath mark — which
is what makes reading them without resolving the font defensible.

**Anything else produces nothing.** The corpus assigns 29 distinct characters; emitting a guess would
put a wrong articulation on a real note, which is worse than leaving the note bare. Coverage is
22,821 marks across 273 documents.

**Fingerings are deliberately not read.** The corpus carries numerals 1–5 in a text font (Arial),
which are fingerings rather than articulations — but telling those from a music-font numeral needs
the font, and a `.mus` does not reliably give one (`fontMain`'s offset varies within a single era).
Reading them would make the two containers disagree.

On the `.mus` side: `articAssign` is details tag 1009 with the definition's cmper at payload +0;
`articDef` is others tag 121 with `charMain` at +0 (2011, 48-byte payload) or +2 (2012, 60-byte) —
the same era split as the clef table. A `.mus` sometimes **repeats** an assignment, on 23 corpus
entries; no `.musx` ever assigns the same `articDef` twice in 11,404 assignments, so the repeat is a
storage artifact its reader drops. Both containers then agree on all 27,155 events of the 72 paired
documents that carry articulations.

### Known format facts — lyrics

Enigma splits a lyric in two, and neither half is much use alone.

- **Text**: one blob per verse in the `texts` pool, syllabified with hyphens
  (`An-gels we have heard on high`). Tag `verse`, `chorus` or `section`, keyed by number.
- **Assignment**: an entry detail (`lyrDataVerse` and friends) carrying `lyricNumber` — which
  verse — and `syll`, a **1-based index into that verse's syllables**. Optionally `wext`, a word
  extension (the line under a held syllable).

Nothing stores the syllables themselves, so `enigma/lyrics.py` tokenises the verse — split on
whitespace, then each word on hyphens — and indexes it. Verified against the corpus: the syllables
land on consecutive entries in playing order, exactly as sung.

**`syllabic` is derived, not stored.** MusicXML needs `single`/`begin`/`middle`/`end`, and Enigma
records only hyphens: a hyphen after a syllable means the word continues, one before means it was
continued into. This is the part most likely to be subtly wrong — it produces output that looks
plausible and sings wrong — so it carries the most tests, including a mutation check that removing
the "previous syllable ended in a hyphen" test breaks `middle` and `end`.

Two cases are dropped rather than guessed at: an assignment whose index falls past the end of its
verse (a verse shortened after the notes were entered), and a lyric detail carrying only positioning.

**The two containers store this very differently, and produce identical output.** A `.musx` writes
one record per (entry, verse). A `.mus` packs every verse the entry sings into one record as
consecutive 20-byte groups (`lyricNumber` +0, `syll` +2, `wext` +8, details tag 1108) — and then
**repeats the whole record**, usually twice, so the adapter emits each (entry, verse) once. Its verse
text is ETF tagged text (`^verse(1)…^end`) in the text stream rather than a binary record. Over the
six same-content pairs whose `.musx` carries lyrics, all 1,794 events match exactly.

`plain_text` now strips both markup dialects: EnigmaXML's `^name(args)` and the binary
`^<opcode><4 bytes>` a `.mus` uses.

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
.mus  ──▶ zlib streams ──▶ pools ──────┐
                                       ├──▶ EnigmaDocument ──▶ build_score ──▶ IR ──▶ MusicXML
.musx ──▶ score.dat ──▶ EnigmaXML ─────┘
```

Both inputs converge **before** the IR, on `EnigmaDocument`. That is stronger than converging at the
IR: `locate_entries`, `read_entry`, `time_signatures`, `decode_key`, `spell_note` and `build_score`
are written once and read either container, so there is no second pipeline to keep in step and no
opportunity for the two to drift.

- `.musx`: `score_xml(path)` → `parse_enigma(xml)` → `EnigmaDocument`
- `.mus`: `read_mus_document(path)` → `EnigmaDocument`, translating the `.mus` pools into the same
  `Record`s (see "Known format facts — reading a `.mus` as an EnigmaDocument")

Then `build_score(document)` → `Score` → `to_musicxml(score)`. Key types are named here as they are
defined.
