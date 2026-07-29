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
| `GF` frame hold | (staff, measure) | `clefPercent` at +4, frame per layer at +6 and +8 | every non-zero frame slot names a real frame, 4,785 of 4,785 |

**`fullName` at +30 is worth pausing on.** That is the same offset the 2011-era investigation
identified as the staff-name selector (`docs/formats/mus-staff-names.md`), and the spec confirms it
independently. In 2001 files the value *is* the text-block number — 150 of 167 named staves resolve
directly. In 2005 files 71 of 205 sit above the highest block in the document, which is the same
signature as the unresolved 2011 case. So the indirection appears between the two, and the 2001
files are the era where a `.mus` names its staves outright.

### The link that is missing

**A 2001-2005 file still does not build a `Score`**, and this is why: the (staff, measure) → frame
link reaches only part of the music. Only **4,196 of 14,191 `GF` records carry a frame at all**, and
**8,999 of 13,710 frames are named by nothing**. Walking `gfhold → frame → entry chain` reaches
20,622 of 70,428 entries — 29%.

The same measurement on the 2011 cohort, whose pipeline demonstrably works, returns **10,465 of
10,465 frames referenced** and 99% of gfholds carrying a frame. That control is what makes this a
finding rather than a bad metric, and it is pinned as a test.

So either `GF` is not the only holder of that link, or it holds it somewhere else in the records
where the frame slots are zero. Building a score on what is currently reachable would silently drop
71% of the notes, which is worse than not building one.

**A trap to record, because it cost real time.** Scanning for "which offset in `GF` resolves to a
frame most often" says **+4 in 116 of the 139 documents** — and +4 is `clefPercent`, which is 75 in
every corpus record. 75 is a valid frame number in any document with at least 75 frames, so it
resolves for every record in the big documents and none in the small ones. The right question is
whether an offset resolves *when it is non-zero*, not how often it resolves. This is the same shape
as the reserved-staff and `textRepeatText` palettes: a high hit rate across documents that is really
one constant meeting a large enough range.

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
