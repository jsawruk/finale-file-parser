# The 2001-2005 `.mus` container

139 of the 238 `.mus` files in the corpus — 58% — are from Finale 2001-2005. Every one of them was
recorded as unreadable past its first pool, on the belief that the era "packs all pools into one
stream with no known delimiters". That belief was wrong, and this is what is actually there.

## 1. What was wrong before

`read_mus_payload` decoded a single PKWARE DCL stream at the fixed offset `0x20A` and returned it.
That stream is real, and it is the `others` pool — but it is one of **four**, and it accounts for
about a quarter of the file. The rest of the file, including every note in the document, sat
undecoded behind it, and nothing reported that: the decode succeeded, so the file counted as
"decodes" in the payload sweep.

`0x20A` itself is now explained. It is `0x200` plus a ten-byte record header.

## 2. The container

From `0x200` to the last byte of the file, with no gaps and nothing after, a run of **pool records**:

| offset | size | field |
| --- | --- | --- |
| 0 | 2 | `kind` — 15 others, 16 details, 17 entries, 18 text |
| 2 | 4 | `length` — the whole record, **this header included** |
| 6 | 4 | checksum (not read here; absent when the pool is empty) |
| 10 | `length - 10` | a PKWARE DCL stream |

Walk it by adding `length` to the current position. All 139 documents land exactly on the last byte,
with kinds `(15, 16, 17, 18)` in that order every time.

**A `length` of exactly 6 means the pool is empty**: the record is the kind and the length, no
checksum and no stream. Three documents carry an empty entry pool that way. It has to be returned as
an empty pool rather than skipped — skipping it would shift the following pool's identity onto the
wrong record.

### Byte order

**Big-endian on Mac, little-endian on Windows**, and it governs the container *and* every field
inside every pool. 102 of the 139 are little-endian, 37 big-endian.

It is read off the file rather than assumed: the first record's kind is always 15, and 15 is only 15
one way round (the other way it is 3840). So the same check that finds the byte order is the check
that there is a container there at all, which is why it raises rather than defaulting.

## 3. The entry pool (kind 17)

**The same 38-byte slots as the 2011/2012 era**, in the same order, differing only in byte order. So
there is one entry decode, not one per era — `enigma.mus_entries` takes the byte order as a
parameter and nothing else changed.

The evidence, from a structural scan of all 136 non-empty pools — 71,801 entries, the 1,373 in the
two documents that the reader later rejects included:

* the slots tile every pool exactly;
* every entry has `SETBIT`;
* the durations take **sixteen distinct EDU values, and every one is a note value with 0-2 dots** —
  512, 256, 1024, 2048, 1536, 768, 4096, 128, 3072, 384, 8192, 64, 6144, 1792, 192, 3584. That is
  eighth, sixteenth, quarter, half, dotted quarter, dotted eighth, whole, thirty-second, dotted
  half, dotted sixteenth, breve, sixty-fourth, dotted whole, double-dotted quarter, double-dotted
  sixteenth, double-dotted half.

That last line is the load-bearing one. A wrong byte order or a wrong slot stride does not produce
sixteen musical durations; it scatters EDU across hundreds of arbitrary values.

So `read_mus_entries` returns **70,428 entries over 137 documents**. The two that fail both die in
`duration_from_edu`, which caps at 4096 and so rejects a breve (8192) and a dotted whole (6144).
**That is a limit of the note-value model, not of this container** — a `.musx` carrying a dotted
whole note fails the same way today. It is worth fixing on its own.

## 4. The record pools (kinds 15 and 16) — a different encoding

These are reachable now but they are **not** the 2011-era self-identifying variable-length records.
They are flat tables of fixed **16-byte rows** carrying ETF's two-character tags:

    others   [u16 cmper][2-char tag][12 bytes]      = ETF's "6 twobyte values"
    details  [u16 cmper1][u16 cmper2][2-char tag][10 bytes]  = ETF's "5 twobytes"

which is exactly what the vendored `docs/etfspec.pdf` describes: *"Each other contains enough space
for 6 twobyte values (or 3 fourbytes) and each detail holds 5 twobytes. If a structure cannot fit
into one other or detail there are multiple incidences of the tag and comparator(s)."* A record too
big for one row runs on into further rows under the same tag and key — the ETF "incidence" is a row
here.

Rows are sorted by tag, and each tag's rows are contiguous. The tags are ETF's own, so the spec
names them directly: `MS` measure spec keyed by measure number, `IS` instrument (staff) spec, `TX`
text block, `IU` the instrument-used list, `NG` staff group, `FL` the frame list. That last set
matters: `IU` is the staff layout order that `mus_document.UNTRANSLATED` records as unidentified in
the 2011 format.

Three independent checks that the row framing is right:

* `MS` rows are keyed 1, 2, 3, … over the measures, and the first row reads width, then beats 4 and
  divbeat 1024 — a 4/4 measure;
* the spec prints `^01(65534) …` through `^08(65534)` as its worked example of an options record;
  **tag `01`, `02`, `03` and `05` all appear at cmper 65534 in 37 of the 37 big-endian documents**,
  and 65534 is `OPTIONS_CMPER`, already known from the 2011 format;
* the spec prints `^CL(0,0) 144 0 0 0`; the detail row `CL` at (0,0) holds 144 in 34 of 38.

`read_mus_rows(path)` reads them. `read_mus_others`/`read_mus_details` still refuse a DCL-era pool
outright — verified, 0 of 139 accepted — because they implement the *other* encoding; refusing is
the point, since a walk that half-succeeded would hand `read_mus_document` fabricated records.

### What the rows say

Established across all 139 documents:

| record | key | fields | evidence |
| --- | --- | --- | --- |
| `MS` measure spec | measure number | `measpace, key, beats, divbeat, auxflag, meflag` | the spec's own `^MS(1) 600 0 4 1024 1 16`; 4,113 measures, every `beats` in 1–32 and every `divbeat` a note value; keyed 1..N with no gaps in 139/139 |
| `IS` staff spec | staff number | 3 incidences in a 2001 file, 6 in a 2005 one; `botLines` at +16, `transposition`, `fullName` at +30, `abbrvName` at +32 | the spec's worked example matches a corpus row verbatim; `fullName` resolves to a text block for 284 of 571 staves |
| `FR` frame | frame number | `startEntry` and `endEntry` as u32 at +0 and +4 | 99.1% of both are real entry numbers, over 13,322 frames |
| `GF` frame hold | (staff, measure) | a frame per layer, four of them, from a base of **+4 in a 2001 file and +6 in a 2005 one** | 13,241 of 13,322 frames are named; the base the staff-spec shape predicts is the one that reaches most entries in 134 of 134 documents |

**`fullName` at +30 is worth pausing on.** That is the same offset the 2011-era investigation
identified as the staff-name selector (`docs/formats/mus-staff-names.md`), and the spec confirms it
independently. In 2001 files the value *is* the text-block number — 150 of 167 named staves resolve
directly. In 2005 files 71 of 205 sit above the highest block in the document, which is the same
signature as the unresolved 2011 case. So the indirection appears between the two, and the 2001
files are the era where a `.mus` names its staves outright.

### The frame link, and a correction

The (staff, measure) → frame link is **where the frame array starts inside a `GF` record**, and it
moves between the eras: **+4 in a 2001 file, +6 in a 2005 one**, four layer slots from there. The
staff spec's incidence count — three or six — is what tells the eras apart, and it is already needed
to read `IS`.

| | frames referenced | entries reached |
| --- | --- | --- |
| base fixed at +6 | 4,711 of 13,322 | 20,622 of 70,428 (29.3%) |
| base by staff-spec shape | **13,241 of 13,322** | **64,993 of 70,428 (92.3%)** |

What makes this a rule rather than a fit: choosing the base per document by whichever reaches more
entries picks exactly what the staff-spec shape predicts, in **134 of 134 documents**.

> **Correction.** The previous revision of this document called +4 a coincidence — "`clefPercent`,
> which is 75 in every corpus record, and 75 is a valid frame number in any document with at least
> 75 frames". The premise was false: +4 is 75 in **5,205 of 14,191** records, in 34 documents, all
> of them 2005-era. That came from generalising a single sampled document, and it is the same
> mistake in the opposite direction from the palette traps this file warns about — there, a constant
> was mistaken for a reference; here, a reference was mistaken for a constant. The way to tell them
> apart is the same either way: look at the per-document distribution before calling anything
> constant.

**What is still unreached**: 5,302 entries in **16 documents** — and they are not unread music.
**They are dead space in a live database.** A `.mus` is written in place, so an entry deleted in
Finale keeps its 38-byte slot until the file is compacted; the pool therefore holds both the current
music and whatever earlier music has not yet been overwritten. The frames are what say which is
which, and an entry no frame reaches is the second kind.

That is the corpus's verdict, not a convenient reading. **4,675 of the 5,302 (88%) are exact
duplicates of passages the frames do reach** — matched as whole `next`-chains, sequence for
sequence, so shape-for-shape coincidence in tonal music is not the explanation. In the clearest
case a document keeps entries 1–858 as a stale copy of the live 859–1717, 824 of them identical
field for field. The remaining 12% are in three documents whose frames reach *nothing at all*,
leaving nothing to duplicate; those are refused outright rather than pruned to an empty score.

> **Two hypotheses died here, both cheaply, both before anything was built on them.**
>
> **They are not voice 2.** `docs/eeppd.txt` warns that "mirrors and voice 2 create complications",
> and voice-2 entries are marked in the entry flag — `CNTLBIT` 0x10000000 for a voice-2 note,
> `CNTLRBIT` 0x20000000 for the "V2 launch" controller. **Not one of the orphans carries either
> bit**, and the 146 voice-2 entries the corpus does contain are all reached already.
>
> **No frame's `endEntry` "stops short".** That reading assumed each frame owns a `next`-chain that
> terminates at its own end. It does not: the pool is **one** doubly-linked list per document, and a
> frame carves a segment out of it with `startEntry`/`endEntry`. Walking `next` from any frame's
> start runs on to the last entry in the file. A measurement built on the wrong model produced a
> confident "12,736 frames stop short" — of 13,306. The give-away was the size of the number: a
> defect that common is usually a defect in the question.

A control worth keeping: the same measurement on the 2011 cohort, whose pipeline demonstrably works,
returns 10,465 of 10,465 frames referenced. It is pinned as a test, and it is what showed the 34%
figure was the data speaking rather than a bad metric.

## 5. The text pool (kind 18)

Byte-identical in form to the 2011 era's text stream: `^block(1)^font(Times,8191)^size(24)^nfx(1)…`.
Nothing new is needed to read it.

## 6. What this does not do

A 2001-2005 file still does not open as a `Score`. What it does now is open as a *container*: four
labelled pools, the right way round, with the notes decoded. Building a score needs the field
layouts inside the 16-byte rows — `MS`, `IS`, `FL` at minimum.

And there is **no oracle for any of it**: not one of the 139 has a stem-matched `.musx`. Every
`.mus`/`.musx` comparison this project relies on is drawn from the 2011/2012 cohort. Verification
here has to come from internal consistency, from the ETF spec's own printed examples, and from
whether the numbers that come out are musically possible.

## 7. Building a `Score`

`read_mus_document` now takes the row path for a 2001-2005 file, so
`to_musicxml(build_score(read_mus_document(path)))` works on the cohort.
**129 of the 139 build**, giving 402 parts, 13,717 measures, 60,476 events and 66,847 pitches.

The translation reuses the 2011 field decoders rather than reimplementing them, because **the 2011
binary layout _is_ the ETF layout** — `measSpec`'s flags byte at +10 and `staffSpec`'s transposition
at +20 were derived independently from paired `.musx` files and land exactly where the ETF record
puts them. Only the byte order and the framing differ.

### What does not build, and why

| | documents |
| --- | --- |
| an entry two frames both claim | 1 |
| a gfhold placing entries in a measure that defines no key | 1 |
| a breve or dotted whole, which `duration_from_edu` rejects | 2 |
| no frame holds at all — a blank score | 3 |
| frame holds that resolve to nothing, so the whole pool is unreachable | 3 |

The orphan cases are gone from this table: since dead pool slots are discarded at the container
edge, `build_score` no longer sees them. **That deletion is exactly the kind that can hide a
regression**, so it is paid for with a pin. The sweep asserts the number of entries the reader
discards — 4,946 — and that number may only fall. A reader that quietly stopped *reaching* music
would discard more and fail there, where the build counts alone would merely get smaller: reverting
`_FRAME_LAYERS` from 4 to 2 pushes it to 6,004, and the pin catches it. `locate_entries`' orphan
check is left exactly as it was, and still fires for `.musx` and for 2011 `.mus`.

The last row is the empty-score trap in a third costume. Pruning turned three documents from
"rejected for orphans" into "builds a `Score` with no parts", and the aggregate totals stayed
green because a document contributing nothing changes no sum. Only the per-document assertion
caught it. They are now refused at the reader, with a message that says what is wrong.

The three blank scores are worth their own line, because of how they were found. They carry staves
and measures but no `GF` records at all, so they built a `Score` with **no parts** — and the
per-document totals in the new sweep were satisfied the whole time, because a document contributing
nothing changes no sum. What caught it was the export audit's "parts disagree about which measures
exist", asserted per document. The reader now refuses them outright, and the sweep asserts
per document that a built score has parts and music in them. Aggregates cannot see an empty file.

### One fallback, named as such

A frame's `startEntry`/`endEntry` pair is at +0 for 13,200 of 13,322 frames. The other 122 carry a
leading block — always a second incidence — that pushes the pair to +12, where 106 of them read
correctly. **What that leading block is has not been identified.** The reader takes whichever pair
names entries the pool actually holds, and drops the frame when neither does (16 frames). That is a
fallback, not an explanation, and it is worth replacing with the real rule.

Dropping a frame also drops the `gfhold` references to it: `build_score` rejects a gfhold naming a
frameSpec that is absent, so keeping the reference would cost the whole document instead of one
frame's music.
