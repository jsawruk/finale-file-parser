# `.mus` (Enigma Binary File) — reverse-engineering notes

**Status:** active research (branch `research/mus-binary-format`). Not yet a shipped reader.
**Goal:** decode the `.mus` payload to plaintext so its records can populate the same
`EnigmaDocument` the `.musx` pipeline builds, giving `.mus`/`.musx` parity for free.

All findings below are from **structural analysis of the curated corpus (238 `.mus`, 401 `.musx`)**
plus permitted community documentation. Report counts/structure only — never corpus record values.

## HEADLINE: the payload is a bit-packed record stream with a 49-bit stride — there is no codec

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

### Scope of the claim

Confirmed on `Blues_BB_Score.mus` for anchors `fefce77e` and `f7e73ff7`, and counter-like fields with a
collapsing shuffle control were also found in `9_Gifts.mus` (anchors `ff31f511`, `47fc63fc`, …). The
49-bit stride itself is so far established on one file. **Next: confirm the stride on more files and
across cohorts, and check whether 49 bits is universal or per-record-type.** Do not assume it is
universal yet.

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
- ~`0xD8`–~`0x200` — a **variable-length, lower-entropy structured preamble** holding **plain-ASCII
  document metadata**, NUL-terminated: title at `0xD8`, then composer, copyright line, and the
  document-style description. Confirmed by diffing two `.mus` files from the same collection: they are
  byte-identical up to `0xD8` and diverge exactly at the first character of the title. This region can
  be byte-identical across different pieces (shared Finale defaults).
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
