# `.mus` (Enigma Binary File) — reverse-engineering notes

**Status:** active research (branch `research/mus-binary-format`). Not yet a shipped reader.
**Goal:** decode the `.mus` payload to plaintext so its records can populate the same
`EnigmaDocument` the `.musx` pipeline builds, giving `.mus`/`.musx` parity for free.

All findings below are from **structural analysis of the curated corpus (238 `.mus`, 401 `.musx`)**
plus permitted community documentation. Report counts/structure only — never corpus record values.

## Headline finding

**The `.mus` payload is LZSS-compressed** (Lempel–Ziv–Storer–Szymanski, the Okumura lineage —
literal/match tokens with a 4096-byte ring buffer, *no* Huffman entropy stage). This is why every
standard codec fails and why the blob's entropy (~7.5 bits/byte) sits *below* the ~8.0 of gzip/zlib
or encryption: raw literal bytes diluted with match tokens.

Evidence: an LZSS decoder collapses the blob's entropy from ~7.5 to ~1.5–2.0 bits/byte, expands it
~3–4×, and — decisively — makes **known-plaintext text strings from the paired `.musx` appear in the
output**. The scheme is confirmed; the exact token variant is not yet pinned (see Open problems).

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
- Not plaintext structured binary: known `.musx` title/lyric strings appear in **no** encoding
  (Latin-1 / UTF-16 / Mac-Roman / CP1252) inside the raw `.mus`.

## Structural map (offsets, little-endian)

- `0x00`–`0xA0` — plaintext header: `ENIGMA BINARY FILE`, version banner (`0x20`), provenance stamps
  (`0x66`–`0x9D`). Already decoded by `version/mus.py`.
- `0xA0`–`0xA6` — small fixed marker (`04 01 0A …`, same in ~36/50 files).
- `0xA6`–~`0xD6` — run of `0x00`.
- ~`0xD8`–~`0x200+` — a **variable-length, lower-entropy structured preamble**; can be byte-identical
  across different pieces (shared Finale defaults). Contains some ASCII fragments (e.g. bytes at
  `0x205` render as `…nserts…`), so parts are plaintext.
- ~`0x209`–~`0x25F` — the **LZSS stream begins** here, at a *data-dependent* offset (no constant
  magic at the start). The exact start per file is not yet determined from a header field.
- End: 89/136 MAC files carry a trailing macOS plist (last 1–3%); trim it before decoding.

## Current best LZSS parameters (produces real strings but desyncs)

Okumura-style: `N = 4096` ring buffer initialised to `0x20` (space); `F = 18`; `THRESHOLD = 2`;
ring write position starts at `N − F`; flag bit **0 = literal**, **1 = match**; match token is two
bytes `b0 b1` with `offset = b0 | ((b1 & 0xF0) << 4)` and `length = (b1 & 0x0F) + THRESHOLD + 1`.

This recovers a *few* known strings per file (≈4/113) then **desyncs into ring-buffer spaces**
(output ~89% ASCII, entropy ~2.0 — space-dominated garbage). One wrong token desyncs everything
after it, so a variant detail is still off.

## Open problems / next steps (in priority order)

1. **Pin the exact LZSS variant** — systematically vary: flag-bit polarity, offset/length nibble
   layout and endianness, `THRESHOLD` (2 vs 3), `F` (17/18), ring init (`0x20` vs `0x00`) and start
   position `r`. **Validate by known-plaintext**: the correct variant yields long *contiguous*
   correct regions and high hit counts against a confirmed paired `.musx`, not a stable
   space-generating desync. The 97 stem-matched `.mus`/`.musx` pairs are the oracle (compute with the
   text internally; never print it).
2. **Find the exact stream start** — likely determined by the preamble structure (a length/pointer
   field), not a fixed offset. Decode-to-exact-expected-length is a good constraint once the variant
   is right.
3. **Identify the decompressed format** — output is ~89% ASCII, so likely the **ETF (Enigma
   Transportable File) tagged-text format** or Enigma text records. ETF is documented; map its
   records onto the existing 7-pool `EnigmaDocument` so `read_entry`/`locate_entries`/`decode_key`/
   `spell_note` attach unchanged.
4. **Validate across all 238 files** and wire up `read_mus_payload(path) -> bytes` (mirrors
   `score_xml`), then a `.mus → EnigmaDocument` parser.

## Method note

The 97 stem-matched `.mus`/`.musx` pairs are the key asset: the `.musx` decodes to known plaintext
(structure + text) that serves as the oracle for both cracking the LZSS variant and validating the
decoded records. Same-stem is not a guarantee of identical content, so prefer pairs with many
confirmed text hits when using them as ground truth.
