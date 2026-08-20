# ImHex pattern for `.mus` pools — design

**Status:** approved 2026-08-20.

**Goal:** someone reverse-engineering a Finale `.mus` can open its decompressed pools in
[ImHex](https://imhex.org/) and see every record this project knows how to read, laid out with the
same offsets, types and evidence the parser uses.

## Why this is not just a file you write once

The offsets already exist as data. `finale_file_parser.formats.layouts` holds one `Layout` per
decoded record type — `name`, `record`, `tag` (2011 numeric), `dcl` (the two-character ETF tag),
`pool`, and a list of `Field(offset, size, name, type_, note)`. The parser reads it, the inspection
report reads it, and `make spec` renders the PDF specification from it. A hand-written `.hexpat`
would be a second, independent statement of every offset, free to drift from the code the moment
either changed. So the pattern is **generated from the same catalog** and committed, with a test
that fails if the committed copy is stale.

Today's catalog is 12 layouts and 45 fields across five field types (`uint16` 32, `int16` 6,
`uint32` 3, `uint8` 2, `string` 2), in the `others` and `details` pools.

## Decisions already taken, and why

**ImHex only; no HexFiend.** HexFiend's binary templates are Tcl with no decompression at all, so
it could only ever describe a `.mus`'s outer envelope. ImHex can at least inflate.

**The pattern parses *extracted* pools, not a `.mus` on disk.** A hex editor sees the compressed
bytes. ImHex's `hex::dec::` namespace covers zlib, bzip, lzma, zstd and lz4 — there is no PKWARE
implode ("DCL"), which is what the 2001-2005 era uses, and that is 139 of the corpus's files.

Implementing implode inside the pattern language was investigated rather than dismissed. It is
closer to possible than it first appears: every one of those 139 files uses **uncoded literals**
with a 1 KB window, so each literal is a raw byte already present in the input, and `std::mem`
offers `copy_value_to_section` and `copy_section_to_section` — literals could be copied from the
input and matches from earlier in the output, with no computed bytes needed. What rules it out is
throughput and generality, not expressiveness: `std::mem` has no primitive to emit a *computed*
byte (so a coded-literal file would be impossible), overlapping LZ77 copies force byte-at-a-time
loops, and the evaluator caps loop iterations at 4096 by default with known bugs in the pragmas
meant to raise it. Decoded payloads here run to hundreds of kilobytes.

The routes that would let a raw `.mus` open natively — an ImHex plugin wrapping `blast`, or
contributing implode upstream to `hex::dec::` — are both viable and both out of scope here. They
are recorded so a later reader does not have to rediscover them.

**Generated and committed, not generated on demand.** An ImHex user should be able to download one
file, not install a Python package and run a command first.

## What gets built

### 1. `finale-parser extract`

Writes a `.mus`'s decompressed pools to disk, one file per pool.

`enigma.mus_payload.read_mus_pools(path) -> tuple[MusPool, ...]` already returns exactly this, so
the command adds **no format knowledge**: it is a CLI verb, a naming rule and file writing.
`MusPool` carries `data`, `byte_order` (`"little"` or `"big"`) and `kind` — the container's pool id
where the container labels its pools, and `None` where it does not.

Naming must carry what the bytes cannot say, because the pattern is told these facts by the user
and a wrong answer produces plausible-looking nonsense:

    <stem>.pool<N>-<kind>.<order>.bin      e.g.  Aura Lee.pool0-others.little.bin
    <stem>.pool<N>.<order>.bin             where the container does not label the pool

`kind` is `others` (15), `details` (16), `entries` (17) or `text` (18). A DCL-era file labels all
four. A zlib-era file labels none — `kind` is `None` for every pool — so those files get the second
form, numbered in file order. This is not a gap in the reader: that container genuinely does not
record what its pools are.

An **empty pool is written as a zero-byte file** rather than skipped. A DCL record whose declared
length is exactly 6 is the container's way of saying the pool exists and holds nothing, and three
corpus documents carry an empty entry pool that way; a missing file and an empty one mean different
things.

`.musx` is **refused by name**, not silently skipped: that container is a ZIP of encrypted, deflated
XML with no pools of this kind, so there is nothing for this command to extract. A batch over a
mixed directory reports each `.musx` as skipped with that reason, which is the existing
report-and-continue behaviour rather than a new one.

Flags follow `convert`: `-o/--output` for a destination directory, `--force` to overwrite, and the
same batch behaviour over a directory (report and skip what fails, non-zero exit if anything was
skipped).

### 2. `docs/formats/finale-mus.hexpat`

Parses one extracted pool. Two `in` variables drive it, rendered by ImHex as input widgets in the
Pattern Editor's Settings tab:

- `era` — `2011` or `dcl`.
- `endian` — `little` or `big`.

Neither is recoverable from an extracted pool's bytes, and both change the reading completely.
37 of the 139 DCL-era corpus documents are big-endian, so this is not a rare branch.

**The two eras store records differently**, which is the fact that shapes this file. They are not
merely compressed differently:

*2011 pools* are runs of self-identifying, variable-length records.

    others    0-1 tag  2-3 cmper  4-5 part   6-9 length  10.. payload[length]  then 4-byte trailer
    details   0-1 tag  2-3 cmper1 4-5 cmper2 6-7 inci    8-11 length  12.. payload, then extra

Records of one tag sit together in sections, and sections may be separated by two-byte zero
padding, which the walk skips.

*DCL pools* are tables of **fixed 16-byte rows** carrying ETF's two-character tags.

    others    0-1 cmper   2-3 tag                4-15  12 bytes
    details   0-1 cmper1  2-3 cmper2  4-5 tag    6-15  10 bytes

Two traps the pattern must get right, both of which a hand-written file would plausibly get wrong:

- **The ETF tag is a `u16`, not two characters.** On a little-endian file its characters come out
  reversed — `^MS` is stored `SM`. Reading the pair verbatim finds no known tag in 102 of the 139
  corpus documents.
- **A record too big for one row runs on into further rows** under the same tag and key — ETF calls
  each row an *incidence*. A single row is therefore a fragment, and the pattern must present it as
  one rather than implying a row is a whole record.

**Payload structs come from the catalog.** One struct per `Layout`, its fields at the catalog's
offsets with the catalog's types, and each `Field.note` emitted as a comment so the pattern carries
the same evidence the parser does. The type mapping is total and needs no special cases:

    uint8 -> u8      uint16 -> u16      uint32 -> u32      int16 -> s16
    string -> char[]  a NUL-terminated string running to the end of the payload. The catalog
             marks such a tail with `size == 0`, only the last field of a layout may use it, and
             its `note` says what ends it. Two layouts use one today.

Dispatch differs by era, because the catalog's two tag columns are not populated alike: 11 layouts
carry a 2011 numeric tag and 5 carry a DCL tag (`GF`, `DT`, `FR`, `MS`, `IS`). `TextExprDef` appears
twice on purpose — once for the DCL spelling and once for 2011 — because what is confirmed of the
newer record does not carry back to the older one.

**A tag with no layout shows its payload as raw bytes.** Inventing a structure for a record this
project has not decoded would put a guess in a specification, which is the one thing a format
document must never do.

### 3. Generator and currency test

`scripts/hexpat/` renders the pattern from `formats.layouts`, wired to a `make hexpat` target
beside the existing `make spec`. A test regenerates in memory and compares byte for byte with the
committed file, so adding a field to a layout either updates the pattern or fails the build.

That test also closes an existing gap: `docs/formats/finale-formats.{html,pdf}` are generated and
committed today with nothing checking that the committed copies are current.

## What this does not do

- **It does not open a `.mus` directly.** Pointing ImHex at a score on disk still shows only the
  container. The pattern's header comment and the README must say so plainly.
- **It does not decode payloads this project has not decoded.** Coverage is exactly the catalog's.
- **It does not describe the `.musx` format**, which is a ZIP of encrypted, deflated XML and has
  nothing a byte-offset pattern would help with.

## Testing

- The generator's output is pinned byte for byte against the committed pattern.
- Every `Layout` in the catalog appears in the generated pattern, and every field type in use maps
  to a hexpat type — asserted by iterating the catalog, so a new type fails loudly rather than
  silently emitting nothing.
- `extract` is covered like `convert`: single file, batch over a tree, `--force`, and refusal to
  overwrite. Round-trip: the bytes written equal `read_mus_pools`' data for that pool.
- A corpus sweep asserts extraction succeeds across both eras and that each written file's size
  matches the pool it came from. Report counts only — never a corpus filename, title or record
  value.

## Risk stated up front

**CI can prove the pattern is current, complete and type-correct against the catalog. It cannot
prove the pattern loads.** ImHex is not installable in this environment and there is no headless
evaluator for the pattern language here, so syntax errors would survive every test above. The
generated file needs opening in ImHex once by hand before the branch is trusted. This is a known,
accepted limitation of the plan rather than something to discover late.
