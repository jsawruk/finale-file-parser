# Pitch spelling (with transposition) — design

**Status:** approved, not yet implemented
**Date:** 2026-07-24

Turn a `Note` (`harmLev`/`harmAlt`) plus the key in force into an **absolute spelled pitch** —
letter, accidental, and octave — for both the **written** staff (what a player reads) and the
**concert** (sounding) pitch. This is the first slice to combine all three typed layers:
`decode_key` (the tonic and the key's accidental pattern), `read_entry` (`harm_lev`/`harm_alt`), and
`locate_entries` (the key in force and the staff), and the first to handle **transposing
instruments** — present in 28 of 80 surveyed corpus files.

## What `harm_lev`/`harm_alt` encode

`harm_lev` is a **diatonic scale degree**: the signed number of diatonic steps of the note above the
key's tonic, octaves included (`harm_lev = 0` is the tonic nearest middle C; `+7` is one octave up;
`−1` is the leading tone below). `harm_alt` is the note's **chromatic alteration** relative to what
the key signature already dictates for that letter (`0` = follow the key; `−1` = one semitone flatter
than the key spells that letter; e.g. F♮ in D major is `harm_lev = 2`, `harm_alt = −1`).

Spelling is therefore: the tonic letter plus `harm_lev` gives the **letter** and **octave**; the
key's accidental for that letter plus `harm_alt` gives the **alteration**.

## How transposition is stored (reverse-engineered)

A `staffSpec` (others pool, `cmper` = staff) carries a `transposition` sub-record. Its `keysig`
sub-record holds two signed integers, plus two flags:

```
staffSpec.transposition
    noKeyOpt      (flag, present only on octave transpositions)
    setToClef     (flag, display-only)
    keysig
        interval  diatonic steps the WRITTEN pitch sits above concert (0 = unison, 7 = octave)
        adjust    the WRITTEN key signature's shift on the circle of fifths (sharps positive)
```

The encoding was derived from the corpus and corroborated against the standard band/orchestra
transpositions — every distinct non-zero signature is a real instrument:

| `interval` | `adjust` | interval above concert | instrument |
|---|---|---|---|
| 1 | 2 | major 2nd (+2 sharps) | B♭ trumpet / clarinet |
| 4 | 1 | perfect 5th (+1 sharp) | F horn |
| 5 | 3 | major 6th (+3 sharps) | E♭ alto sax |
| 8 | 2 | major 9th (+2 sharps) | B♭ tenor sax |
| 12 | 3 | major 13th (+3 sharps) | E♭ baritone sax |
| ±7 | 0 | octave (`noKeyOpt`) | bass / piccolo family |

**Why this reading is trusted:**

- **The octave anchor.** `interval = ±7, adjust = 0` (with `noKeyOpt`) fixes `interval` as
  *diatonic steps* — 7 steps is an octave — and fixes `adjust` as a key-signature shift that is 0 for
  a pure octave.
- **Each added sharp is a perfect fifth.** A key-signature shift of `adjust` fifths moves the tonic
  by `(7 · adjust) mod 12` semitones. Combined with `interval`, every row above reproduces the
  instrument's textbook transposition exactly (B♭ = M2, F = P5, E♭ alto = M6, and so on).
- **Pitches are stored *written*.** The transposition transposes the *key signature*; that mechanism
  is only meaningful if the stored `harm_lev`/`harm_alt` are the written pitch relative to the
  written key. `measSpec` carries a single **concert** key per measure (keyed by measure only, shared
  across staves), so the written key is not stored — it is derived. This is consistent with Finale's
  documented behaviour of storing written pitch.

### What is proven vs inferred

- **The `interval`/`adjust` decode is strongly corroborated** (six distinct signatures, all textbook
  instruments; the octave anchor; the fifths-to-semitones law). No corpus file's instrument is
  *independently* known, so it remains an inference — high confidence, circumstantial, like the
  `mode = 1 ⇒ minor` inference in `decode_key`.
- **Written storage** rests on the structural argument above plus Finale's documented behaviour; for
  octave (`noKeyOpt`) staves it also fixes the octave direction, which no corpus ground truth
  independently confirms.

## Public interface

A new pure module `src/finale_file_parser/enigma/pitch.py`.

```python
@dataclass(frozen=True)
class SpelledPitch:
    letter: str        # "C".."B"
    alteration: int    # semitones vs the natural letter: flat negative, sharp positive
    octave: int        # scientific pitch, middle C = C4

    @property
    def name(self) -> str:   # e.g. "C#5", "Bb3", "F4", "F##4"

def spell_pitch(note: Note, key: KeySignature) -> SpelledPitch: ...

def transpose_key(key: KeySignature, interval: int, adjust: int) -> KeySignature: ...

def transpose_pitch(pitch: SpelledPitch, interval: int, adjust: int) -> SpelledPitch: ...

@dataclass(frozen=True)
class StaffTransposition:
    interval: int      # diatonic steps written sits above concert
    adjust: int        # written key-signature shift, in fifths

    @property
    def is_concert(self) -> bool:   # interval == 0 and adjust == 0

def read_transposition(staff_spec: Record) -> StaffTransposition: ...

@dataclass(frozen=True)
class SpelledNote:
    written: SpelledPitch   # as printed on the (possibly transposing) staff
    concert: SpelledPitch   # the sounding pitch

def spell_note(
    note: Note, concert_key: KeySignature, transposition: StaffTransposition
) -> SpelledNote: ...
```

### The four transforms

- **`spell_pitch(note, key)`** — pure. `pos = LETTERS.index(key.tonic[0]) + note.harm_lev`;
  `letter = LETTERS[pos % 7]`; `octave = 4 + pos // 7`; `alteration = key_accidental(letter,
  key.fifths) + note.harm_alt`, where `key_accidental` is `+1` if the letter is among the first
  `fifths` of the sharp order `F C G D A E B`, `−1` if among the first `−fifths` of the flat order
  `B E A D G C F`, else `0`. `LETTERS = "CDEFGAB"` (C-indexed, so the octave boundary falls at C, as
  scientific pitch requires). Given the **written** key it yields the written pitch; given the
  **concert** key it yields the concert letter/accidental.

- **`transpose_key(key, interval, adjust)`** — the written key from a concert key: `fifths` becomes
  `key.fifths + adjust`; `mode` is unchanged; `tonic` is re-derived from the new `(fifths, mode)` via
  the same circle-of-fifths tables `decode_key` uses. `interval` is accepted for interface symmetry
  and consistency (the shifted tonic letter must match `LETTERS[(idx + interval) % 7]`); the key
  itself is fixed by `adjust` alone. Raises `UnsupportedKeyError` if the resulting `fifths` leaves
  `−7..+7` (no corpus case does; observed written range is `−5..+4`).

- **`transpose_pitch(pitch, interval, adjust)`** — written → concert (sounding) pitch. The concert
  pitch is `interval` diatonic steps and `T` semitones **below** the written pitch, where
  `T = ((7 · adjust) mod 12) + 12 · (interval // 7)`. Concretely: `dpos = pitch.octave * 7 +
  LETTERS.index(pitch.letter) − interval`; `letter = LETTERS[dpos % 7]`; `octave = dpos // 7`;
  `alteration = midi(pitch) − T − natural_midi(letter, octave)`, where `midi` maps a `SpelledPitch`
  to a semitone number (C4 = 60) and `natural_midi` is the same for the bare letter. For a
  non-transposing staff (`interval = 0, adjust = 0`, so `T = 0`) this is the identity.

- **`spell_note(note, concert_key, transposition)`** — the composition:
  `written_key = transpose_key(concert_key, transposition.interval, transposition.adjust)`;
  `written = spell_pitch(note, written_key)`;
  `concert = transpose_pitch(written, transposition.interval, transposition.adjust)`.
  For a concert (non-transposing) staff, `written == concert`.

- **`read_transposition(staff_spec)`** — pulls `interval`/`adjust` out of a `staffSpec` record's
  `transposition.keysig`, returning `StaffTransposition(0, 0)` when the record has no transposition
  (the common case). The `noKeyOpt`/`setToClef` flags are not consumed: `noKeyOpt` appears only on
  octave transpositions, where `adjust = 0` already leaves the key unchanged, and `setToClef` is a
  display concern.

A caller composes the end-to-end spelling from the existing layers:

```python
loc = locate_entries(doc)
location = loc[entnum]
concert_key = decode_key(location.key_signature)
staff_spec = doc.others.get("staffSpec", location.staff)
transposition = read_transposition(staff_spec) if staff_spec else StaffTransposition(0, 0)
for note in read_entry(entry_record).notes:
    spelled = spell_note(note, concert_key, transposition)   # .written, .concert
```

`spell_pitch`, `transpose_key`, `transpose_pitch`, and `spell_note` are all **pure transforms** — no
document, no I/O. Only `read_transposition` touches a `Record`, and only to read two integers.

### The `name` accidental format

`alteration` is rendered as `"#" * alteration` for sharps, `"b" * (−alteration)` for flats, `""` for
a natural — so double sharps are `"##"` and double flats `"bb"`, and any magnitude renders without a
special case. `name` is `f"{letter}{accidental}{octave}"`.

## Errors

- **`UnsupportedKeyError`** (reused from `enigma.key`) — raised by `transpose_key` when the written
  `fifths` leaves `−7..+7`. A key we cannot spell must fail loudly rather than silently misspell, the
  same stance `decode_key` takes.

`spell_pitch` and `transpose_pitch` do not raise: any `(harm_lev, harm_alt)` and any in-range key
spell to *some* pitch. Malformed input (a non-integer `harmLev`) already fails earlier in
`read_entry`, and a non-standard raw key already fails in `decode_key`; this slice adds no new
degradation path.

## Testing

Unit tests over the pure transforms (each rule isolated so a mutation to it fails a test):

- **`spell_pitch`** — the C-major scale `harm_lev 0..7` → `C4 D4 E4 F4 G4 A4 B4 C5` and `−1..−7` →
  `B3 A3 … C3` (octave boundary at C); D major (2 sharps) `0..7` → `D4 E4 F#4 … C#5 D5`; B♭ major
  (2 flats) `0..7` → `Bb4 C5 … Bb5`; A minor `0..7` → `A4 B4 C5 … A5`; `harm_alt` both directions
  (D major `harm_lev = 2, harm_alt = −1` → `F4`; C major `harm_lev = 0, harm_alt = +1` → `C#4`).
- **`transpose_key`** — concert C major + B♭ (`1, 2`) → D major; + F horn (`4, 1`) → G major; +
  E♭ alto (`5, 3`) → A major; a concert minor key transposes with `mode` preserved; `interval = 0,
  adjust = 0` is the identity; a shift past `±7` raises `UnsupportedKeyError`.
- **`transpose_pitch`** — a written B♭-instrument note (interval 1, adjust 2) transposes down a major
  2nd with correct letter and octave (written C5 → concert B♭4); an octave transposition
  (`interval = 7, adjust = 0`, `T = 12`) drops exactly one octave and keeps the letter; a
  `−7` transposition raises one octave; `0, 0` is the identity; a boundary case that crosses the
  octave (written C4, down a step → concert B♭3) gets the octave borrow right.
- **`spell_note`** — a concert staff yields `written == concert`; a B♭ staff in concert C major
  yields written pitch in D major and concert pitch a major 2nd lower, both spelled correctly.
- **`read_transposition`** — a staffSpec with `interval = 1, adjust = 2` → `StaffTransposition(1, 2)`;
  a staffSpec with a zero transposition, and one with no transposition sub-record, both →
  `StaffTransposition(0, 0)`; `is_concert` is true for `(0, 0)` and false otherwise.
- **`SpelledPitch` / `SpelledNote` / `StaffTransposition` are frozen**; `name` renders naturals,
  single and double sharps/flats.

Corpus sweep (local only, skipped in CI): **every note in all 401 archives spells without raising**,
and — the non-vacuous invariant — for every note the concert pitch's *printed* accidental (its
`alteration` minus the concert key's accidental for its letter) **equals the original `harm_alt`**.
This holds because a key transposition must preserve scale degree; it was verified to hold for all
50,024 transposing-staff notes with **0 violations** during design, and catches any error in
`transpose_key`, `transpose_pitch`, or their composition. The sweep reports counts only — never a
record value beyond the structural integers.

Every rule verified by mutation (dropping the `pos // 7` octave term must fail an octave test;
dropping `adjust` in `transpose_key` must fail the D-major test; dropping the `12 · (interval // 7)`
octave term in `T` must fail the octave `transpose_pitch` test and the corpus invariant).

## Out of scope

- **Microtonal / non-12-EDO** key alterations and custom key signatures (already excluded by
  `decode_key`, which raises on non-standard keys before this slice runs).
- **Tuplet duration scaling**, clefs, time signatures, and the remaining detail records — later
  roadmap slices.
- **MusicXML export** — a downstream consumer of `SpelledNote`.
- The `noKeyOpt`/`setToClef` flags beyond noting their meaning; no corpus case needs them.

## Consequences

- New `enigma/pitch.py`; `SpelledPitch`, `SpelledNote`, `StaffTransposition`, `spell_pitch`,
  `transpose_key`, `transpose_pitch`, `spell_note`, and `read_transposition` exported from
  `finale_file_parser.enigma` and the package root.
- `docs/ARCHITECTURE.md` gains the transposition encoding (`interval` = diatonic steps, `adjust` =
  fifths shift; `T = ((7·adjust) mod 12) + 12·(interval//7)`), its corroboration table, the
  written-storage argument, and the inferred-vs-proven note.
- `docs/ROADMAP.md`: pitch spelling checked off; next up is tuplet scaling / clefs / time signatures
  toward the MusicXML exporter.
