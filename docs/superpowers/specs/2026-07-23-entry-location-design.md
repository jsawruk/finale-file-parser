# Entry location (cross-pool link resolution) — design

**Status:** approved, not yet implemented
**Date:** 2026-07-23

Resolve each entry to its place in the score: which staff, which measure, and the raw key signature
in force. This is the **first cross-pool link resolution** — deferred through the last several
slices — and the reusable foundation for pitch spelling, clefs, and time signatures.

## Scope: link resolution only

Pitch spelling turned out to need three separable things:

1. **the link chain + key inheritance** (entry → staff/measure → the raw key in force) — **this slice**;
2. **decoding the key-signature integer** into a tonic/mode/accidentals — the next slice;
3. **the spelling algorithm** (key + `harmLev`/`harmAlt` → a letter name) — after that.

This slice does (1) and stops. It exposes the raw `keySig` integer **undecoded**. The chain it builds
is reused by everything measure- or staff-scoped, so it earns its own bounded slice.

## The link chain

An entry does not name its staff, measure, or key. The path, all confirmed against the corpus:

```
entry (entnum)
  ← reached by walking a frame's entry chain (startEntry, then each entry's `next` attr)
frameSpec (others, cmper = frame number)  — startEntry / endEntry
  ← referenced by
gfhold (details, cmper1 = staff, cmper2 = measure)  — frame1 … frame4
measSpec (others, cmper = measure)  — keySig (a nested record: {key: <int>})
```

- **`gfhold` cmper1 = staff, cmper2 = measure.** Verified: cmper1 has few distinct values matching
  `staffSpec` cmpers (e.g. 1, 2, 3, 32767); cmper2 is contiguous 1..N measures.
- **A `gfhold` holds up to four frames** — Finale's layers/voices — in fields `frame1`…`frame4`. In
  the corpus: `frame1` always, `frame2`/`frame3` on multi-layer measures (299 of 6332 gfholds over
  30 files). **All present frames must be resolved**, or layer-2+ entries would be unlocated.
- **Entries are a linked list.** A frame's entries are `frameSpec.startEntry`, then each entry's
  `next` attribute, until `endEntry`. `prev`/`next`/`entnum` are *attributes* on the entry record,
  not fields.
- **`measSpec` is keyed by measure alone**, so the key is a per-measure property shared by all
  staves; inheritance runs in measure order, not per staff.

**Coverage is exact.** Resolving `frame1`…`frame4` across the corpus placed every entry in exactly
one (staff, measure): 24,159 entries over 30 files, **0 orphans, 0 double-coverage**.

## Key inheritance

Not every measure carries a `keySig` — 449 of 2622 score measures over 40 files omit it, inheriting
the previous measure's key. So the effective key per measure is computed by walking measures in
order, carrying the last seen `keySig.key` forward.

- A measure with no `keySig` uses the prior measure's effective key.
- If the **first** measure has no `keySig`, the effective key defaults to `0` (documented
  assumption; `0` is the fifths-convention value for C major / no accidentals).

## The raw key value — NOT decoded here

The `keySig.key` integer is exposed verbatim. Its decoding is the next slice; its docstring records
what is known so far, so the decode work starts from it:

- Corpus values include `1, 2, 3` and `253, 254, 255, 257`. The pattern reads as a fifths-style
  signed accidental count in a byte: `+n` = n sharps (`+2` = D major), `256 − n` = n flats
  (`255` = −1 = F major, `254` = −2, `253` = −3), with high bits (`257` = `0x101`) likely a
  mode/type flag.
- **Decoding traps to handle in that slice, not here:** enharmonic equivalents are distinct keys
  (F♯ major ≠ G♭ major — the sign matters), a key signature does not fix major vs minor (C minor and
  E♭ major share three flats — mode is separate), and transposing instruments have a written key
  distinct from concert pitch. This slice sidesteps all of it by staying raw.

## Public interface

New pure module `src/finale_file_parser/enigma/location.py`.

```python
@dataclass(frozen=True)
class EntryLocation:
    entnum: int
    staff: int                  # gfhold cmper1
    measure: int                # gfhold cmper2
    key_signature: int          # effective raw measSpec keySig 'key' (inheritance applied; NOT decoded)

def locate_entries(doc: EnigmaDocument) -> dict[int, EntryLocation]: ...
```

`locate_entries` builds the whole index in one pass and is **pure over the parsed document** — it
uses the document's keyed lookup and `of_tag`, no I/O. A caller composes
`locate_entries(parse_enigma(score_xml(path)))`, then `location[entnum]`.

Returning a `dict[int, EntryLocation]` (not a lazy resolver) because the effective-key inheritance
needs a full measure-order pass anyway, and callers iterate entries far more than once.

## Errors

- **`MalformedScoreError`** (new, subclasses `FinaleFileError`) — an entry that no frame places
  (an orphan), a `gfhold` frame pointing at a missing `frameSpec`, or a `keySig.key` that is not an
  integer. The corpus has 0 orphans, so this fires only on genuinely malformed input — consistent
  with the raise-don't-degrade posture of `read_entry`/`score_xml`.
- A cycle or runaway `next` chain is bounded by a guard and raises rather than hanging.

## Testing

- Unit tests over synthetic documents built in-test: two staves × two measures placing entries via
  `gfhold`/`frameSpec`; a multi-frame (layered) gfhold placing layer-2 entries; key inheritance (a
  measure with no `keySig` inheriting the prior); the first-measure default to `0`; the raw key
  exposed verbatim (e.g. `253` stays `253`, not decoded); an orphan entry raising
  `MalformedScoreError`; a frame pointing at a missing `frameSpec` raising; a `next`-chain cycle
  raising rather than hanging.
- Corpus sweep (local only, skipped in CI): **every entry in all 401 archives is located exactly
  once** (0 orphans, 0 double-coverage — the guarantee the resolution rests on); every located
  entry has an integer `key_signature`; staff values are among the `staffSpec` cmpers. Report counts
  only — never a record value.
- Every resolution rule verified by mutation (dropping frame2–4 handling must fail the layered test;
  dropping inheritance must fail the inheritance test).

## Out of scope

Decoding the key integer; pitch spelling; clefs; time signatures; tuplets. This slice is the link
chain and the raw effective key only.

## Consequences

- New `enigma/location.py`; `EntryLocation`, `locate_entries`, `MalformedScoreError` exported from
  `finale_file_parser.enigma` and the package root.
- `docs/ARCHITECTURE.md` gains the link chain (gfhold → frameSpec → entry next-chain; measSpec key
  per measure with inheritance) and the raw-key note with the decode hints.
- Roadmap next: **decode the key signature** (raw int → tonic/mode/accidentals, per the recorded
  hints), then **pitch spelling** (key + `harmLev`/`harmAlt` → spelled pitch). Then clefs, time
  signatures, tuplets, the detail records, toward a MusicXML exporter.
