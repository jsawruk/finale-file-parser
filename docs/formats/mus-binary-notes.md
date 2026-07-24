# `.mus` (Enigma Binary File) — reverse-engineering notes

**Status:** active research (branch `research/mus-binary-format`). Not yet a shipped reader.
**Goal:** decode the `.mus` payload to plaintext so its records can populate the same
`EnigmaDocument` the `.musx` pipeline builds, giving `.mus`/`.musx` parity for free.

All findings below are from **structural analysis of the curated corpus (238 `.mus`, 401 `.musx`)**
plus permitted community documentation. Report counts/structure only — never corpus record values.

## Headline finding

**The payload is compressed or encrypted (not plaintext), and it is not any standard codec.** That
much is solid. What the transform *is* remains open.

### LZSS — leading hypothesis, NOT confirmed (a caution)

LZSS (Lempel–Ziv–Storer–Szymanski, Okumura lineage: literal/match tokens, 4096-byte ring buffer, no
Huffman) is a plausible lead — the blob's ~7.5-bit/byte entropy sits below the ~8.0 of gzip/zlib or
encryption, consistent with LZ-without-entropy-coding. **But an LZSS decode has not been made to
work.** A systematic grid of 64 variants (flag polarity × LSB/MSB bit order × ring init `0x20`/`0x00`
× four offset/length layouts × threshold 2/3) crossed with stream-start offsets **all desync** into
runs of the ring buffer's `0x20` fill (output entropy ~1.7, ~89% spaces).

**Do not mistake that entropy "collapse" for success** — any space-initialised ring-buffer decoder
emits spaces when it desyncs, so low output entropy is an *artifact*, not evidence of a correct
decode. Correct decompression of records/text would land around entropy ~4–5, which no variant
reached. The handful of known-plaintext hits (~4/113) is consistent with literal-byte leakage plus a
weak (same-filename-only) pairing, not a real decode.

**Before trusting any decode, get a trustworthy oracle** (see Method note): confirm a `.mus`/`.musx`
pair is the *same document* (e.g. matching creation stamps), then require long *contiguous* recovered
regions, not scattered short hits.

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

1. **Build a trustworthy oracle FIRST.** The stem-based pairing is unreliable (only ~4/113 hits even
   at best — likely wrong pieces or literal leakage). Confirm same-document pairs decode-independently
   — e.g. match `.mus` and `.musx` **creation stamps** (both formats carry provenance;
   `version/mus.py` reads the `.mus` side). Only a confirmed pair gives real known-plaintext. Without
   this, every decode attempt is scored against noise.
2. **Reconsider transform class with the oracle.** Do not assume LZSS. With real known-plaintext,
   test decisively: (a) is a long known string recoverable under *any* LZSS variant (contiguously)?
   (b) if not, is the blob a **stream cipher** (a two-time-pad / crib-drag with confirmed shared
   plaintext across two same-key files)? (c) other LZ variants (LZW with different width, LZ77
   framings, PackBits-on-tokens).
3. **If LZSS survives (2a):** pin flag polarity, offset/length layout+endianness, `THRESHOLD`, `F`,
   ring init, and the exact stream start (likely a preamble length/pointer field;
   decode-to-exact-expected-length is a good constraint). Success = long contiguous correct regions,
   output entropy ~4–5, high hit counts — NOT a low-entropy space desync.
4. **Identify the decompressed/decrypted format** — map its records onto the existing 7-pool
   `EnigmaDocument` so `read_entry`/`locate_entries`/`decode_key`/`spell_note` attach unchanged.
5. **Validate across all 238 files** and wire up `read_mus_payload(path) -> bytes` (mirrors
   `score_xml`), then a `.mus → EnigmaDocument` parser.

## Method note

The 97 stem-matched `.mus`/`.musx` pairs are the key asset: the `.musx` decodes to known plaintext
(structure + text) that serves as the oracle for both cracking the LZSS variant and validating the
decoded records. Same-stem is not a guarantee of identical content, so prefer pairs with many
confirmed text hits when using them as ground truth.
