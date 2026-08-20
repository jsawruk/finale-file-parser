# ImHex pattern for `.mus` pools — design

**Status:** approved 2026-08-20.

**Goal:** someone reverse-engineering a Finale `.mus` runs one command, opens **one** file in
[ImHex](https://imhex.org/), loads **one** pattern, and can walk the whole document in a hex dump —
every pool, every record, at the offsets and types the parser itself uses.

## The obstacle, and why it is smaller than it looks

A `.mus` stores its payload as four compressed pools. A hex editor opens the file on disk and sees
the compressed bytes, so nothing useful is visible without decompression. ImHex can inflate zlib in
a pattern (`hex::dec::zlib_decompress`), which would cover the 2011-era files — but 139 of the
corpus's 238 documents are the 2001–2005 era, which uses PKWARE implode ("DCL"), and `hex::dec::`
has no implode.

**Implode is not needed inside ImHex.** It is needed only to open a *raw, untouched* `.mus`
directly. This project already decompresses both eras in Python — `enigma.blast` for DCL,
`zlib` for 2011 — so the answer is to decompress first and hand ImHex a file it can read straight
through. That covers both eras equally and needs no plugin, no upstream contribution, and no
implode outside Python.

Recorded so nobody re-derives it: the routes that *would* let a raw `.mus` open natively are an
ImHex plugin wrapping `blast` (there is precedent in ImHex-Zlib-Plugin, and both C++ and Rust plugin
templates exist) or contributing implode upstream to `hex::dec::`. Both are real and both buy only
the convenience of skipping one command, which is not worth a separate cross-platform project.

Implementing implode *in the pattern language* was also investigated and is not viable, for reasons
that are not about the format: every DCL file here uses uncoded literals with a 1 KB window, so
literals could in principle be copied from the input with `std::mem::copy_value_to_section` and
matches from earlier output with `copy_section_to_section` — but `std::mem` has no primitive to emit
a *computed* byte, overlapping LZ77 copies force byte-at-a-time loops, and the evaluator caps loop
iterations at 4096 by default with known bugs in the pragmas meant to raise it.

## Why the offsets are generated, not written

`finale_file_parser.formats.layouts` holds one `Layout` per decoded record type — `name`, `record`,
`tag` (2011 numeric), `dcl` (the two-character ETF tag), `pool`, and a list of
`Field(offset, size, name, type_, note)`. The parser reads it, the inspection report reads it, and
`make spec` renders the PDF specification from it. A hand-written `.hexpat` would be a second,
independent statement of every offset, free to drift the moment either changed.

So the pattern is **generated from that catalog** and committed, with a test that fails if the
committed copy is stale. Today the catalog is 12 layouts and 45 fields across five field types
(`uint16` 32, `int16` 6, `uint32` 3, `uint8` 2, `string` 2), in the `others` and `details` pools.

## 1. `finale-parser extract`

Writes **one** file holding every decompressed pool of a `.mus`.

```bash
finale-parser extract "2_Aura Lee.mus"        # writes 2_Aura Lee.pools.bin beside it
finale-parser extract ./scores -o ./pools     # a whole tree, layout preserved
```

`enigma.mus_payload.read_mus_pools(path) -> tuple[MusPool, ...]` already returns the decompressed
pools, each with its `data`, `byte_order` and `kind`, so this command adds **no format knowledge**.

### The file it writes

An 8-byte header, then the pool chain. Every header field is a single byte, so the header itself
has no byte order to get wrong:

    0-3   magic     "FMUS"
    4     version   1
    5     order     0 little, 1 big -- the order of every multi-byte field after this header
    6     era       0 = 2011/zlib, 1 = DCL (2001-2005)
    7     pools     pool count (4 in every corpus document)

    8-    the pool chain, each entry:
          0-1   kind      15 others, 16 details, 17 entries, 18 text
          2-5   length    the whole entry, this 10-byte header included
          6-9   checksum  the container's, or 0 where the container carries none
          10-   payload   `length - 10` decompressed bytes

**The chain is the DCL container's own framing**, not something invented for this file. A DCL `.mus`
already stores its payload as exactly this chain — kind, length, checksum, stream — laid end to end
from `0x200` with no gaps, and `length` already counts its own header. Two things differ from the
file on disk, and only two: each payload is decompressed, so `length` reflects the decompressed
size; and a magic header is prepended so the file announces what it is rather than impersonating a
`.mus`.

**An empty pool keeps its shape:** `length == 6`, no checksum and no payload, which is how the DCL
container itself says a pool exists and holds nothing. Three corpus documents carry an empty entry
pool that way, and a reader must be able to tell that from a pool that is missing.

**Byte order and era come from the source document**, which is why they are in the header: they are
not recoverable from decompressed pool bytes, and guessing wrong produces plausible-looking nonsense
— the worst failure a hex pattern has. 37 of the 139 DCL-era corpus documents are big-endian.

### Pool kinds for the 2011 era

A DCL container labels all four pools; a zlib-era container labels none. `extract` therefore
**identifies** them rather than leaving them numbered, using the same walks the readers already use
as their own "is this the right pool?" test:

- `mus_others._walk` succeeds only on an others pool.
- `mus_details._walk` succeeds only on a details pool.
- `mus_entries._looks_like_entry_pool` succeeds only on an entry pool.

Measured across all 99 zlib-era corpus documents: **99 of 99 identify others, details and entries
positively, with no ambiguity**, and always in that order. The fourth pool is the text pool **by
elimination** — no positive test for it exists — which matches the order the DCL container states
outright (15, 16, 17, 18). The extractor must record that distinction rather than blur it: three
kinds are identified and one is inferred, and if a document ever fails to identify all three, the
whole file is refused rather than written with a guessed label.

### Other behaviour

- `.musx` is **refused by name**: that container is a ZIP of encrypted, deflated XML with no pools
  of this kind, so there is nothing to extract. In a batch it is reported and skipped.
- Flags follow `convert`: `-o/--output`, `--force`, and the same batch behaviour over a directory —
  report and skip what fails, non-zero exit if anything was skipped.

## 2. `docs/formats/finale-mus.hexpat`

One pattern, generated from the catalog, that reads a `.pools.bin` end to end.

**It needs no configuration.** Order, era and pool kinds all come from the header, so there are no
`in` variables to set and no way to set them wrong. This is the main reason the header exists.

The pattern walks the chain, then parses each pool's records according to era and kind. **The two
eras store records differently** — this is the fact that shapes the file, and they are not merely
compressed differently:

*2011 pools* hold self-identifying, variable-length records:

    others    0-1 tag  2-3 cmper  4-5 part   6-9 length  10.. payload[length], then 4-byte trailer
    details   0-1 tag  2-3 cmper1 4-5 cmper2 6-7 inci    8-11 length  12.. payload, then extra

Records of one tag sit together in sections; sections may be separated by two-byte zero padding,
which the walk skips.

*DCL pools* hold tables of **fixed 16-byte rows** carrying ETF's two-character tags:

    others    0-1 cmper   2-3 tag                4-15  12 bytes
    details   0-1 cmper1  2-3 cmper2  4-5 tag    6-15  10 bytes

Two traps the generated pattern must handle, both of which a hand-written file would plausibly get
wrong:

- **The ETF tag is a `u16`, not two characters.** On a little-endian file its characters come out
  reversed — `^MS` is stored `SM`. Reading the pair verbatim finds no known tag in 102 of the 139
  corpus documents.
- **A record too big for one row runs on into further rows** under the same tag and key; ETF calls
  each row an *incidence*. A single row is a fragment, and the pattern must present it as one rather
  than implying a row is a whole record.

**Payload structs come from the catalog.** One struct per `Layout`, fields at the catalog's offsets
with the catalog's types, and each `Field.note` emitted as a comment so the pattern carries the same
evidence the parser does. The type mapping is total:

    uint8 -> u8      uint16 -> u16      uint32 -> u32      int16 -> s16
    string -> char[]  a NUL-terminated string running to the end of the payload. The catalog marks
             such a tail with `size == 0`, only the last field of a layout may use it, and its
             `note` says what ends it. Two layouts use one today.

Dispatch differs by era, because the catalog's two tag columns are not populated alike: 11 layouts
carry a 2011 numeric tag and 5 carry a DCL tag (`GF`, `DT`, `FR`, `MS`, `IS`). `TextExprDef` appears
twice on purpose — once for the DCL spelling, once for 2011 — because what is confirmed of the newer
record does not carry back to the older one.

**A tag with no layout shows its payload as raw bytes.** Inventing a structure for a record this
project has not decoded would put a guess into a format specification, which is the one thing such a
document must never do. Only 5 of 12 layouts carry a DCL tag, so this is the common case in the
older era — which is exactly where someone is doing the reverse engineering a hex editor is for.

## 3. Generator and currency test

`scripts/hexpat/` renders the pattern from `formats.layouts`, wired to a `make hexpat` target beside
the existing `make spec`. A test regenerates in memory and compares byte for byte with the committed
file, so adding a field to a layout either updates the pattern or fails the build.

That test also closes an existing gap: `docs/formats/finale-formats.{html,pdf}` are generated and
committed today with nothing checking the committed copies are current.

## What this does not do

- **It does not open a `.mus` directly.** Pointing ImHex at a score on disk still shows only the
  compressed container. The pattern's header comment and the README must say so plainly, and name
  the command that produces a file it *can* read.
- **It does not decode payloads this project has not decoded.** Coverage is exactly the catalog's.
- **It does not describe `.musx`**, which is a ZIP of encrypted, deflated XML with nothing a
  byte-offset pattern would help with.

## Testing

- The generator's output is pinned byte for byte against the committed pattern.
- Every `Layout` in the catalog appears in the generated pattern, and every field type in use maps
  to a hexpat type — asserted by iterating the catalog, so a new type fails loudly rather than
  silently emitting nothing.
- `extract` is covered like `convert`: single file, batch over a tree, `--force`, refusal to
  overwrite, and `.musx` refused by name.
- Round-trip, which is the real guard: reading the written file's chain back yields, for each pool,
  the same `kind`, `byte_order` and bytes that `read_mus_pools` returned. A framing bug that
  shifted a payload by one byte would pass every other test here and produce a hex dump that is
  wrong in a way a reader would trust.
- An empty pool round-trips as `length == 6` with no payload, distinct from an absent pool.
- A corpus sweep asserts extraction succeeds across both eras, that all three identifiable pool
  kinds are identified in every zlib-era document, and that each written chain re-reads. Report
  counts only — never a corpus filename, title or record value.

## Risk stated up front

**CI can prove the pattern is current, complete and type-correct against the catalog. It cannot
prove the pattern loads.** ImHex is not installable in this environment and there is no headless
evaluator for the pattern language here, so a syntax error would survive every test above. The
generated file needs opening in ImHex once by hand before this branch is trusted. This is a known,
accepted limitation of the plan rather than something to discover late.
