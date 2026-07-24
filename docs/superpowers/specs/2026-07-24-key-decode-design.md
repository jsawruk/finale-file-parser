# Key signature decoding — design

**Status:** approved, not yet implemented
**Date:** 2026-07-24

Decode the raw `keySig.key` integer (exposed by the entry-location slice) into a structured
`KeySignature`: fifths, mode, and tonic. Pure reverse-engineering — the encoding is documented
nowhere we have read; it was derived from the corpus.

## The encoding

```
key = (mode << 8) | (fifths & 0xFF)
```

- **low byte, signed** = `fifths`: the accidental count, sharps positive, flats negative — the
  MusicXML convention (`+2` = D major, `−1` = F major).
- **high byte** = `mode`: `0` = major, `1` = minor.

Every one of the 13 distinct raw values across all 401 corpus archives decomposes cleanly:

| Raw | fifths | mode | key |
|---|---|---|---|
| 1, 2, 3 | +1, +2, +3 | major | G, D, A |
| 251–255 | −5…−1 | major | D♭, A♭, E♭, B♭, F |
| 256, 257 | 0, +1 | minor | A minor, E minor |
| 507, 510, 511 | −5, −2, −1 | minor | B♭, G, D minor |

### How the encoding was established (corroboration)

The encoding is inferred, so the evidence matters:

- **Clean bit decomposition.** All 13 values yield `mode ∈ {0, 1}` and `fifths ∈ [−7, 7]` with no
  remainder.
- **`keySig` has no other field.** Only `key` — so mode has nowhere to live except inside that
  integer, which is exactly the high byte.
- **Matches MusicXML.** `fifths` + `mode` is the universal interchange representation, and Finale
  exports MusicXML, so its internal key almost certainly maps to it.
- **Tonic derivation checks out.** Deriving the tonic from (fifths, mode) via the circle of fifths
  reproduces standard music theory for every corpus value (`−3` major → E♭; raw 256 → A minor).

### What is inferred vs proven

- **`mode = 1` → minor is inferred, not proven.** No corpus file's key is independently known. The
  inference rests on the bit pattern, minor being the common second mode, and the high-byte-1 values
  being ordinary minor keys (A, E, D, G, B♭ minor). High confidence, circumstantial.
- **`fifths` beyond −5…+3 and any mode ≥ 2 are not corpus-exercised.** The ±6/±7 enharmonic keys are
  modelled (the signed byte covers them) but unseen. Finale's church modes (Dorian, etc.) and
  custom/linear key signatures would use `mode ≥ 2` or a different scheme entirely — none occur, so
  they are **not** decoded (see Errors).

## Public interface

A new pure module `src/finale_file_parser/enigma/key.py`.

```python
def decode_key(raw: int) -> KeySignature: ...

class Mode(Enum):
    MAJOR = 0
    MINOR = 1

@dataclass(frozen=True)
class KeySignature:
    fifths: int          # signed accidental count, −7..+7
    mode: Mode
    tonic: str           # tonic note name: "C", "F#", "Bb"; "A" for A minor
```

- `fifths` = signed low byte; `mode` = `Mode(high byte)`.
- `tonic` derived via the circle of fifths: major `0`→C `+1`→G `+2`→D … `−1`→F `−2`→B♭ …; minor uses
  the relative-minor tonic (`0`→A `+1`→E `−1`→D …). This is the note `harm_lev = 0` maps to — the
  anchor the pitch-spelling slice needs.

`decode_key` is a **pure `int → KeySignature` transform** — no document, no I/O. A caller composes
`decode_key(location[entnum].key_signature)`.

## Errors

- **`UnsupportedKeyError`** (new, subclasses `FinaleFileError`) — a raw value outside the proven
  standard model: `mode ≥ 2` (a church mode or custom/linear key we have not reverse-engineered) or
  `fifths` outside `−7…+7`. Raising is deliberate: we cannot decode what we have not established, and
  a wrong guess would silently misspell every pitch downstream. The corpus has 0 such values, so it
  fires only on genuinely non-standard input.

## Transposing instruments — not this slice

A transposing staff's `keySig` holds its **written** key; reconciling written vs concert pitch is a
per-staff concern for a later slice. `decode_key` faithfully returns the written key it is given.

## Testing

- Unit tests over the transform: each of the 13 corpus raw values → its known (fifths, mode, tonic);
  the sign convention (`+2` = D major, `255` = F major, `253` = E♭ major); a minor value (`256` = A
  minor, `511` = D minor); the enharmonic boundary (`+6` → F♯ major and the byte for `−6` → G♭ major,
  distinct); `+7`/`−7` (C♯/C♭ major); `mode ≥ 2` and `fifths` out of range each raise
  `UnsupportedKeyError`; `KeySignature` is frozen.
- Corpus sweep (local only, skipped in CI): **every distinct `keySig.key` in all 401 archives
  decodes without raising**, and the set of decoded (fifths, mode) pairs matches the surveyed set.
  Report counts only — never a record value beyond the key integers themselves (which are structural,
  not content).
- Every rule verified by mutation (dropping the signed-byte conversion must fail the flats tests;
  dropping the mode split must fail a minor test).

## Out of scope

Pitch spelling (key + `harmLev`/`harmAlt` → letter — the next slice, which consumes this). Church
modes and custom/linear key signatures (unseen; would need their own reverse-engineering).
Transposing reconciliation. Clefs, time signatures.

## Consequences

- New `enigma/key.py`; `decode_key`, `KeySignature`, `Mode`, `UnsupportedKeyError` exported from
  `finale_file_parser.enigma` and the package root.
- `docs/ARCHITECTURE.md` gains the key encoding (`(mode << 8) | signed fifths`), its corroboration,
  and the inferred-vs-proven note.
- Roadmap next: **pitch spelling** — `decode_key` + `read_entry`'s `harm_lev`/`harm_alt` +
  `locate_entries` → an absolute spelled pitch. Then clefs, time signatures, tuplets, the detail
  records, toward a MusicXML exporter.
