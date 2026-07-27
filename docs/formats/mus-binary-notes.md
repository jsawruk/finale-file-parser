# `.mus` (Enigma Binary File) — reverse-engineering notes

**Status:** active research (branch `research/mus-binary-format`). Not yet a shipped reader.
**Goal:** decode the `.mus` payload to plaintext so its records can populate the same
`EnigmaDocument` the `.musx` pipeline builds, giving `.mus`/`.musx` parity for free.

All findings below are from **structural analysis of the curated corpus (238 `.mus`, 401 `.musx`)**
plus permitted community documentation. Report counts/structure only — never corpus record values.

## ✅ `tupletDef` is decoded — details tag 1072, keyed by entry

**Entry-attached details reuse the two key fields as one 32-bit entry number, high word first**:
`entnum = (cmper1 << 16) | cmper2`. Confirmed on every `tupletDef` in the corpus; the little-endian
reading matches **none** of them, so the order is established rather than assumed. This is the first
`.mus` record found keyed by entry rather than by a (staff, measure) pair, and the same convention
should be tried first for the other entry details (articulations, lyrics, beams).

Payload, 30 bytes, little-endian u16:

```
+0 symbolicNum   +2 symbolicDur   +4 refNum   +6 refDur
```

### The evidence here is end-to-end, not an offset sweep — and that matters

**Every one of the 373 paired corpus tuplets is 3:2 over a 512-EDU reference.** Each of the four
fields therefore has exactly *one* distinct value in the whole corpus, so an offset sweep matches
several candidates trivially and can distinguish none of them. Two things pin the layout instead:

1. The natural u16 reading at 0/2/4/6 agrees with **ETF's documented field order**
   (`symbolicNum symbolicDur refNum refDur`).
2. **Every `.mus` sounded duration and tuplet ratio now equals its `.musx`.** Swapping the two pairs
   inverts every ratio, so that check would fail immediately.

The unit tests carry a 5:4 case that the corpus does not contain, precisely because the corpus
cannot tell an inverted ratio from a correct one.

### Effect

The `.mus` → IR sweep's sounded-duration differences fall from **1,092 events to 0**, and tuplet
ratios match on every event. **Every remaining difference between a `.mus`-derived score and its
`.musx` is now instrument-derived** — 4,138 pitches on transposing staves and 22 clefs, both
traced below to values the `.mus` does not store at all.

## ✅ The clef table is decoded — options tag 109

Enigma's document-wide options live in the **`others` pool under cmper `0xFFFE`** (98 records in a
sampled document, against the `.musx` options pool's 34 — the `.mus` split is finer, so the two do
not correspond record for record). `EnigmaDocument` keeps them in `options` only because EnigmaXML
puts them in a separate element.

**Tag 109 is `clefOptions`**: a flat array of clef-table entries, one per clef index.

**The entry stride is set by the Finale version**, the same era split `mus_payload` already uses to
choose a codec — 2011 → 72 documents at stride 18, 2012 → 10 at stride 20, with no overlap:

| field | 2011 (stride 18) | 2012 (stride 20) |
| --- | --- | --- |
| `adjust` (i16) | +0 | +0 |
| `clefChar` (u16) | +2 | +2 |
| `clefYDisp` (i16) | +4 | **+6** |
| `shapeID` (u16) | +8 | **+10** |

2012 inserts two bytes after `clefChar` and two more before `shapeID`. A zero `clefChar` or
`shapeID` means the field is absent, not zero — that is what makes `Clef.sign` report UNKNOWN or
SHAPE rather than inventing a G clef.

**Evidence: all four fields match the paired `.musx` on 1,512 of 1,512 entries across 84 documents**
(18 clefs each).

### The false start worth recording

The 360-byte payloads first looked like **20 entries of 18 bytes** rather than 18 entries of 20,
because 360 is divisible by both. Read that way the fields were consistently two bytes out and the
match rate collapsed to ~1/18. The tell was that `.musx` reports exactly 18 clefs in every corpus
document, so a 20-entry reading needed the `.musx` to be dropping two — a much larger claim than a
stride change. **Deriving the stride from the payload length cannot disambiguate this; the banner
year can, and does.**

### Effect

Clef differences in the `.mus` → IR sweep fall from **327 measures to 22**. Every one of the 22 is
the same case: the `gfhold` stores `clefID` 0, meaning "use the staff's `defaultClef`", and the
`.mus` `staffSpec` stores 0 there too while the `.musx` materialises clef 3. That is the
instrument-derived gap already documented below, not a decode error — so 22 is a floor until an
instrument table is found.

## ⚠️ `staffSpec` located — but the transposition octave is NOT in it

`staffSpec` is **others tag 231**, payload 84 bytes (161 records) or 96 (20). Confirmed by content
against 181 paired records, not by key sequence:

| offset | field | evidence |
| --- | --- | --- |
| +12 | `defaultClef` (u8) | 39/45 exact; the other 6 are `.mus` 0 where `.musx` says 3, and 136/136 records without one store 0 |
| +16 | `staffLines` (u8) | every record, both payload lengths |
| +24 | `dwRestOffset` (i8) | every record, 2 distinct values |
| +25 | `wRestOffset` (i8) | every record, 2 distinct values |
| +34 | `botRepeatDotOff` (i8) | every record |
| +35 | `topRepeatDotOff` (i8) | every record |
| +40 | `vertTabNumOff` (i16) | every record |

The single-valued fields are weak on their own; `dwRestOffset`/`wRestOffset` landing on adjacent
offsets with two distinct values each, plus `staffLines`, is what makes the identification solid.
Both payload lengths share these offsets.

### ⛔ REFUTED: that decoding `staffSpec` would fix transposing staves

This was the stated reason to decode the record, and it does not work. **The octave component of a
staff's transposition is not stored in `staffSpec`.**

The corpus holds staves the `.musx` gives `interval` 1 and 8 (and 5 and 12) — pairs an octave apart.
Their `.mus` `staffSpec` payloads are **byte-identical across all 84 bytes**, while their `.musx`
records carry *different* `instUuid`s. So the `.musx` recovers the octave from its instrument
identity, a Finale-2014-era concept the `.mus` record has no equivalent of.

That is a hard negative, not a "not found yet": there are no bytes left to search in this record.

What *is* there:

- **`adjust` is bijective with byte +20** across all 181 records: 0 → `0x00`, 1 → `0x01`,
  2 → `0x42`, 3 → `0x83`. Only four distinct values, and the encoding is not understood (the low
  bits carry `adjust`; what the high bits mean is open), so treat this as a lead.
- **`interval mod 7` is *not* recoverable.** In this corpus `adjust` maps 1:1 onto `interval mod 7`,
  but with only four instruments that is a coincidence of the sample — both derive from the
  instrument. Do not build on it.

### ⛔ REFUTED: a transposing-staff flag at +23

`+23` is 1 on all 25 transposing staves, which looked like a flag until the other side was checked:
it is also 1 on **124 non-transposing** staves, and takes values 0, 1, 4, 6 and 7 across the corpus.
It is some other field.

### Part names are not at a fixed offset either

`fullName`/`abbrvName` are text-block references (values 2/93 and 3/94 in the corpus). No 1-, 2- or
4-byte offset matches even 80% of the 64 records that carry one; the best candidate, `u16` at +30,
matches 6 of 64 while correctly storing 0 for 107 of 117 records without a name. So either the names
live outside this record or the payload is not a flat fixed-offset struct.

### What this means for `.mus` fidelity

The `.mus` → IR sweep's 4,138 pitch differences on transposing staves **cannot be closed from
`staffSpec`**. Either an instrument table exists elsewhere in the file and has to be found, or the
information is genuinely absent and a `.mus`-only reader cannot spell transposing staves the way
Finale 2014 did. The same "`.mus` stores 0, `.musx` materialises a real value" pattern already seen
in `gfhold.clefID` shows up again in `defaultClef` (+12), which points at the same explanation:
several staff defaults are instrument-derived and simply not written into the `.mus`.

## ✅✅ SOLVED: `details` too, and `gfhold` is decoded

The `details` pool (stream 2) has the **same shape as `others`** with one extra key field, because a
details record is keyed by a pair of cmpers:

```
+0 tag(2)  +2 cmper1(2)  +4 cmper2(2)  +6 inci(2)  +8 length(4)  +12 payload  +4 trailer
```

A record is **`16 + length`** bytes, against the `others` pool's `14 + length`. Shipped as
`enigma/mus_details.py` (`read_mus_details`); the walk tiles stream 2 exactly in **84 of 91** pairs
(167,463 records) — the same seven documents fail as for `others`.

**`gfhold` is tag 1044**, and its 20-byte payload is `clefID` at +0, `clefPercent` at +4, `frame1`
at +6. Over the 80 same-content pairs carrying it: the key sequence is the `.musx` sequence
restricted to the keys `.mus` holds in **80 of 80** documents, `clefPercent` and `frame1` match on
**every** record, and `clefID` matches on 8,110 with the other 272 explained — see below. That makes
`gfhold` the second payload-confirmed record type after `frameSpec`/`measSpec`, and it is the link
from a (staff, measure) to the entry frames that fill it.

**`.mus` writes `clefID` 0 to mean "use the staff's `defaultClef`";** a `.musx` export materialises
the resolved value. All 272 non-matching records are exactly that case, none unexplained. This
refines the earlier finding that every `gfhold` carries a `clefID` with no inheritance — true of
`.musx`, not of `.mus`.

**`inci` at +6 is named by position, not evidence.** Zero in all 77,384 corpus records examined, and
no corpus document repeats a `(tag, cmper1, cmper2)` key, so nothing distinguishes an incidence
counter from a reserved field. The reader keeps the value rather than dropping it.

### ⚠️ RETRACTED: the earlier `gfhold` field offsets

The previously recorded layout — `frame1` at +0, staff at +20, measure+1 at +22, the latter two at
160/164 — was **the same mistake a third time**. The anchor sat 16 bytes inside the record, so `+20`
and `+22` were the *next* record's `cmper1`/`cmper2`. That is why they scored ~160/164 rather than
164/164, and why the measure appeared to need a "+1" that no field actually stores. Correctly
anchored, `cmper1` and `cmper2` are at +2 and +4 with no off-by-one, and `frame1` is a payload
field.

**Three near-misses on this format have now all been the neighbouring record's header.** The
counter-measure is mechanical: after locating anything by content search, column-scan *backwards*
as well as forwards before believing any offset.

### Mutual rejection of the two pool rules is empirical, not structural

Across the corpus the `others` stream never tiles under the details rule and the details stream
never tiles under the `others` rule, which is what lets each reader identify its own stream. This is
a property of real pools, not a guarantee: a degenerate stream of uniform zero-payload records
satisfies both, because each rule reads its length field out of the other's zeroed payload.

## ✅✅ SOLVED: `others` records are self-identifying. The `cmper` question is answered.

**Every `others` record carries its own key in a ten-byte header, and the pool is a flat run of
variable-length records that can be walked from byte zero with no directory, no key array and no
positional convention.** Little-endian:

| offset | field | notes |
| --- | --- | --- |
| +0 | `tag` | record type; `.musx` names the same types |
| +2 | `cmper` | the `(n)` in an ETF `^XX(n)` |
| +4 | `part` | 0 for the score, then 1, 2, … per linked part |
| +6 | `length` | payload size, LE32 |
| +10 | payload | `length` bytes |
| +10+`length` | trailer | four bytes |

so a record occupies **`14 + length`** bytes. Records of one tag sit together in a section; sections
may be separated by two-byte zero padding, which a walk skips.

**Evidence.** Walking stream 1 from byte 0 tiles it exactly in **84 of 91** paired documents
(211,554 records). Against the paired `.musx`:

- **frameSpec (tag 146)** — the `(cmper, part)` sequence matches exactly in **76 of 77** same-content
  documents, and the `startEntry`/`endEntry` payload in **7,919 of 7,922** records.
- **measSpec (tag 176)** — `beats` and `divbeat` match in **3,799 of 3,799** records; `width` in
  3,750, with every miss in one document, which is what re-spacing a score between saves does to
  layout while leaving the music alone.

Shipped as `enigma/mus_others.py` (`read_mus_others`). The seven documents that do not tile hit one
record type whose length field the walk still mis-reads; the reader **refuses** those rather than
returning a truncated pool.

### Why five structural hypotheses were refuted before this

Every earlier attempt located a section by searching for payload values already known from the
paired `.musx`, then read **forward** from that anchor. The key sits **ten bytes behind** it, so it
was never in view. The two near-misses recorded below were the *neighbouring record's* header read
as though it belonged to the anchored one:

- **`+18 == cmper + 1` on 156/164** — `+18` from the old anchor is the next record's `cmper` field.
  It equals `cmper + 1` exactly when no frame number was skipped, which is why it decayed to 50/82
  in documents with more gaps.
- **`+16` "is 146 on 163 of 164 records, near-constant, not a discriminator"** — 146 *is* the tag,
  and it is constant because every record in a section shares one. The 164th reads 147, the tag of
  the next section. It was dismissed for being exactly what a tag looks like.

**The lesson is not "look harder".** It is that an anchor found by content search has no defined
relationship to the record boundary, so *scan in both directions from it*. The test that found this
in one shot — sweep every stride and column in the stream for a strided series equal to the known
key sequence — is cheap, assumes nothing about the record size, and would have answered the
question at any point in the investigation.

### What this retracts

- **"Records are NOT self-identifying"** — wrong. They are. That section is kept below as a record
  of the wrong turn.
- **"No directory / no key array / not positional / no bitmap / no run-length"** — all still true,
  and all irrelevant: the key never left the record.
- **The `measSpec` "18 + 22 × (staves − 1) block"** — the numbers were right, the model was wrong.
  It is not a measure head plus inter-staff rows. It is one 26-byte-payload `measSpec` record for
  the score (40 bytes on disk) followed by one 8-byte-payload record per linked part (22 bytes
  each). The block grew with the staff count because more parts means more part records, and the
  third header field is the part index — confirmed 16/16 in the cases where `.musx` `part` and
  `inci` disagree, and never `inci`.

### Tag ids

Derived by matching each tag's `(cmper, part)` sequence against the `.musx` `others` pool, with the
number of documents agreeing. **Only `frameSpec` and `measSpec` are confirmed by payload content**;
the rest are key-sequence matches and could still be coincidence for tags whose record counts
collide, so treat them as leads, not facts.

| tag | name | docs | | tag | name | docs |
| --- | --- | --- | --- | --- | --- | --- |
| 121 | `articDef` | 88 | | 165 | `metaArtic` | 80 |
| 124 | `channelPlayData` | 80 | | 168 | `metaDynam` | 81 |
| 126 | `chordSuffixPlay` | 85 | | 169 | `metaKeySig` | 80 |
| 131 | `drumLibName` | 86 | | 170 | `metaRepeat` | 81 |
| 134 | `durAllot` | 91 | | 171 | `metaShape` | 80 |
| 136 | `execShape` | 85 | | 172 | `metaStaffStyle` | 80 |
| 140 | `fretboardSymbol` | 91 | | 173 | `metaTimeSig` | 81 |
| 144 | `fontName` | 5 | | **176** | **`measSpec`** | payload-confirmed |
| **146** | **`frameSpec`** | payload-confirmed | | 231 | `staffSpec` | 9 |
| 147 | `lockMeas` | 81 | | 235 | `shapeExprDef` | 10 |
| 149 | `fretInst` | 90 | | 242 | `textExpressionEnclosure` | 14 |
| 163 | `layerAtts` | 85 | | 315 | `volumeValue` | 14 |

### What is still open

- **Seven documents halt mid-walk**, always inside a record whose declared length does not carry the
  walk to the next valid header. One tag (158) is implicated in six of them.
- **The remaining sections' payload layouts** — the walk gives every record's tag, key and bytes;
  what those bytes mean is per-tag work, and ETF field order transfers for some tags and not others.
- **`details` (stream 2)** — the same header shape is the obvious first thing to try, and `gfhold`
  is already located there at offset 104,240.

## ✅ SCOPING ANSWERED: the payload maps onto the existing 7-pool `EnigmaDocument`

`.mus` parity is a **small-to-medium project, not a second format to reverse-engineer.** The
decompressed payload is the same Enigma record model the `.musx` pipeline already builds, and the
vendored docs describe it accurately.

### The streams are the pools

A 2011 `.mus` decompresses to four zlib streams. Compared against the *same document* read from its
paired `.musx` (`01 Overture - Acc`):

| stream | size | character | maps to |
| --- | --- | --- | --- |
| 1 `@0x216` | 170,998 B | 66% zeros, instrument/percussion names, period 26 | `others` (3,850 records) |
| 2 `@0x747C` | 118,274 B | binary, no ASCII, period 36 | `details` (2,686 records) |
| 3 `@0xB19C` | 22,534 B | binary, **period 38** (79%, harmonics 76/114) | **`entries` (580 records)** |
| 4 `@0xC3C9` | 8,734 B | **81% ASCII, ETF tagged text** | **`texts` (147 records)** |

**Stream 4 is human-readable ETF markup** — `^block(1)^…Score^end^block(2)^font(Times,4096)^size(14)^nfx(0)Percussion^end`.
Its tag counts match the `.musx` texts pool exactly:

| stream 4 | count | `.musx` texts tag | count |
| --- | --- | --- | --- |
| `^expression(` | 72 | `expression` | **72** ✓ |
| `^smartshape(` | 60 | `smartShapeText` | **60** ✓ |
| `^fileInfo(` | 1 | `fileInfo` | **1** ✓ |

(`^block(` is 28 against 14 `blockText` records — exactly 2×, unexplained and worth a look, but the
other three families are exact.)

### The entry pool parses directly from `eeppd.txt`

Reading stream 3 little-endian at a 38-byte stride reproduces the documented doubly-linked list:

| record | `@0` entnum | `@6` prev | `@10` next | `@14` dura |
| --- | --- | --- | --- | --- |
| 0 | 9 | 0 | 10 | 1024 |
| 1 | 10 | 9 | 13 | 1024 |
| 2 | 13 | 10 | 14 | 1024 |

`dura = 1024` is a quarter note, exactly as `eeppd.txt` specifies. Validated against the paired
`.musx`:

- **580 entries parsed from `.mus`, 580 in `.musx`, 100% entry-number overlap**
- **567/580 durations agree**

The 13 disagreements are *not* a format problem: those records read as mostly zeros with data at
offsets 35–37, i.e. a naive fixed-stride slice drifting out of alignment. All 13 have `numNotes = 3`.
`eeppd.txt` says entries are **variable-length** — a header plus one 6-byte note record per note — so
a real parser walks the chain rather than slicing at a constant stride. (Note 20 + 3×6 = 38, which is
why a 38-byte stride works for most records and drifts on the rest.)

### What this means for the work

The hard parts are already done or documented: the payload decompresses (shipped), the pool structure
matches the existing model, `docs/eeppd.txt` gives the entry/note layout and every flag bit, and the
85 confirmed `.mus`/`.musx` pairs give exact per-record ground truth to validate against.

Remaining unknowns are the `others` and `details` record layouts (streams 1 and 2), where the ETF spec
gives semantics but **not** binary field order — see the two failed experiments below. Those will need
the same empirical treatment, but now with a working oracle rather than blind.

Sensible first slice: a `.mus` entries reader validated against the paired `.musx` on all 85 pairs.

## ✅✅ SOLVED — BOTH ERAS. 238 of 238 corpus files decode.

| cohort | files | payload encoding | offset | decodes |
| --- | --- | --- | --- | --- |
| 2001 / 2004 / 2005 | 139 | **PKWARE DCL "implode"** (`lit=0`, `dict=4`) | `0x20A` | **139/139** |
| 2011 / 2012 | 99 | **chain of zlib streams** (`78 9c`) | `0x216` (2 files `0x20A`) | **99/99** |

Both offsets and the DCL header are constant across every file in their cohort. DCL inflation runs
0.82×–2.75× (median 2.35×); the zlib chain 5.87×–8.63× (median 6.07×) once all streams are
concatenated — a *single* zlib stream is only ~3.2×–3.5×. Decoded payloads run 32,816–699,585 bytes.

Decoded output is unambiguously real Finale data —
"General MIDI", "Entry & Playback", "Agogo Bells", "Wood Blocks", "Bookmark" in the old cohort;
"Orchestral Percussion", "Times New Roman", "Broadway Copyist" in the new.

**Shipped as `finale_file_parser.read_mus_payload(path) -> bytes`** (`enigma/mus_payload.py`), which
dispatches on the banner year and falls back to the other scheme if that disagrees. The PKWARE DCL
decompressor is `enigma/blast.py` — a port of zlib's `contrib/blast`, pinned by that project's own
test vector. Both enforce a 64 MiB output cap *while* decoding, since this is untrusted input.

### ⚠️ RETRACTED: the "bit-packed record stream" model for 2001/2005

**Everything this document said about the old cohort being an uncompressed bit-packed record stream
was analysis of *compressed* data.** The 49-byte groups, the 49-bit sub-units, the counter fields, the
doubling ladder, the "5-byte record" — all artifacts. Retained below only as a cautionary record.

The irony is that they were *real* patterns with a mundane cause. **DCL with `lit=0` emits raw 8-bit
literals into a bit-packed stream interleaved with 1-bit literal/match flags.** So plaintext bytes
pass through verbatim but at bit offsets that drift as flags and match tokens accumulate. That single
fact explains every "discovery":

| observed | actual cause |
| --- | --- |
| counter at successive **bit** offsets; ladder 2,4,8,16,32,64,128,0 | a plaintext counter array passing through as raw literals, its bit offset drifting one bit per flag |
| "byte-oriented, not a bitstream" | literals are whole bytes — just not byte-*aligned* |
| no readable text at any fixed bit shift | the drift means no single global shift aligns them |
| bit density varying 0.447–0.638 | plaintext statistics showing through the raw literals |
| long exact repeats | repeated literal runs in the source |

### The mistake that hid this for the whole investigation

**PKWARE DCL was tested, with a correctly validated decoder, and recorded as "RULED OUT" — but the
test ran against `confirmed_pairs()`, which are 2011/2012 files.** Those are zlib, so of course DCL
found nothing. The negative was then written down as settled and never revisited.

Every codec test in this investigation — LZSS, LZH, DCL — ran on 2011/2012 files, because that is
where the `.musx` oracle exists. The old cohort was never searched at all until the very end.

**The rule this earns:** a codec negative is only meaningful *for the cohort it was run on*. Record
the cohort with every result. Two false negatives (raw DEFLATE, and DCL) each cost this investigation
more than every positive finding gained.

## `others` and `details`: a foothold, not a solution

`others` (stream 1) is **verified** and its `measSpec` section is decoded. `details` (stream 2) is not.

### Stream 1 really is the `others` pool

Previously inferred from size and autocorrelation period during scoping, never checked. It is now
confirmed: **all 24 distinct `measSpec` widths from the paired `.musx` are present in stream 1**,
against 4, 2 and 1 in streams 2-4 — chance level for a 16-bit value. They are interleaved rather than
consecutive, which is what a record array with `width` as one field among many looks like.

### `measSpec` decoded

Located by searching stream 1 for the known width sequence and fitting an arithmetic progression:
**41 of 41 measures fit at start offset 60,314 with an 84-byte stride** — 41 being exactly the measure
count. Field offsets within a record, each confirmed against every one of the 41 measures:

| offset | field | measure 1 |
| --- | --- | --- |
| +0 | `width` (ETF `measpace`) | 305 |
| +2 | `key` | 253 |
| +4 | `beats` | 2 |
| +6 | `divbeat` | 1024 |

**This is the ETF spec's documented field order** — `^MS(n) measpace key beats divbeat ...`. Worth
noting explicitly, because that order emphatically did *not* transfer for the entry pool (see the two
failed experiments below). ETF order transferring here and not there means neither outcome can be
assumed; each record type has to be checked.

### What the structure looks like so far

Records of one tag sit **contiguously in a section**; the stream is a run of such sections. The first
section of stream 1 is a different record type: 26-byte records with an incrementing `cmper` in bytes
0-1, and a `fe ff` marker at +2 that occurs 269 times in the stream and so belongs to that type rather
than to records generally.

### The `measSpec` region is a per-measure block, not a flat record array
> **SUPERSEDED** by the self-identifying-record finding at the top of this file. Kept as a
> record of the wrong turn, not as a finding.

The 84-byte "stride" is not a record size. Measuring it across ten document configurations and three
staff counts gives an exact law:

| staves | 2 | 3 | 4 |
| --- | --- | --- | --- |
| block size | 40 | 62 | 84 |

That is **`18 + 22 x (staves - 1)`**. So each block is an 18-byte measure head followed by
**`staves - 1`** rows of 22 bytes. The row count being one *fewer* than the staff count is the
tell: it matches the number of **gaps between** staves, which is what inter-staff spacing data would
need. (A flat `measSpec` array would not change size with the staff count at all.)

The measure head carries the fields already identified:

```
+0 width   +2 key   +4 beats   +6 divbeat   +8..17 further measure fields
```

Confirmed on consecutive measures: head 1 reads 305/253/2/1024 and head 2 reads 334/253/2/1024,
matching the paired `.musx` exactly.

### Layout is structural, not content-driven -- which argues against an index

**Thirteen different pieces of music with the same shape (2 staves, 41 measures) put this region at the
identical offset 57,244 with the identical block size.** Offset and size follow from the document's
*counts*, not from what the music contains.

That is what a format with **no directory** looks like: the reader knows each record type's size and
walks sections in a fixed order, deriving offsets from counts it already has. Three places an index
could have hidden were checked and ruled out:

- **Not a small stream.** The payload holds exactly four zlib streams; nothing is hiding below the
  reader's 4 KiB floor.
- **Not the tail.** The 1,216 bytes after the last stream are the documented macOS plist plus 22 bytes.
- **Not an absolute offset.** 60,314 appears nowhere as a 2- or 4-byte value in any stream or in the
  raw file.

**But the offset is not a simple function of (staves, measures) either** -- 4 staves x 23 measures sits
at 89,656 while 4 x 41 sits at 60,314. It depends on the size of everything preceding it, which varies
with content such as chord suffixes and fretboards. So walking from the start of the stream, section by
section, is the only route: each section's size has to be derivable before the next can be located.

### `frameSpec` decoded

Located the same way as `measSpec` -- by fitting an arithmetic progression to values already known
from the paired `.musx`. **All 164 frameSpec records fit at offset 35,492 with a 26-byte stride**, and
the fields are confirmed against every one of them:

```
+0  startEntry  LE32      +4  endEntry  LE32
```

### The pool's first section is fixed-size

The stream opens with **18 records of 26 bytes = 468 bytes**, and that size is identical across every
configuration sampled (2-4 staves, 40-64 measures). Its *content* is not fixed -- two documents diverge
at byte 18 -- and `header[24:40]` depends **only on the staff count**, identically across 4-staff files
and identically across 2-staff files, so it encodes staff layout rather than counts.

### Why counts cannot come from the document's shape

`frameSpec` counts are **content-dependent, not structural**: 164 frames for 4 staves x 41 measures is
exactly 4x41, but 4 staves x 40 measures gives **157, not 160**. Empty frames are omitted. So a reader
cannot compute the section size from staff and measure counts, and something must supply it.

Three candidates checked and ruled out:

- **Not in the fixed header.** No offset in the 468-byte block holds the measure, staff or frame count
  consistently across configurations.
- **Not a length before the section.** The count, the byte size, and both offsets are all absent from
  the 64 bytes preceding the section.
- **Not an absolute offset anywhere** (established previously).

### ⚠️ REFUTED: records are NOT self-identifying
> **SUPERSEDED** by the self-identifying-record finding at the top of this file. Kept as a
> record of the wrong turn, not as a finding.

The lead below was tested and **does not hold**. Retained because the tests narrow the problem.

**`+16` is not a tag id.** Within the `frameSpec` region it is 146 on 163 of 164 records -- near
constant, not a discriminator. Scanning the whole stream at stride 26 gives a value distribution
dominated by 0, 12 and 65535, which is noise from a stream that is not uniformly 26-byte.

**`+18` is not `cmper`.** It tracks `cmper + 1` on 156 of 164 records, which looked promising, but
reading `+16..+19` as one LE32 shows it incrementing by **exactly 65536 on 155 of 163 steps** -- the
high word is a plain sequential record counter. `cmper` meanwhile runs 3 to 194 with gaps, so the two
drift apart wherever a slot is skipped. An approximate match to a counter is not a key.

**The section is not positionally keyed either.** If every slot in the `cmper` range were stored, the
record for `cmper` *c* would sit at `base + (c - 3) * 26`. That fits **72 of 164** records, against
**164 of 164** for contiguous storage. So the 164 present frames are stored back to back in `cmper`
order and the 28 empty ones are simply absent.

### `gfhold` located -- and the "malformed question" reframing is REFUTED

**`gfhold` sits in stream 2 (`details`) at offset 104,240, stride 36 bytes.**

> **SUPERSEDED** — the offset and stride are right, but the field offsets below are read from an
> anchor 16 bytes inside the record, so `+20`/`+22` are the *next* record's key pair. See the
> details-pool section at the top of this file.

| offset | field | evidence |
| --- | --- | --- |
| +0 | `frame1` (LE16) | **164/164** records match the paired `.musx` |
| +20 | staff (`cmper1`) | 160/164 |
| +22 | measure + 1 (`cmper2`) | 160/164; measure *without* the +1 matches 0/164 |

The remaining 4 are where the fixed-stride walk drifts, the same way it did for the entry pool before
variable-length records were understood.

**The decisive result:** fitting `gfhold`'s frame references against the two candidate numberings gives
**164/164 for `.musx` numbering** and **8/164 for positional**. So `.mus` references frames by exactly
the numbers `.musx` reports, and **every one of the 164 referenced frames has a `frameSpec` record**.

That kills the reframing proposed above. `.musx` cmper values *are* faithful to `.mus`; the assumption
was sound and the cmper question is real, not an artifact of renumbering. **The section above is
retained as a record of a wrong turn, not as a finding.**

### A near-miss that survived one file and died on the second
> **SUPERSEDED** by the self-identifying-record finding at the top of this file. Kept as a
> record of the wrong turn, not as a finding.

`gfhold`'s `measure + 1` at +22 looks like the same off-by-one as `frameSpec`'s `+18 = cmper + 1`
(156/164), which was tempting evidence that `frameSpec` carries its key after all -- i.e. that the
refutation recorded below was itself wrong.

It is not. Re-tested across four documents, `+18 == cmper + 1` holds on **156/164** in the first file
but only **50/82** in three others. The first file's cmpers happen to be mostly contiguous, which makes
a plain counter look like a key. **The original refutation stands.**

Twice now on this question a ~95% match has looked like a finding. The check that settles it is
cheap and should be automatic: **run the candidate against a second document before believing it.**

### No key array either
> **SUPERSEDED** by the self-identifying-record finding at the top of this file. Kept as a
> record of the wrong turn, not as a finding.



Searching every stream and the raw file for the 164 `cmper` values as a contiguous array, at both
2- and 4-byte widths, finds **nothing** -- not the full list, not even its first twelve values. So
`cmper` is not stored as a parallel index either.

**That is four structural hypotheses refuted, which is enough to suspect the question.** Consider what
the evidence actually shows: the 164 present frames sit back to back in `.musx` document order, and a
positional fit over the *`.musx` cmper range* fails (72/164) while contiguous storage succeeds
(164/164).

The simplest reading is that **`.mus` numbers frames positionally and `.musx` renumbers them** -- the
sparse 3..194 range with 28 gaps is `.musx`'s own numbering, not something `.mus` ever stored. On that
reading there is no missing key: a `.mus` reader assigns frame numbers by position, and the internal
references (a `gfhold`-equivalent naming `frame1..frame4`) would use that positional numbering.

This is **not yet confirmed** -- it needs the `gfhold` equivalent located in stream 2 (`details`) to
see what frame numbers `.mus` actually references. But it would explain every negative above at once,
and it means the effort spent hunting for a directory, an in-record key and a key array was spent
looking for something that need not exist.

**Method note.** Four refutations in a row on the same question is itself evidence -- not that the
format is unusually clever, but that the framing carried an assumption. Here the assumption was that
`.musx` cmper values are faithful to `.mus`, imported from how every other cross-format check in this
document has worked. That assumption is load-bearing and was never tested.

### Where that leaves `cmper`
> **SUPERSEDED** by the self-identifying-record finding at the top of this file. Kept as a
> record of the wrong turn, not as a finding.

For this section `cmper` is **not in the record, not implied by position, and not in a directory** --
all three now tested. Something else must carry it. The remaining candidates are a separate key or
index array elsewhere in the pool (one entry per record, which would not look like a "directory" and
would be easy to miss), or a per-section run-length structure that encodes which slots are present.

That is a narrower question than the one this line of work started with, and the tests above rule out
the three most obvious answers rather than leaving them to be re-tried.

### The original lead, now refuted -- records may be self-identifying
> **SUPERSEDED** by the self-identifying-record finding at the top of this file. Kept as a
> record of the wrong turn, not as a finding.

The 26-byte record run **does not begin at the fitted `frameSpec` offset** -- it extends earlier, and
the records share a structure. Bytes +16 and +18 hold a pair that increments across records and rolls
over between them:

```
... 92 00 | 03 00 ...   (record before the frameSpec fit)
... 92 00 | 04 00 ...   (frameSpec record 0)
... 92 00 | 05 00 ...   (frameSpec record 1)
... 93 00 | 01 00 ...   (last frameSpec record)
... 93 00 | 06 00 ...   (record after)
```

A rolling major/minor pair like that looks like a **key carried inside the record** rather than implied
by position. If it is, this region is a flat array of self-identifying 26-byte records and needs no
directory at all -- which would explain why no index has been found. **Testing whether that pair is a
(cmper, inci) or (cmper1, cmper2) key is the next step**, and it can be checked directly against the
`.musx`, whose records carry exactly those attributes.

### The open problem: locating a section without the oracle

`measSpec` was found by searching for values already known from the paired `.musx`. That does not
generalise — a `.mus`-only file has no oracle, and the pool has 73 distinct tags.

**No directory was found.** The section offset 60,314 appears nowhere as a 2- or 4-byte value in any
stream or in the raw file (one incidental 2-byte hit in the raw file, not a reference). So sections are
not indexed by absolute offset; if there is a table it is expressed some other way — counts and sizes
to accumulate, or a per-section header. That is the thing to find next, and everything else unlocks
behind it.

### `details` (stream 2) — NOT confirmed, do not build on this

> **SUPERSEDED** — the details pool is now decoded; the 36-byte stride guessed here was right for
> `gfhold` but the field boundaries were not. See the top of this file.

Reading stream 2 at a 36-byte stride (the period autocorrelation suggested) yields plausible-looking
structure: LE32 pairs where the second value increments by small amounts, and a constant `20` at +8.
**But the first value is 1009, which matches no `cmper1` on any `.musx` details record in that
document.** So the stride, the field boundaries, or both are wrong. Recorded only so the next attempt
does not repeat it and mistake it for progress.

## READ `docs/eeppd.txt` AND `docs/etfspec.pdf` FIRST

**Process failure worth recording:** most of this document was derived by reverse engineering while
Coda's own documentation sat in this repo, git-tracked. `CLAUDE.md` requires reading the relevant
`docs/` file before working in an area; that was skipped because `corpus/` was searched for `.etf`
files and `docs/` was never listed. Read these before touching the format:

- **`docs/eeppd.txt`** — Coda's Enigma **Entry Pool** documentation (1996). Entry/note field layout
  and every flag bit.
- **`docs/etfspec.pdf`** — official Coda **ETF Specification v98c.0**. A superset of `eeppd.txt`:
  same entry-pool material plus ~22 record types. Extract with `pdftotext -layout` (available here).
- `docs/lilypond-etf-format.html` — self-described incomplete; corroborate before relying on it.
- `docs/cahill-enigma-cpnview-thesis.pdf` — covers **ETF (the text format)**, not the binary layout.
  `REFERENCES.md` describes it as treating the legacy binary format, which overstates it.

Use only these in-repo copies. Other copies exist elsewhere on the machine and are out of scope.

### The record vocabulary (from `etfspec.pdf`)

22 tags: `^eE` entry · `^MS` measure spec · `^IS` staff spec · `^NG` group spec · `^PS` page spec ·
`^SS` staff system spec · `^IU` instrument used · `^TX` text block · `^pT` page text block ·
`^mt` measure text block · `^ve` lyrics · `^CL` clef · `^CH`/`^hC` chord · `^CN` notehead mods ·
`^IM` articulation · `^IV` chord suffix · `^IK` chord playback · `^ME` MIDI expression ·
`^ac` performance data · `^CD` cross staffing · `^LP` staff enduction.

### What the docs settle about findings in this document

| Finding derived here | What the vendor docs say |
| --- | --- |
| Monotone +1 counter fields, validated with shuffle controls | *Hypothesis, **NOT** confirmed — see the failed test below.* `eeppd.txt` fields 1–2 are 32-bit prev/next entry links, sequential by construction, which looked like an obvious match. A direct test does not support it. |
| Systematic 1-bit excess (0.535–0.555 in every cohort); histogram dominated by runs of 1s | **`SETBIT 0x80000000` — "always set (indicates a legal entry)"**, on *both* entry and note flags. A mandatory set high bit in every record, smeared across bit offsets by the packing. Not an "all-ones sentinel" as guessed here. |
| The 1,022-byte lyrics-only block holds counters, not text | **Confirmed.** `etfspec.pdf`: "Lyrics are stored as entry details which give a **syllable offset into a raw text record**." The block is `^ve` detail records; the text lives in a separate raw-text section. |
| Isomorph attack found no lyric text | Consistent — the raw text is a separate section, and it is evidently packed rather than stored as characters. |

### ⚠️ ETF documents SEMANTICS, not the binary layout — two failed attempts prove it

Both attempts to carry ETF field layout across to the binary failed. Record this before trying again.

**1. The `^MS` counting attack found nothing.** `etfspec.pdf` gives MS as
`measpace key beats divbeat auxflag meflag`, one record per measure. From the paired `.musx` for
`01 Overture - Acc`: 41 measures, `key`=253 and `beats`=2 and `divbeat`=1024 constant throughout,
`width` varying per measure (305, 334, 262, 261, 305, …) — a 41-value fingerprint.

Searched at **bit** granularity (not just byte-aligned), across the whole file:

| search | result |
| --- | --- |
| width sequence (41 varying 16-bit values) | `width[0]`=305 occurs at only 5 bit positions, `width[1]`=334 at 2 — chance level (~6 expected). **No run.** |
| `divbeat`=1024 as a repeated constant | 15 positions in the whole file, not 41. Longest arithmetic progression: **2**. |
| `key`=253 | 2 positions. |
| same, on spec-era files (2005 Blues, 2005 Gifts, 2001 Bach Concerto), incl. byte-swapped | longest progression **2–3**, i.e. nothing. |

So measure specs are **not** stored as flat arrays of 16-bit fields in any cohort.

**2. The entry linked-list prediction failed.** `eeppd.txt` says entries are a doubly linked list, so
entry *k* carries prev=*k*−1 and next=*k*+1 — predicting **two counter fields in one record with a
constant delta of 2**. Testing every counter-like field at the confirmed stride: 70 such fields found,
and **zero pairs with any constant small delta**. The counters are therefore *not* prev/next links.

**The lesson:** the ETF spec is the *transportable text* format at **v98c.0 (Finale 97)**, while the
corpus runs 2001–2012. Its field **order and widths do not transfer** to the binary. What the docs
reliably give is **semantics**: what records exist, what the flag bits mean, enumerations, and the key
encoding. Binary field layout still has to come from the bit-level work in this document — the docs
then supply the meaning once a field is located. Do not treat an ETF field list as a binary struct.

Two things this still unlocks:

- **Counting attack is now well-founded.** `etfspec.pdf`: "There is exactly **one MS record for every
  measure** in the piece." So a record count in a `.mus` can be matched against the measure count read
  from a paired `.musx` to identify record types by fingerprint.
- **Key encoding is confirmed vendor-side.** Linear keys are `< 16384`: top two bits 0, next six a
  bank number (0–63), bottom eight the accidentals (−128…127); bank 0 = major, bank 1 = minor. That is
  exactly the `mode << 8 | signed-fifths` layout `enigma/key.py` already derived from the corpus —
  independent confirmation of shipped code.

## ✅ SOLVED (2011/2012 cohort): the payload is a chain of ZLIB streams, found by `78 9c`

**The 2011/2012 `.mus` payload is a sequence of consecutive zlib streams with ordinary `78 9c`
headers. Locate them by scanning for the magic — do NOT hardcode an offset.**

> **Corrected from the first write-up of this section**, which described it as *raw* DEFLATE at a
> constant `0x218`. `0x218` is simply `0x216 + 2`: the two header bytes skipped. Reading it as
> headerless deflate worked but hid the real structure, and hardcoding the offset breaks on files
> whose preamble is a different length. Note this also means the earlier note *"zlib — no magic
> anywhere"* was **another false negative**: `78 9c` is present, at `0x216`.

### Corpus-wide verification (all 238 files)

| cohort | files | files with zlib streams | total streams |
| --- | --- | --- | --- |
| 2001 | 102 | **0** | 0 |
| 2004 | 1 | **0** | 0 |
| 2005 | 36 | **0** | 0 |
| 2011 | 89 | **89** | 354 |
| 2012 | 10 | **10** | 40 |

**99 of 99 files in the 2011/2012 cohort decode; 0 of 139 in the 2001/2004/2005 cohort do** — at any
offset in `0x80`–`0x4000`, not just `0x216`. That is decisive confirmation of the two-era split: the
older cohort is a genuinely different, uncompressed format, and the bit-packed record findings in this
document belong to it.

First-stream header offsets: **`0x216` in 97 files, `0x20A` in 2** (`Ode to Joy.mus`,
`Ode to Joy - Opt. C Inst.mus`). The offset moves because the preamble ahead of it is variable-length —
in the common case it ends with the ASCII fragment `ext inserts\0` then a short binary run. Roughly
4 streams per file (394 across 99 files).

Verified on `01 Overture - Acc.mus` (2011), walking stream by stream:

| stream | offset | compressed | inflated | entropy |
| --- | --- | --- | --- | --- |
| 1 | `0x00218` | 29,270 | 170,998 | 3.12 |
| 2 | `0x0747E` | 15,632 | 118,274 | 2.67 |
| 3 | `0x0B19E` | 4,637 | 22,534 | 3.06 |
| 4 | `0x0C3CB` | 1,770 | 8,734 | 5.14 |

**320,540 bytes inflated from a 53,113-byte file.** The output is unambiguously real: it contains
**166 of 306 known strings** from the paired `.musx` — against a measured false-positive floor of
**0 hits in ~12,300 decodes** — plus readable Finale vocabulary ("Orchestral Percussion", "Concert
Snare Drum", "Times New Roman", "Broadway Copyist", "Expressive Text").

Offset `0x218` held across all 8 confirmed pairs tested, inflating 3.2–3.5×:

| file | `.mus` | offset | inflated | tail |
| --- | --- | --- | --- | --- |
| 01 Overture - Acc | 53,113 | `0x218` | 170,998 | 23,307 |
| 01 Overture - Bass | 44,924 | `0x218` | 154,308 | 17,857 |
| 01 Overture - Bb Sax | 44,869 | `0x218` | 154,372 | 17,792 |
| … 5 more, all `0x218` | | | 150,586–154,372 | 17,250–17,857 |

### Why this took the whole investigation

**This document previously recorded "raw DEFLATE (no offset inflates)" as ruled out.** That was a
false negative, and it survived because every later result was interpreted in its light. Three
compounding mistakes:

1. **The early raw-DEFLATE test was wrong** and never re-run, because it had been written down as
   settled fact.
2. **A broken control** (`os.urandom` as a stand-in for compressed data) produced the "long exact
   repeats ⇒ not compressed" argument, which then *retired the entire compression search space* —
   see the correction above.
3. **Cohort blindness.** The structural findings (bit-packing, counters, the doubling ladder) are
   real but come from **2001/2005** files, and were generalised to a format that had changed.

The lesson worth keeping: **a negative result recorded as fact is more dangerous than an open
question.** Re-test cheap negatives when later evidence shifts, and never build a sweeping exclusion
on a control you have not measured.

### Practical notes for the reader

- Use `zlib.decompressobj(-15)` and walk the streams: inflate, advance by the consumed length
  (`len(data) - p - len(obj.unused_data)`), repeat.
- **Guard against the stored-block artifact.** A raw inflate at an arbitrary offset can hit a DEFLATE
  *stored* block and return a verbatim copy of its input, which looks like a large successful decode.
  Check `out[:64] == data[p+5:p+69]` and reject.
- Observed inflation is 3.2–3.5× here, but cap allocations anyway — this is untrusted input.

## How the two eras relate: shared container, entirely different payload

Now that the newer payload decompresses, the two eras can be compared directly.

### What they DO share

- **The container header is identical in structure.** `ENIGMA BINARY FILE` magic, the version banner
  at `0x20`, and the provenance stamps at `0x66`–`0x9D` — already decoded by `version/mus.py` for all
  238 files, both eras.
- **The payload begins at ~`0x200`** in both.
- **The same logical Enigma data model**, per the vendored docs: the same record types conceptually
  (entries, measure specs, staff specs, …) whatever the physical encoding.

### What they do NOT share — the payload encoding is unrelated

| | 2001/2005 (raw) | 2011/2012 (decompressed) |
| --- | --- | --- |
| compression | **none found** | chain of zlib streams |
| entropy | 7.748 | 3.257 |
| 1-bit density | 0.5349 | 0.1327 |
| bytes inside ASCII runs ≥6 | 0.46% | 4.21% |
| `Times New Roman`, `Maestro`, `Percussion`, `Broadway Copyist` | **absent** | **all present** |

**The old format is not a compressed anything.** Exhaustive inflate at *every* offset in the file,
with both `wbits=15` and `wbits=-15`, on three files across both old cohorts: **nothing**. (Stray
`78 01`/`78 9c`/`1f 8b` byte pairs occur a handful of times per file, at chance frequency, and none
inflates.) Combined with the corpus scan — 0 of 139 old-cohort files versus 99 of 99 new — the old
format is definitively not deflate-based.

**But it is not plainly readable either.** Searching all 8 bit-shifts of the payload for generic font
probes (`Times`, `Maestro`, `Font`, `Roman`) finds nothing in any 2001 or 2005 file, while the same
strings are trivially present in decompressed 2011 data. Every Finale document must reference fonts,
so the old format evidently does not store them as literal strings at any bit alignment — plausibly as
numeric IDs (Mac font IDs were the era's convention), but that is untested.

So the two eras share a container and a data model, and nothing else. **Findings from one era must not
be carried to the other** — the mistake that cost this investigation most of its time.

### Open: what the old payload actually is

It is neither deflate-compressed nor plaintext. Constraints any answer must satisfy:

- bit density varies **0.447–0.638** across 8 KiB windows — three times the spread of a gzip control,
  which no compressor produces (see the cohort table above)
- it carries **counter fields** that survive a shuffle control, and a **doubling ladder**
  (2, 4, 8, 16, 32, 64, 128, 0) with exact byte-modular wraparound
- no readable text at any bit alignment

**Inconclusive test, recorded so it is not mistaken for a result:** 6-bit and 7-bit packed-text
unpacking was tried across all bit offsets, scored by a "word-like run" regex. It is worthless — the
detector fires on any letter sequence, returning 2,119 gibberish "words" from the old payload while
scoring genuine decompressed English at only 715. **Re-run with a real dictionary before drawing any
conclusion about packed text.**

## The 2001/2005 cohort in detail: a bit-packed record stream

> ### ⚠️ MAJOR CORRECTION — the "no codec anywhere" claim was built on a broken control
>
> This document previously asserted that the payload is **not compressed in any cohort**, on the
> grounds that it contains long exact repeats and "random/compressed data has **zero** repeated
> 16-grams". **That control was wrong.** It compared against `os.urandom`. Compressed output is *not*
> random bytes — it carries Huffman and block structure that repeats. Measured on the *same document*,
> equal 52,601-byte samples:
>
> | sample | entropy | rep 8-gram | rep 16-gram | rep 24-gram |
> | --- | --- | --- | --- | --- |
> | `.mus` payload (2011) | 7.985 | 621 | 424 | 338 |
> | **gzip of the same document** | 7.992 | **271** | **105** | **63** |
>
> Real gzip has *hundreds* of repeated 16- and 24-grams. The `.mus` has more, but the same order of
> magnitude — not the "167 versus 0" contrast this document claimed. **The repeat argument therefore
> does not exclude compression, and every conclusion that rested on it is withdrawn**, including
> "stop testing LZ variants". For the 2011/2012 cohort the earlier codec searches (LZSS, LZH, PKWARE
> DCL — all run on 2012-era files) should be treated as **live again**, not settled.
>
> **Do not use `os.urandom` as a stand-in for compressed data.** Compress a real file and compare
> against that.

### What survives, and for which cohort

The bit-packing model holds for **2001/2005 only**, where it rests on direct evidence rather than the
broken repeat argument:

| evidence | 2001/2005 | 2011/2012 | gzip control |
| --- | --- | --- | --- |
| payload entropy | 7.748 | 7.985 | 7.992 |
| per-8 KiB 1-bit density spread | **0.1909** | 0.0175 | 0.0599 |
| counter fields (validated, shuffle-controlled) | **256** at S=392 | **0** at every stride tried | — |
| counter readable directly in a hexdump | yes (5-byte record, +0x20/record) | not found | — |
| doubling ladder 2,4,8,16,32,64,128,0 | yes, exact modular wraparound | not found | — |

The 2005 bit-density spread is **three times** the gzip control's, and no compressor emits bit density
varying from 0.447 to 0.638 across a file — that reflects plaintext statistics showing through. Add
the counters and the doubling ladder and the 2001/2005 case is solid.

The 2011/2012 case is the opposite. Its entropy, bit density and per-region density spread are all
**statistically indistinguishable from — indeed tighter than — real gzip**, and it yields no counter
fields at any stride tried. This cohort is plausibly compressed, and the format may simply have
changed between eras. That also re-explains the cohort split recorded further down, which was
attributed merely to "packing harder".

**Caveat on the 2011/2012 counter scan:** one anchor, six strides. Suggestive, not exhaustive.

> **Correction (stride).** An earlier version claimed a **49-bit stride** as the format's constant.
> That is **refuted** — 49 is specific to one file, and the group is 49 *bytes* with 8 sub-units 49
> bits apart. See "The stride is not universal" below.

Everything below this section was written while assuming the payload was *transformed* somehow. It is
not. It is **dense bit-packed structured records**, and the reason no decompressor ever worked is that
there is nothing to decompress.

### The evidence

In `Blues_BB_Score.mus` (2005/MAC), the 4-byte anchor `fe fc e7 7e` occurs 93 times, and **76 of its
92 gaps are exactly 49 bytes**. Taking the byte at fixed offsets from each anchor and measuring the
increment per anchor occurrence:

| byte offset from anchor | −8 | −2 | +4 | +10 | +16 | +22 | +28 | +34 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| increment per record | **+2** | **+4** | **+8** | **+16** | **+32** | **+64** | **+128** | **0** |

That is one logical counter incrementing by 1, observed at eight successive **bit** positions:
2¹, 2², 2³, 2⁴, 2⁵, 2⁶, 2⁷, 2⁸≡0. The wraparounds are exact byte-modular arithmetic (−224 = 32−256,
−192 = 64−256, ±128), and the final column is 0 because the field has shifted entirely out of that
byte. Dividing each column by its power of two yields increments of **exactly 1.0** with identical
reset behaviour across all columns.

Each successive field sits **+6 bytes and +1 bit** from the previous one — a stride of **49 bits**.
Eight strides = 392 bits = **49 bytes**, which is precisely the observed byte-level super-period: byte
patterns recur every 49 bytes because that is when the bit phase realigns to a byte boundary.

### Why this explains the entire investigation

- **Why every codec failed** — LZSS, LZH, LZW, DEFLATE, bzip2, lzma, PKWARE DCL. There is no codec.
- **Why entropy is ~7.6–7.98** — densely packed fields with no wasted bits look near-random.
- **Why long exact repeats exist** — identical record content at the same bit phase produces identical
  bytes. No compressor would have left them.
- **Why repeats are byte-aligned** — they can only recur at multiples of 49 bytes, where phase realigns.
- **Why cross-file identical runs appear at arbitrary byte shifts** — same content, same phase.
- **Why the isomorph attack found no text** — text fields sit at varying bit offsets, so no global byte
  substitution or single global bit-shift can expose them.

### The stride is NOT universal — 49 is one file's dominant record type

Tested anchor-free, via byte-match autocorrelation on the payload (a stride of S bits with S odd gives
a byte super-period of exactly S bytes, so the dominant lag *is* the stride). Sampled across cohorts:

| file | cohort | baseline | top lags |
| --- | --- | --- | --- |
| Bach Concerto.MUS | 2001 | 1.06% | **7** (3.99%), 14, 21, 28, 35 |
| Twinkle Variations.MUS | 2001 | 1.04% | **7** (3.58%), 14, 28, 35, 21 |
| 8_Entertainer_1.mus | 2004 | 1.13% | **22** (3.70%), 31, 9, 75 |
| Blues_BB_Score.mus | 2005 | 1.10% | **49** (3.35%), 75, 98, 25, 50 |
| 13_Petrushka_Score.mus | 2005 | 1.31% | **7** (3.42%), 14, 28, 21, 35 |
| Bach_Fugue.mus | 2005 | 1.03% | **22** (2.91%), 31, 9 |
| Jingle Bells.mus | 2012 | 0.63% | 7 (1.32%), 14, 33 |

**49 appears in exactly one file.** The dominant period varies by document, which is what a
variable-record-type format predicts: whichever record type is most abundant sets the observed period.
A big-band score with many staves is dominated by a different record than a solo piano piece.

Two things do generalise, and they matter more than the number:

- **A period-7 family with clean harmonics at 14/21/28/35** recurs across 2001, 2005 and 2012 files.
  Seven is odd, so this is a **7-bit stride**. That 7 keeps reappearing across cohorts suggests a 7-bit
  unit is fundamental somewhere in the format. (Note the ladder test in `stride.py` cannot evaluate
  S=7: the per-step byte offset is S//8 = 0, so successive instances share a byte. It needs a
  bit-level formulation to test small strides — a gap in the tooling, not evidence against.)
- **The 2011/2012 cohort has far weaker periodicity** — top lags reach only ~1.3% over a 0.6% baseline,
  versus 3.35% over 1.10% for 2005. Consistent with the entropy split (7.96 vs 7.64) reported above:
  the newer format packs harder, leaving less periodic structure exposed.

**What survives from the 49-bit result:** the *bit-packing model*, which was verified directly and does
not depend on the number. In `Blues_BB_Score.mus` the doubling ladder 2, 4, 8, 16, 32, 64, 128, 0 with
exact byte-modular wraparound is unambiguous evidence of one counter field read at successive bit
offsets. Stride is a per-record-type property; bit-packing is the format.

### Second correction: the group is 49 BYTES, with 8 sub-units 49 BITS apart

"49-bit stride" was wrong in a second way, caught by bit-level extraction. Sampling the known counter
field at successive strides:

| stride | extracted values | monotone |
| --- | --- | --- |
| **392 bits (= 49 bytes)** | 74, 76, 78, 80, 82, 84, 86, 88, 90, … | **0.91** |
| 49 bits | 74, 43, 179, 215, 156, 113, 196, 147, … | 0.36 (noise) |

The counter repeats every **392 bits = 49 bytes**. So the record *group* is 49 bytes, and it contains
**8 sub-units spaced 49 bits apart** (8 × 49 = 392) — which is exactly what produced the 1-bit
progressive shift and the doubling ladder. Note this relation is automatic: a byte-period of G always
decomposes as 8 sub-units of G bits, since 8·G bits = G bytes.

### The counter structure does NOT appear in the period-7 family

Bit-granular search (`scratchpad/bitfields.py`), scanning every field offset `0..S-1` and widths
6/8/10/12/16, scored by monotone fraction against a **shuffled-record-order control**:

| file | S=7 | 14 | 28 | 49 | 56 | 98 | 196 | **392** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Blues_BB_Score.mus *(positive control)* | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **258** |
| Bach Concerto.MUS | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 13_Petrushka_Score.mus | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The tool is validated and *specific*: it finds 258 counter fields at the correct stride and **zero** at
384 or 400 bits, so it is not a permissive test that fires on anything.

**Conclusion: the lag-7 autocorrelation peak is not a counter-bearing record stride.** The period-7
family shows no counter fields at 7 or 56 bits (or anything else tried). What causes that peak remains
**unexplained** — plausibly byte-aligned 7-byte structures carrying no counters, but that is untested.
Caveat: those files were probed from one anchor each, and Petrushka's anchor had only 19 occurrences.

### A directly readable record: 5-byte, byte-aligned, with a visible counter

The payload of `Blues_BB_Score.mus` opens at `0x200` with structure legible in the raw bytes — no
analysis needed. From `0x215`, in 5-byte rows:

```
0x0021A  e4 4f e6 bf 8a     counter 0xE64F
0x0021F  e4 6f e6 3f 8b            0xE66F   +0x20
0x00224  e4 8f e6 bf 8b            0xE68F   +0x20
0x00229  e4 af e6 3f 8c            0xE6AF   +0x20
0x0022E  e4 cf e6 3f 8e            0xE6CF   +0x20
0x00233  e4 ef e6 bf 8e            0xE6EF   +0x20
0x00238  e4 0f e7 3f 8f            0xE70F   +0x20   <- carries into the high byte
0x0023D  e4 2f e7 3f 91            0xE72F   +0x20
0x00242  e4 2f e8 3f 81            0xE82F   +0x100  <- discontinuity, new group
```

**5-byte records with a 16-bit counter incrementing by exactly `0x20`.** `0x20` = 2⁵, so the underlying
value increments by **1** and sits 5 bits up in the field — the same signature the doubling ladder
established, but here visible without any tooling. Byte 3 alternates `3f`/`bf` (a single `0x80` flag);
byte 4 drifts `8a 8a 8b 8b 8c 8e 8e 8f 91`, plausibly a staff or pitch index.

Note this region is **byte-aligned**: 5 bytes = 40 bits, a multiple of 8, so there is no bit-phase
drift and the counter's scale stays fixed at ×32. That contrasts with the 49-byte region, whose
sub-units are 49 bits and whose phase walks one bit per record. **The format mixes byte-aligned and
non-byte-aligned record types**, consistent with the dominant period varying by document.

This is the best starting point for field-layout work: a short, byte-aligned record with an
unambiguous counter, at a known offset, in a file already characterised.

### Byte histogram: strongly non-uniform, and dominated by runs of 1-bits

Measured on the 2005 payload (`Blues_BB_Score.mus`, 122,253 bytes). Earlier histogram work looked only
at a 2012 file, which is nearly flat — that masked this.

- **chi-square vs uniform = 56,784** against df = 255. Overwhelmingly non-uniform.
- Most/least common byte ratio **19.8×** (2,634 vs 133).
- Top bytes: `FF` 2.15%, `7F` 1.50%, `3F` 1.49%, `FE` 1.24%, `E2`, `F8`, `FC`, `F1`, `9F`, `7E`, `FD`,
  `1F`, `7C` — against 0.39% uniform.

Nearly all of the leaders are **runs of consecutive 1-bits at different alignments**: `FF`=11111111,
`7F`=01111111, `3F`=00111111, `FE`=11111110, `F8`=11111000, `1F`=00011111, `7C`=01111100. Both the low
and high nibble show `0xF` at ~14% against 6.25% uniform.

This is exactly the fingerprint of **all-ones fields smeared across bit offsets by the packing** — a
16- or 24-bit field of `1`s lands at each of the 8 alignments and produces precisely this family of
byte values. Corroborated directly:

| file | cohort | fraction of 1-bits | longest run of 1s |
| --- | --- | --- | --- |
| Blues_BB_Score.mus | 2005 | 0.5349 | 22 bits |
| 9_Gifts.mus | 2005 | 0.5436 | 26 bits |
| Bach Concerto.MUS | 2001 | 0.5548 | 23 bits |

1-bits are over-represented in every cohort, with runs of ~3 bytes of solid 1s. **The natural reading
is that unset/default fields are stored as all-ones (`-1` / `0xFFFF` "none" sentinels)** — a very
common convention — rather than as zeros. Note the complement is *not* a fix-all: inverting makes
`0x00` the top byte at only 2.15%, far below the 10–30% zero rate typical of plain record data, so the
all-ones fields are localised rather than pervasive.

### Per-column histograms confirm the 5-byte field structure

Splitting the 5-byte record region (`0x215`, 160 records) by column position:

| column | distinct values | entropy | most common |
| --- | --- | --- | --- |
| 0 | 74 | **5.11** | `E4` 22%, `BF` 11%, `3F` 9% |
| 1 | 82 | 6.02 | `8F` 4%, `0F` 4%, `4F` 4% |
| 2 | 74 | **5.38** | `E4` 18%, `EA` 6%, `E9` 6% |
| 3 | 78 | 5.65 | `3F` 11%, `BF` 11% |
| 4 | 92 | 6.18 | `E8` 6%, `E6` 4%, `E9` 4% |

**Every column sits at 5.1–6.2 bits against 7.75 for the payload as a whole.** Slicing on the 5-byte
period recovers ~2 bits per byte of structure, which only happens if the period genuinely aligns to
fields. Columns 0 and 2 are the most constrained (tag-like); 1 and 4 look like value fields; column 3
carries the `3f`/`bf` flag already noted. This is independent confirmation of the record layout and a
concrete handle for naming fields.

### Methodological note: always put a known-positive in the sweep

The first run of this sweep returned **zero for every file and every stride, including
`Blues_BB_Score` at S=392** — where 258 fields had been found minutes earlier. The cause was `K=300`
records per scan: the counters reset periodically, so a long window drags the monotone fraction below
threshold. The positive control is the only reason this was caught rather than written up as a clean
negative. **Any sweep here must carry a case known to fire, and `K` must stay near 60.**

## Headline finding

**The payload is transformed (not plaintext) at ~7.98 bits/byte, but it is neither LZ-family
compression nor encryption.** It carries long exactly-repeated substrings that both of those would
destroy, and identical content encodes identically at arbitrary byte offsets. The transform is
**byte-aligned, byte-oriented, static and context-free**. See "the payload contains long repeats"
below — that section supersedes any older framing of this as "compressed or encrypted", and it
explains why every standard codec tried so far has failed.

Read this document top to bottom before running anything; several of the numbers it used to quote
turned out to be measurement artifacts, and they are corrected in place.

### Correction: the payload entropy is 7.985, not 7.50

Measured over `0x200`→EOF on a confirmed-pair file: **7.985 bits/byte**, and *uniform* — 4 KiB
windows run min 7.76 / median 7.89 / max 7.93 with none below 7.0, all 256 byte values present, and
per-column entropy at strides 2, 3 and 4 flat at ~7.98 (so no field alignment or nibble structure).

The older 7.50 figure evidently averaged in the plaintext header and low-entropy preamble. This
matters because 7.50 would have been *anomalously low* for a codec — an interesting clue pointing
away from compression. 7.985 is not anomalous at all: it is exactly what a well-compressed or
encrypted stream looks like. **Do not build arguments on the 7.5 number.**

### Beware window-size artifacts when measuring entropy

A 96-byte window cannot exceed log2(96) = 6.58 bits, so it reads ~6.2 even for random data and shows
a "plateau" that is purely an artifact of the window. Use a window of at least 1 KiB to resolve
high-entropy data at all — and remember that a 1 KiB window cannot localise a transition to better
than ~1 KiB, so it is the wrong tool for pinning the exact stream start.

### Plain LZSS — RULED OUT (on a reliable oracle)

Okumura-lineage LZSS (literal/match tokens, 4096-byte ring buffer, **no** Huffman) is **not** the
transform. Tested against a **confirmed same-document pair** (see the oracle below): across every
variant (flag polarity × LSB/MSB bit order × ring init `0x20`/`0x00` × four offset/length layouts ×
threshold 2/3) and every stream-start offset `0xA0`–`0x900`, **no decode recovers even 5 of the 113
known strings**. A correct or even partial LZSS decode would leak matching literal bytes; it leaks
none. (An earlier apparent "entropy collapse to ~1.7" was the decoder desyncing into the ring
buffer's `0x20` space-fill — an artifact, not a decode. Do not be fooled by low output entropy.)

### Decoders are now validated before use — and how

The previous round's LZH negative was untrustworthy because the decoder itself had never been tested.
That is fixed, and the technique generalises: **fetch a real archive plus its known plaintext, and
require byte-exact reproduction before believing any negative.**

| Decoder | Test vector | Result |
| --- | --- | --- |
| LHA `-lh5-` (`scratchpad/lha.py`) | `fragglet/lhasa` `test/archives/lha_unix114i/h0_lh5.lzh` — 18,092 bytes of GPL-2 text, 6,996 compressed | **byte-exact, 18,092/18,092** |
| PKWARE DCL (`scratchpad/blast.py`, port of zlib `contrib/blast`) | the vector in blast.c's own header comment: `00 04 82 24 25 8f 80 7f` → `AIAIAIAIAIAIA` | **exact** |

Both vectors are fetchable from GitHub, which the sandbox allows. `7z` on this machine also reads
LZH, giving an independent cross-check of the ground truth.

### LZH / LHA — excluded, but by argument rather than by sweep

Be precise about what was and was not run. The decoder is now validated (above), and a sweep over the
entropy-transition window (`0x100`–`0x280` × 8 bit-shifts × `DICBIT` 12–16, 1,454 successful decodes)
returned **0 crib hits**. The *full*-range sweep (`0xA0`–`0x900`, several confirmed pairs) was started
repeatedly but never completed — background jobs kept being killed — so **no full-range empirical
negative exists.**

It does not matter: LZH is LZ-family, and the repeat evidence above excludes the entire family on
structural grounds. Treat LZH as ruled out **by that argument**, and do not spend more time sweeping
it.

### PKWARE DCL "implode" — RULED OUT

Plausible on era grounds (a widely licensed commercial compressor when `.mus` was designed) and not
covered by any stdlib module. Its header is byte-aligned and tightly constrained — `lit ∈ {0,1}`,
`dict ∈ {4,5,6}` — a 1-in-10,922 filter, so a whole-file scan is nearly free and *every* candidate
can be tried in full rather than sampled. Real `.mus` files yield only **1–3 candidate offsets each**;
none produces ≥256 bytes of output containing any crib, across the confirmed pairs tested. Noise
floor 0.

### ⚠️ The payload contains long repeats — so it is NOT LZ-compressed and NOT encrypted

This is the most important result so far and it reframes everything above.

Counting repeated n-grams in the high-entropy region (`0x200`→ start of the trailing plist, 51,200
bytes) against random bytes of the same length:

| n-gram | distinct repeated (`.mus`) | occurrences | distinct repeated (random) |
| --- | --- | --- | --- |
| 8 | 374 | 1,100 | **0** |
| 16 | 167 | 475 | **0** |
| 24 | 72 | 206 | **0** |
| 32 | 16 | 52 | **0** |

Random — and therefore any well-compressed or encrypted stream — contains **zero** repeated 8-grams
at this scale, let alone 32-grams. The chance of even one is vanishingly small (n²/2 / 2⁶⁴).

The repeats are predominantly **short-period tandem runs**. A representative example: a 4-byte group
repeated six times back-to-back (24 bytes), where that 4-byte value occurs **nowhere else in the
file**. The dominant repeat gaps are 4 (118×), 7 (27×), 41 (23×), then a long tail; the GCD of all
gaps is 1, so this is not a repeating-key period. Neighbouring bytes show the same pattern one byte
off (period-5 and period-6 near-repeats differing in a single byte).

**Why this is decisive:**
- **No LZ-family codec can emit this.** An LZ77/LZSS/LZH/DEFLATE/DCL/LZW coder encodes a tandem run
  as a *match*; emitting the run literally is precisely what it exists to avoid.
- **No stream cipher can emit this.** Ciphertext has no repeats.

This explains the entire run of negatives at a stroke — LZSS, LZW, DEFLATE, bzip2, lzma, PKWARE DCL
(and LZH) all failed because **the codec is not in that family at all**, not because of a decoder bug
or a missed parameter.

### The coding DOES vary by Finale version — and the corpus splits in two

Surveyed across **all 238 `.mus` files** (note: 137 are lowercase `.mus`, 101 are uppercase `.MUS` —
a case-sensitive glob silently drops the entire Windows cohort). Entropy and repeat counts measured on
a **fixed 16 KiB payload sample**, because entropy estimates are size-biased and the cohorts have very
different file sizes:

| banner year / platform | n | entropy (16 KiB sample) | vendor in banner |
| --- | --- | --- | --- |
| 2001 / WIN | 101 | 7.645 | Coda Music |
| 2004 / MAC | 1 | 7.667 | Coda Music |
| 2005 / MAC | 36 | 7.640 | MakeMusic |
| 2011 / MAC | 89 | 7.965 | MakeMusic |
| 2012 / MAC | 10 | 7.960 | MakeMusic |
| *(random reference)* | — | 7.989 | — |

**Two regimes**, and the gap is not a sample-size artifact — it survives fixed-size sampling. The
2001–2005 files are measurably *less dense* (7.64–7.67) than the 2011–2012 files (7.96), which sit
close to random. So a decoder that works on one era should not be assumed to work on the other, and
any future result must state which cohort it was established on.

**What does generalise:** the long-exact-repeat signature appears in every cohort — only 2 files out
of 238 show zero repeated 16-grams over the whole payload. So "not LZ-family, not a cipher" is a
property of the format across all versions, not an artifact of the single 2012-era file the argument
was first built on.

### The payload is regionally heterogeneous, not one uniform stream

Per-8 KiB windows through a large 2005/MAC payload: entropy swings between **6.816 and 7.791**, and
repeated 16-grams cluster hard — 500 in one window, 0 in several others, 114–218 across a contiguous
band. A single compressed stream would be statistically uniform end to end. This is not that.

It reads as distinct record pools with very different internal redundancy, whose local statistics
survive into the output — which is itself further evidence for static, context-free coding.

**Practical consequence: attack the 2005/MAC cohort, not the 2011/2012 files.** It has the lowest
entropy (7.640), the most repeats (median 2,037 repeated 16-grams over the whole payload), the largest
files (median 70,686 bytes), and 36 files to cross-check against. More surviving structure means more
to grip. Most of the analysis so far used a 2012-era file — the hardest case.

### Working the 2005/MAC cohort: a differential oracle and the record template

**The 85-pair `.musx` oracle does NOT cover this cohort — 0 of the 36 files has a stem-matched
`.musx`.** That is the cost of switching targets: more surviving structure, no known-plaintext.

**Replacement oracle: `9_Gifts.mus` vs `9_Gifts_No_Lyrics.mus`** (Chapter_9_Folder) — the same
document with and without lyrics, 78,493 vs 76,896 bytes. They are **byte-identical for the first
0x1182D (91% of the file)**, and every lyric-related difference sits in the tail from `0x11833` to
EOF: 26 regions, 3,385 bytes present only in the lyrics version, the largest a contiguous **831-byte
block**. So lyrics occupy their own pool at the tail, and an entire pool can be added without
perturbing a single byte before it — an independent, very strong confirmation that the coding is
local and context-free.

Useful negative: `10_Bach_3`/`10_Bach_4` and `8_Entertainer_3`/`8_Entertainer_4` look like minimal
pairs from the filenames but are **not** (15.2% and 29.3% identical, first difference at `0x57` and
`0x204`). They are different exercise stages, not small edits. Don't use them as differentials.

**Byte-orientation re-confirmed on this cohort, by a different method.** Within the homogeneous
1,022-byte lyrics-only block: 282 distinct repeated 32-bit windows, and **99.8% of their gaps are
byte-aligned** (a bitstream would give ~12.5%; random data gives no repeats at all). This is a
within-file measurement on an independent cohort, so it does not lean on the earlier cross-file test.

**The record template.** Records are built from 4-byte groups at *variable* spacing (motif gaps run
33–98 bytes). Four groups recur as constants — `ee 27 90 fc`, `b8 9f 40 f2`, `e2 7e 02 c9`,
`89 fb 09 24` — with no bit-rotation relationship between them (checked all 32 rotations pairwise).
Aligning on `ee 27 90 fc` (14 occurrences) exposes **monotonically increasing counter fields**:

| field position | observed sequence |
| --- | --- |
| byte before the motif | `23 23 24 24 25 25 26 27 27 28 28 29` |
| +4 bytes after motif | `8d 8f 91 93 95 96 98 9a 9c 9e … a4` (steps of 1–2) |
| +12 bytes after motif | `38 40 48 4e 5c 62 6a 74 …` |

**Clean monotone counters are not something any compressor emits.** Together with the constant
templates, this says the payload is a **structured record stream**, not compressed output — which
finally reconciles the whole picture: high entropy and repeats coexist because this is *dense
bit-packed record data*, not a codec's output. (The counters stepping by 1–2 and by 8 hint that
fields sit at different bit offsets within their bytes, i.e. packed fields rather than byte-aligned
integers — worth confirming.)

**The lyric text is still not directly readable.** Tested against the lyrics-only block: all 8 global
bit-shifts, complement, bit-reversal, and all 7 byte rotations. Best printable-ASCII fraction 35.7%,
*below* the ~37% a random buffer scores. So no single global byte transform exposes the text.

### Known-plaintext isomorph attack — the text is genuinely compressed

The paired `.musx` files give **exact lyric text** for `.mus` files we hold. `Angels We Have
Heard.mus` (51,674 B, banner 2012/MAC) has a confirmed pair whose EnigmaXML yields the verse
syllable-hyphenated exactly as Finale stores it (189 B). That is byte-level known plaintext, and it
supports an attack that does not require guessing the transform.

**Method (`scratchpad/isomorph.py`).** If the text is stored under *any* fixed byte substitution, the
**equality pattern** survives: wherever the plaintext repeats a character, the stored bytes repeat at
the same relative offsets. Signature = for each position, the distance back to the previous occurrence
of that byte. Match signatures instead of bytes, and a hit yields the substitution map for free.

**The method is validated by controls, which is what makes the negative usable:**

| control | score |
| --- | --- |
| plaintext planted in random bytes | **40/40** |
| plaintext planted after a **random bijection** | **40/40** |
| pure random, no plaintext present | 21/40 (noise floor) |
| **actual `.mus`** | **28/40**, located at `0x000D7` |

The second row is the important one: the method recovers text under a substitution it was never told
about. The real file scores barely above noise, and its best window sits at `0x000D7` — inside the
**plaintext title metadata**, which is text-like and therefore shares equality statistics with English.
That is not the lyric pool.

Extended to cover bit-level packing (which the 2005 counter fields hinted at): all 8 global bit-shifts
of the file score 22–28/40, and a 7-bit unpacking scores 22/40. All noise.

**Conclusion: the lyric text is not stored as characters under any substitution, bit alignment, or
7-bit packing. It is compressed.**

### Where that leaves the model — and an open tension

Everything measured now points at one surviving model: a **static, context-free, byte-aligned,
variable-length code** — a codebook/static-dictionary compressor. That fits every constraint
simultaneously: repeats survive (same input substring → same output bytes), position-independence
holds, output is byte-aligned, entropy is high, and the code is not 1:1 so isomorph correctly fails.
Note this is *not* the same as adaptive LZW, which was ruled out earlier — a **static** dictionary is
still open.

**Honest tension to resolve:** this sits awkwardly with the 2005 cohort's clean monotone counter
fields, since compressors do not usually emit tidy counters. Three ways it could reconcile — (a) the
code is order-preserving, so monotone source values stay monotone through it; (b) the payload is
mixed, with record scaffolding coded more literally than text; (c) the counter reading was
over-interpreted from 14 samples. **Do not treat either the "structured record stream" reading or the
"compressed" reading as settled until this is resolved.** Deciding it is the next real step: extract
the same counter fields from many more records and check whether the increments stay locally
consistent, which (a) and (b) predict and (c) does not.

Two further measurements narrow it sharply.

**Different pieces share long identical payload runs, at arbitrary byte shifts.** Comparing the
payloads of two *different* carols from one collection: **81 common runs of ≥8 bytes, the longest 67
bytes**, with the matches sitting at shifts of −356, −361 and −362 bytes. Identical source content
(shared Finale default records) therefore encodes to identical output *regardless of its absolute
position*. This independently re-confirms "not a cipher" — a keystream XOR is position-dependent, so
identical plaintext at different offsets could never give identical ciphertext — and it also rules out
**adaptive** coding (FGK/Vitter, adaptive arithmetic), whose coder state depends on everything
preceding and so could not reproduce a 67-byte match after different history.

**The alignment is byte, not bit.** Re-running that cross-file comparison with file B shifted by each
of 0–7 bits: shift 0 gives 81 runs / 1,316 bytes / longest 67; **every other shift gives 0–2 runs of
exactly 8 bytes** (noise). A static Huffman or arithmetic *bitstream* would scatter matches across all
eight shifts, since identical symbols land on arbitrary bit boundaries. It does not. **So the earlier
"order-0 Huffman/arithmetic bitstream" guess is refuted** — do not pursue it.

So the transform is: **byte-aligned, byte-oriented, static, and context-free (position-independent),
while still producing ~7.98 bits/byte.** Order-1 conditional entropy is 6.773 against 6.981 for random
bytes and 6.898 for zlib output at the same sample size — a real but modest deficit, consistent with
the localised repeats rather than with broad residual structure.

That combination is genuinely constraining, and it is the thing to explain next. A plain byte→byte
substitution fits every structural property but cannot produce 7.98 bits/byte from record data (a
substitution preserves the histogram shape). Something that emits **whole bytes from a fixed table or
dictionary** fits better. Resolving that tension is the open question.

### The oracle (key research asset)

**85 of the 97 stem-matched `.mus`/`.musx` pairs are confirmed to be the SAME document**, by matching
`created` provenance stamps (`year/month/day`, application, platform) — read decode-independently from
both formats (`version/mus.py` for `.mus`; `detect_version(...).detail.created` for `.musx`). The
`modified` stamps often differ (the `.musx` was re-saved later, e.g. MAC 2010 → WIN 2015), but the
`created` stamp is the document's birth certificate. These 85 pairs give **reliable known-plaintext**:
the `.musx` decodes to the exact text/structure the `.mus` also contains. Score any candidate decode
by long *contiguous* recovered text on a confirmed pair — never by low entropy or scattered short
hits. (`ProvenanceStamp` fields are `year/month/day`, not `.date` — an early bug.)

## What was ruled out (do not re-derive)

The payload is **compressed, not plaintext and not simply encrypted**. Confirmed transforms that do
**not** apply:

- `score.dat`'s XOR-LCG cipher — applying it *raises* entropy (7.50 → 7.98).
- gzip, zlib (no magic anywhere), **raw DEFLATE** (no offset inflates), **bzip2**, **lzma**, **LZW**.
- Repeating-key (Vigenère) XOR of any period 1–64 — no period collapses entropy; the lag-5
  autocorrelation peak is spurious (modal per-column byte is `0xFF`, a bit-flip).
- Fixed-key stream XOR — modal-byte keystream recovery fails to decrypt; the elevated zero rate in
  file⊕file (3.3%) comes from **shared identical template regions** (one ~1185-byte run between two
  files), not a shared keystream (the rest of file⊕file is random, scattered length-1 zeros).
- Not plaintext structured binary *in the payload region*: known `.musx` lyric strings appear in **no**
  encoding (Latin-1 / UTF-16 / Mac-Roman / CP1252) there. **But note the correction below — document
  title, composer and copyright ARE stored as plain ASCII in the preamble.**
- **PKWARE DCL "implode"** — ruled out with a *validated* decoder (see below).
- **A chain of length-prefixed records** — ruled out. If the payload were many small independently
  compressed blocks, no single stream start would exist and every whole-stream negative would be
  explained at a stroke. It is not: walking `length → jump → length` from every start in
  `0x80`–`0x400`, over `u16`/`u32` × LE/BE × header extra 0/2/4 × length-inclusive/exclusive, the
  **longest consistent chain in a real `.mus` is 6 hops — identical to the 6 hops random bytes
  produce**, and none reaches EOF.
- **The `score.dat` keystream at *any* alignment.** The earlier test applied MakeMusic's own cipher at
  a single alignment; since the payload starts at a data-dependent offset, alignment was the whole
  unknown. Searched properly: for each candidate offset `p` and each compressed-format magic `m`, the
  keystream window that *would* be required is `data[p:p+n] XOR m`, so searching that string inside
  the fixed 128 KiB keystream block settles every alignment in one pass. 40,533 raw magic
  coincidences (expected — a 3-byte magic in 128 KiB hits by chance ~30× per file), of which 32,846
  were then **actually fed to a decompressor**. Exactly one survivor produced output, and it was an
  artifact: a raw-DEFLATE *stored* block, i.e. the "output" is a verbatim copy of the input
  (confirmed `out[:200] == input[5:205]`, entropy 7.996). No alignment yields a decodable stream.

### Two scoring traps that have already cost this investigation time

**"The decoder ran without throwing" is not evidence.** Measured on the LHA decoder: **random bytes
decode to the output cap in ~18% of trials** (591 of 3,200). Huffman tables built from noise are
still valid tables. Score only on *content*.

**Long cribs cannot falsify anything.** A 100-character known string can only match a decode that is
perfectly synchronised for 100 characters, so scoring it at zero tells you nothing about a partially
correct decode. Use **short cribs (6–16 chars)** — words from the paired `.musx` text pool plus
standard font names. Calibrate on random input: the short-crib score has a measured false-positive
floor of **0 hits across ~12,300 successful decodes**, so any nonzero hit is real signal.

## Structural map (offsets, little-endian)

- `0x00`–`0xA0` — plaintext header: `ENIGMA BINARY FILE`, version banner (`0x20`), provenance stamps
  (`0x66`–`0x9D`). Already decoded by `version/mus.py`.
- `0xA0`–`0xA6` — small fixed marker (`04 01 0A …`, same in ~36/50 files).
- `0xA6`–~`0xD6` — run of `0x00`.
- ~`0xD8`–~`0x200` — a **fixed-size metadata block** which, *when populated*, holds **plain-ASCII
  document metadata**, NUL-terminated: title at `0xD8`, then composer, copyright line, and the
  document-style description. Confirmed by diffing two `.mus` files from the same collection: they are
  byte-identical up to `0xD8` and diverge exactly at the first character of the title.
  **It is frequently empty.** `Blues_BB_Score.mus` is all `0x00` from `0xA6` straight through `0x1FF` —
  the Berklee exercise files simply carry no title/composer. So `0xD8` is where the title *goes*, not
  where one is always found; a reader must not assume text is present. The block can also be
  byte-identical across different pieces (shared Finale defaults).
- ~`0x200` — the **high-entropy payload begins**, at a *data-dependent* offset with no constant magic.
  (A 1024-byte entropy profile saturates by `0x180`, but a window that wide cannot localise a
  transition to better than its own width, and plain ASCII metadata is still present at `0x1BE`. So
  treat `~0x200` as the estimate and do not quote the profile as if it were precise.)
- End: 89/136 MAC files carry a trailing macOS plist (last 1–3%); trim it before decoding.

## Open problems / next steps (in priority order)

The oracle is built (85 confirmed pairs). The repeat finding above says the codec is **not LZ-family
and not a cipher**, so the search should move to entropy coders. **Stop testing LZ variants** — LZW,
LZS, LZRW and friends are all excluded by the same argument, and testing them is wasted effort.

1. **Characterise the repeats properly.** Cheapest next step and it constrains everything else.
   Measure the distribution of tandem-run periods and lengths across many files, and check whether run
   period correlates with anything structural. If the source is an order-0 coder over fixed-size
   records, the periods should cluster at a few values, not spread smoothly.
2. **Test order-0 entropy coders.** Static Huffman with a stored table (look for the table in the
   `0x180`–`0x200` preamble tail), adaptive/dynamic Huffman (FGK, Vitter), and arithmetic/range
   coding. For a *static* table the preamble is the place to look; for *adaptive* coding there is no
   table and the decode must start cold at the stream head.
3. **Exploit the shared preamble.** Files from one collection are byte-identical up to `0xD8`. Check
   how far into the *payload* two same-collection files stay identical: with an adaptive coder both
   start in the same state, so a shared prefix persists until the first content difference, and its
   length locates the true stream start precisely.
4. **Once decoded:** identify the format (map its records onto the existing 7-pool `EnigmaDocument` so
   `read_entry`/`locate_entries`/`decode_key`/`spell_note` attach unchanged), validate across all 238
   files, and wire up `read_mus_payload(path) -> bytes` (mirrors `score_xml`), then a
   `.mus → EnigmaDocument` parser.

### Validated-tool inventory (reuse these, don't rewrite them)

Both live in the session scratchpad and both pass their reference vectors:
`lha.py` (LHA `-lh4-/-lh5-/-lh6-/-lh7-`) and `blast.py` (PKWARE DCL). Keep the validation step
attached to any future decoder — an unvalidated decoder's negative result is worth nothing, which is
the single biggest time sink this investigation has hit.

## Method note

The 97 stem-matched `.mus`/`.musx` pairs are the key asset: the `.musx` decodes to known plaintext
(structure + text) that serves as the oracle for both cracking the LZSS variant and validating the
decoded records. Same-stem is not a guarantee of identical content, so prefer pairs with many
confirmed text hits when using them as ground truth.
