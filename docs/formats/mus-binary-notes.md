# `.mus` (Enigma Binary File) — reverse-engineering notes

**Status:** active research (branch `research/mus-binary-format`). Not yet a shipped reader.
**Goal:** decode the `.mus` payload to plaintext so its records can populate the same
`EnigmaDocument` the `.musx` pipeline builds, giving `.mus`/`.musx` parity for free.

All findings below are from **structural analysis of the curated corpus (238 `.mus`, 401 `.musx`)**
plus permitted community documentation. Report counts/structure only — never corpus record values.

## Headline finding

**The payload is compressed or encrypted (not plaintext), and it is not any standard codec.** That
much is solid. What the transform *is* remains open.

### Plain LZSS — RULED OUT (on a reliable oracle)

Okumura-lineage LZSS (literal/match tokens, 4096-byte ring buffer, **no** Huffman) is **not** the
transform. Tested against a **confirmed same-document pair** (see the oracle below): across every
variant (flag polarity × LSB/MSB bit order × ring init `0x20`/`0x00` × four offset/length layouts ×
threshold 2/3) and every stream-start offset `0xA0`–`0x900`, **no decode recovers even 5 of the 113
known strings**. A correct or even partial LZSS decode would leak matching literal bytes; it leaks
none. (An earlier apparent "entropy collapse to ~1.7" was the decoder desyncing into the ring
buffer's `0x20` space-fill — an artifact, not a decode. Do not be fooled by low output entropy.)

### What that implies — leading candidates now

A decoder finding **no raw literal bytes** matching known text points to either:
1. **LZH / LHA (LZSS + Huffman)** — the Okumura-lineage codec where literals are *Huffman-coded*, so
   they never appear as raw bytes. Consistent with plain-LZSS finding nothing. **Top candidate.**
2. **Encryption** — literals hidden by a cipher, not a codec.

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

## Open problems / next steps (in priority order)

The oracle is built (85 confirmed pairs). Plain LZSS is ruled out. Remaining work:

1. **Test LZH / LHA (top candidate) — ATTEMPTED, INCONCLUSIVE.** A hand-written `-lh4-/-lh5-/-lh6-`
   decoder (dynamic Huffman: pre-tree → c_len → position table, then the slide loop; in
   `scratchpad/lha.py`) was scanned over start offsets `0xA0`–`0x900` × `DICBIT` 12/13/14 on a
   confirmed pair: **0/113 known-plaintext hits** (only `DICBIT=14` decodes ran without throwing, and
   those produced garbage to the length cap). **BUT this negative is untrustworthy** — the decoder is
   complex and *unvalidated*, so a bug (canonical-code assignment, the `c==7` pre-tree run, the
   position `(1<<(j-1))+getbits` step, or the MSB bit reader) is as likely as "not LHA."
   **Before concluding, validate the LHA decoder against a known `-lh5-` test vector** (a real LHA
   tool, or a crafted archive). Only a verified decoder makes a negative meaningful. Note the
   compressed-stream start is a data-dependent offset after the structured preamble.
2. **If LZH fails, test encryption.** Two-time-pad / crib-drag needs same-key + shared plaintext:
   look for two `.mus` files that are the same document (duplicate `created` stamps *within* the
   `.mus` set), then `A ⊕ B` cancels a fixed keystream. Or crib-drag a known plaintext string over one
   ciphertext to recover a keystream and test for LCG structure.
3. **Also worth trying** (cheap): LZW variants (Unix `compress` 9–16-bit with clear codes; TIFF/PDF
   EarlyChange), LZS (Stac), LZRW1 — all scored on a confirmed pair.
4. **Once decoded:** identify the format (map its records onto the existing 7-pool `EnigmaDocument` so
   `read_entry`/`locate_entries`/`decode_key`/`spell_note` attach unchanged), validate across all 238
   files, and wire up `read_mus_payload(path) -> bytes` (mirrors `score_xml`), then a
   `.mus → EnigmaDocument` parser.

## Method note

The 97 stem-matched `.mus`/`.musx` pairs are the key asset: the `.musx` decodes to known plaintext
(structure + text) that serves as the oracle for both cracking the LZSS variant and validating the
decoded records. Same-stem is not a guarantee of identical content, so prefer pairs with many
confirmed text hits when using them as ground truth.
