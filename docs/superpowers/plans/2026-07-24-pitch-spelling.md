# Pitch Spelling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spell a `Note` (`harmLev`/`harmAlt`) plus the key in force into an absolute written and concert (sounding) pitch, decoding transposing-instrument staves.

**Architecture:** A new pure module `enigma/pitch.py` with four transforms — `spell_pitch` (note + key → pitch), `transpose_key` (concert key → written key), `transpose_pitch` (written pitch → concert pitch), and `spell_note` (compose all three) — plus `read_transposition`, which pulls the `interval`/`adjust` transposition off a `staffSpec` `Record`. All spelling logic is pure; only `read_transposition` touches a record. A small refactor first exposes the tonic lookup already in `enigma/key.py` so `transpose_key` can reuse it.

**Tech Stack:** Python ≥3.12, uv, ruff, mypy --strict, pytest. Only runtime dependency is `defusedxml` (unchanged — this slice adds no dependency).

## Global Constraints

- **Toolchain:** run everything through `make` — `make check` is the pre-push gate (ruff lint + ruff format-check + `mypy --strict` + pytest over `src tests scripts`). Never run tools ad-hoc.
- **Line length 100**; ruff rules E/F/I/UP/B; code fully type-annotated (`mypy --strict`).
- **Commits:** Conventional Commits (`feat:`, `refactor:`, `docs:`, `test:`). Subject describes the behavioural change.
- **Untrusted input:** malformed input must raise a clear error, never crash or hang. Every value read from a file is hostile until parsed.
- **Corpus is copyrighted, gitignored, absent in CI.** The corpus sweep test must skip when `corpus/` is absent and must report **counts only** — never a filename, pitch name, lyric, title, or any record value beyond structural integers.
- **Format knowledge is documented, not implicit:** the transposition encoding goes in `docs/ARCHITECTURE.md` with its evidence.
- **Purity:** spelling functions are pure `(value) → value`; do I/O / record access only in `read_transposition`.

---

### Task 1: Expose `tonic_for` in `enigma/key.py`

Pure refactor: `transpose_key` (Task 3) needs the (fifths, mode) → tonic lookup that `decode_key` performs inline against `_MAJOR_TONIC`/`_MINOR_TONIC`. Extract it to a reusable module function; `decode_key`'s behaviour is unchanged.

**Files:**
- Modify: `src/finale_file_parser/enigma/key.py`
- Test: `tests/enigma/test_key.py`

**Interfaces:**
- Consumes: `_MAJOR_TONIC`, `_MINOR_TONIC`, `Mode` (existing in `key.py`).
- Produces: `def tonic_for(fifths: int, mode: Mode) -> str` — the tonic note name for a standard `(fifths, mode)` key. Not added to `__all__` (internal helper, imported by `pitch.py`).

- [ ] **Step 1: Write the failing test**

Add to `tests/enigma/test_key.py`:

```python
from finale_file_parser.enigma.key import tonic_for


def test_tonic_for_major_and_minor() -> None:
    assert tonic_for(0, Mode.MAJOR) == "C"
    assert tonic_for(2, Mode.MAJOR) == "D"
    assert tonic_for(-2, Mode.MAJOR) == "Bb"
    assert tonic_for(0, Mode.MINOR) == "A"
    assert tonic_for(-1, Mode.MINOR) == "D"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enigma/test_key.py::test_tonic_for_major_and_minor -v`
Expected: FAIL with `ImportError` / `cannot import name 'tonic_for'`.

- [ ] **Step 3: Add `tonic_for` and use it in `decode_key`**

In `src/finale_file_parser/enigma/key.py`, add after the tonic tables:

```python
def tonic_for(fifths: int, mode: Mode) -> str:
    """The tonic note name for a standard (fifths, mode) key, via the circle of fifths."""
    return (_MAJOR_TONIC if mode is Mode.MAJOR else _MINOR_TONIC)[fifths]
```

Then replace the inline lookup in `decode_key`:

```python
    mode = Mode(mode_value)
    tonic = tonic_for(fifths, mode)
    return KeySignature(fifths=fifths, mode=mode, tonic=tonic)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/enigma/test_key.py -v`
Expected: PASS (new test plus all existing `decode_key` tests — behaviour unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/enigma/key.py tests/enigma/test_key.py
git commit -m "refactor: extract tonic_for helper in enigma.key"
```

---

### Task 2: `SpelledPitch` and `spell_pitch`

The pure spelling core: a note relative to a key → absolute letter, alteration, octave.

**Files:**
- Create: `src/finale_file_parser/enigma/pitch.py`
- Test: `tests/enigma/test_pitch.py`

**Interfaces:**
- Consumes: `Note` (from `enigma.music`), `KeySignature` (from `enigma.key`).
- Produces:
  - `SpelledPitch(letter: str, alteration: int, octave: int)` frozen dataclass with `name: str` property.
  - `def spell_pitch(note: Note, key: KeySignature) -> SpelledPitch`.
  - Module privates later tasks reuse: `_LETTERS`, `_key_accidental`, `_midi`, `_natural_midi`, `_OCTAVE`.

- [ ] **Step 1: Write the failing test**

Create `tests/enigma/test_pitch.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from finale_file_parser.enigma.key import KeySignature, Mode
from finale_file_parser.enigma.music import Note
from finale_file_parser.enigma.pitch import SpelledPitch, spell_pitch


def _note(harm_lev: int, harm_alt: int = 0) -> Note:
    return Note(harm_lev=harm_lev, harm_alt=harm_alt, tie_start=False, tie_end=False)


def _key(fifths: int, mode: Mode, tonic: str) -> KeySignature:
    return KeySignature(fifths=fifths, mode=mode, tonic=tonic)


C_MAJOR = _key(0, Mode.MAJOR, "C")
D_MAJOR = _key(2, Mode.MAJOR, "D")
BB_MAJOR = _key(-2, Mode.MAJOR, "Bb")
A_MINOR = _key(0, Mode.MINOR, "A")


def test_c_major_scale_up() -> None:
    got = [spell_pitch(_note(h), C_MAJOR).name for h in range(8)]
    assert got == ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]


def test_c_major_scale_down_octave_boundary_at_c() -> None:
    got = [spell_pitch(_note(h), C_MAJOR).name for h in range(-1, -8, -1)]
    assert got == ["B3", "A3", "G3", "F3", "E3", "D3", "C3"]


def test_d_major_applies_key_sharps() -> None:
    got = [spell_pitch(_note(h), D_MAJOR).name for h in range(8)]
    assert got == ["D4", "E4", "F#4", "G4", "A4", "B4", "C#5", "D5"]


def test_bb_major_applies_key_flats() -> None:
    got = [spell_pitch(_note(h), BB_MAJOR).name for h in range(8)]
    assert got == ["Bb4", "C5", "D5", "Eb5", "F5", "G5", "A5", "Bb5"]


def test_a_minor_relative_scale() -> None:
    got = [spell_pitch(_note(h), A_MINOR).name for h in range(8)]
    assert got == ["A4", "B4", "C5", "D5", "E5", "F5", "G5", "A5"]


def test_harm_alt_lowers_and_raises_against_key() -> None:
    assert spell_pitch(_note(2, harm_alt=-1), D_MAJOR).name == "F4"  # F# -> F natural
    assert spell_pitch(_note(0, harm_alt=1), C_MAJOR).name == "C#4"  # C -> C#


def test_double_accidental_names() -> None:
    assert SpelledPitch("F", 2, 4).name == "F##4"
    assert SpelledPitch("B", -2, 3).name == "Bbb3"
    assert SpelledPitch("G", 0, 4).name == "G4"


def test_spelled_pitch_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        SpelledPitch("C", 0, 4).letter = "D"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enigma/test_pitch.py -v`
Expected: FAIL — `ModuleNotFoundError: finale_file_parser.enigma.pitch`.

- [ ] **Step 3: Create `pitch.py` with `SpelledPitch` and `spell_pitch`**

Create `src/finale_file_parser/enigma/pitch.py`:

```python
"""Spell a Note (harmLev/harmAlt) plus the key in force into an absolute pitch.

Combines decode_key (tonic + key accidentals), read_entry (harmLev/harmAlt), and
the staff's transposition into written and concert (sounding) spelled pitches. The
transposition encoding is reverse-engineered from the corpus; see
docs/superpowers/specs/2026-07-24-pitch-spelling-design.md for the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.key import KeySignature
from finale_file_parser.enigma.music import Note

_LETTERS = "CDEFGAB"  # C-indexed, so the octave boundary falls at C (scientific pitch)
_SHARP_ORDER = "FCGDAEB"
_FLAT_ORDER = "BEADGCF"
_LETTER_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_OCTAVE = 7  # diatonic steps per octave
_MIDDLE_C_OCTAVE = 4  # harm_lev = 0 tonic sits in octave 4 (middle C region)


def _key_accidental(letter: str, fifths: int) -> int:
    """The alteration a key signature applies to a bare letter: +1 sharp, -1 flat, 0 natural."""
    if fifths > 0 and letter in _SHARP_ORDER[:fifths]:
        return 1
    if fifths < 0 and letter in _FLAT_ORDER[:-fifths]:
        return -1
    return 0


@dataclass(frozen=True)
class SpelledPitch:
    """An absolute spelled pitch: letter, alteration, and octave."""

    letter: str
    """The note letter, "C".."B"."""

    alteration: int
    """Semitones vs the natural letter: sharps positive, flats negative."""

    octave: int
    """Scientific-pitch octave; middle C is C4."""

    @property
    def name(self) -> str:
        """The pitch name, e.g. "C#5", "Bb3", "F4", "F##4"."""
        if self.alteration > 0:
            accidental = "#" * self.alteration
        elif self.alteration < 0:
            accidental = "b" * -self.alteration
        else:
            accidental = ""
        return f"{self.letter}{accidental}{self.octave}"


def _midi(pitch: SpelledPitch) -> int:
    """Semitone number of a spelled pitch; C4 = 60."""
    return (pitch.octave + 1) * 12 + _LETTER_SEMITONE[pitch.letter] + pitch.alteration


def _natural_midi(letter: str, octave: int) -> int:
    """Semitone number of a bare (natural) letter at an octave; C4 = 60."""
    return (octave + 1) * 12 + _LETTER_SEMITONE[letter]


def spell_pitch(note: Note, key: KeySignature) -> SpelledPitch:
    """Spell a note relative to a key into an absolute pitch.

    Given the written key this yields the written pitch; given the concert key it
    yields the concert letter and accidental.
    """
    pos = _LETTERS.index(key.tonic[0]) + note.harm_lev
    letter = _LETTERS[pos % _OCTAVE]
    octave = _MIDDLE_C_OCTAVE + pos // _OCTAVE
    alteration = _key_accidental(letter, key.fifths) + note.harm_alt
    return SpelledPitch(letter=letter, alteration=alteration, octave=octave)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/enigma/test_pitch.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/enigma/pitch.py tests/enigma/test_pitch.py
git commit -m "feat: spell a note relative to a key into an absolute pitch"
```

---

### Task 3: `transpose_key` — the written key from a concert key

**Files:**
- Modify: `src/finale_file_parser/enigma/pitch.py`
- Test: `tests/enigma/test_pitch.py`

**Interfaces:**
- Consumes: `KeySignature`, `Mode`, `UnsupportedKeyError`, `tonic_for` (from `enigma.key`).
- Produces: `def transpose_key(key: KeySignature, interval: int, adjust: int) -> KeySignature`. `interval` is accepted for interface symmetry with `transpose_pitch`; the key is fixed by `adjust` (fifths) with `mode` preserved. Raises `UnsupportedKeyError` if the written `fifths` leaves −7..+7.

- [ ] **Step 1: Write the failing test**

Add to `tests/enigma/test_pitch.py`:

```python
from finale_file_parser.enigma.key import UnsupportedKeyError
from finale_file_parser.enigma.pitch import transpose_key


def test_transpose_key_bb_instrument_c_to_d() -> None:
    written = transpose_key(C_MAJOR, interval=1, adjust=2)
    assert (written.fifths, written.mode, written.tonic) == (2, Mode.MAJOR, "D")


def test_transpose_key_f_horn_c_to_g() -> None:
    written = transpose_key(C_MAJOR, interval=4, adjust=1)
    assert (written.fifths, written.tonic) == (1, "G")


def test_transpose_key_eb_alto_c_to_a() -> None:
    written = transpose_key(C_MAJOR, interval=5, adjust=3)
    assert (written.fifths, written.tonic) == (3, "A")


def test_transpose_key_preserves_minor_mode() -> None:
    written = transpose_key(A_MINOR, interval=1, adjust=2)
    assert (written.fifths, written.mode, written.tonic) == (2, Mode.MINOR, "B")


def test_transpose_key_identity_for_concert() -> None:
    written = transpose_key(D_MAJOR, interval=0, adjust=0)
    assert (written.fifths, written.mode, written.tonic) == (2, Mode.MAJOR, "D")


def test_transpose_key_out_of_range_raises() -> None:
    with pytest.raises(UnsupportedKeyError):
        transpose_key(_key(6, Mode.MAJOR, "F#"), interval=1, adjust=2)  # 6 + 2 = 8 fifths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enigma/test_pitch.py -k transpose_key -v`
Expected: FAIL — `cannot import name 'transpose_key'`.

- [ ] **Step 3: Add `transpose_key`**

In `src/finale_file_parser/enigma/pitch.py`, extend the `key` import and add the constant and function:

```python
from finale_file_parser.enigma.key import (
    KeySignature,
    UnsupportedKeyError,
    tonic_for,
)
```

Add near the other constants:

```python
_MAX_FIFTHS = 7
```

Add after `spell_pitch`:

```python
def transpose_key(key: KeySignature, interval: int, adjust: int) -> KeySignature:
    """The written key a transposing staff reads, from its concert key.

    `adjust` shifts the key signature on the circle of fifths; `mode` is preserved.
    `interval` (diatonic steps written sits above concert) is accepted for symmetry
    with transpose_pitch and does not affect the key. Raises UnsupportedKeyError if
    the written key leaves -7..+7 fifths.
    """
    fifths = key.fifths + adjust
    if not (-_MAX_FIFTHS <= fifths <= _MAX_FIFTHS):
        raise UnsupportedKeyError(
            f"transposed key out of range: {key.fifths} + {adjust} = {fifths} fifths"
        )
    return KeySignature(fifths=fifths, mode=key.mode, tonic=tonic_for(fifths, key.mode))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/enigma/test_pitch.py -v`
Expected: PASS (all tests including the 6 new ones).

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/enigma/pitch.py tests/enigma/test_pitch.py
git commit -m "feat: transpose a concert key to a transposing staff's written key"
```

---

### Task 4: `transpose_pitch` — written pitch to concert (sounding) pitch

**Files:**
- Modify: `src/finale_file_parser/enigma/pitch.py`
- Test: `tests/enigma/test_pitch.py`

**Interfaces:**
- Consumes: `SpelledPitch`, `_LETTERS`, `_OCTAVE`, `_midi`, `_natural_midi` (this module).
- Produces: `def transpose_pitch(pitch: SpelledPitch, interval: int, adjust: int) -> SpelledPitch` — the concert pitch, `interval` diatonic steps and `T = ((7*adjust) % 12) + 12 * (interval // 7)` semitones below `pitch`. Identity for `interval=0, adjust=0`.

- [ ] **Step 1: Write the failing test**

Add to `tests/enigma/test_pitch.py`:

```python
from finale_file_parser.enigma.pitch import transpose_pitch


def test_transpose_pitch_bb_down_major_second() -> None:
    # B-flat instrument (interval 1, adjust 2): written C5 sounds Bb4.
    assert transpose_pitch(SpelledPitch("C", 0, 5), interval=1, adjust=2).name == "Bb4"


def test_transpose_pitch_octave_down() -> None:
    # interval 7, adjust 0 => T = 12: written C4 sounds C3, same letter.
    assert transpose_pitch(SpelledPitch("C", 0, 4), interval=7, adjust=0).name == "C3"


def test_transpose_pitch_octave_up() -> None:
    # interval -7 => T = -12: written C4 sounds C5.
    assert transpose_pitch(SpelledPitch("C", 0, 4), interval=-7, adjust=0).name == "C5"


def test_transpose_pitch_octave_borrow_on_letter_wrap() -> None:
    # written C4 down a major second sounds Bb3 (octave borrow across the C boundary).
    assert transpose_pitch(SpelledPitch("C", 0, 4), interval=1, adjust=2).name == "Bb3"


def test_transpose_pitch_identity_for_concert() -> None:
    assert transpose_pitch(SpelledPitch("F", 1, 4), interval=0, adjust=0).name == "F#4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enigma/test_pitch.py -k transpose_pitch -v`
Expected: FAIL — `cannot import name 'transpose_pitch'`.

- [ ] **Step 3: Add `transpose_pitch`**

In `src/finale_file_parser/enigma/pitch.py`, add after `transpose_key`:

```python
def transpose_pitch(pitch: SpelledPitch, interval: int, adjust: int) -> SpelledPitch:
    """Transpose a written pitch down to its concert (sounding) pitch.

    The concert pitch is `interval` diatonic steps and T semitones below the written
    pitch, where T = ((7 * adjust) % 12) + 12 * (interval // _OCTAVE). For a concert
    staff (interval 0, adjust 0) this is the identity.
    """
    semitones = (7 * adjust) % 12 + 12 * (interval // _OCTAVE)
    dpos = pitch.octave * _OCTAVE + _LETTERS.index(pitch.letter) - interval
    letter = _LETTERS[dpos % _OCTAVE]
    octave = dpos // _OCTAVE
    alteration = _midi(pitch) - semitones - _natural_midi(letter, octave)
    return SpelledPitch(letter=letter, alteration=alteration, octave=octave)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/enigma/test_pitch.py -v`
Expected: PASS (all tests including the 5 new ones).

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/enigma/pitch.py tests/enigma/test_pitch.py
git commit -m "feat: transpose a written pitch to its concert sounding pitch"
```

---

### Task 5: `StaffTransposition`, `read_transposition`, `SpelledNote`, `spell_note`

Tie the transforms together and read the transposition off a `staffSpec` record.

**Files:**
- Modify: `src/finale_file_parser/enigma/pitch.py`
- Test: `tests/enigma/test_pitch.py`

**Interfaces:**
- Consumes: `Record` (from `enigma.document`), `Note`, `KeySignature`, and this module's `spell_pitch`, `transpose_key`, `transpose_pitch`.
- Produces:
  - `StaffTransposition(interval: int, adjust: int)` frozen, with `is_concert: bool` property.
  - `def read_transposition(staff_spec: Record) -> StaffTransposition` — reads `transposition.keysig.interval`/`adjust`, defaulting to `(0, 0)` when absent.
  - `SpelledNote(written: SpelledPitch, concert: SpelledPitch)` frozen.
  - `def spell_note(note: Note, concert_key: KeySignature, transposition: StaffTransposition) -> SpelledNote`.

- [ ] **Step 1: Write the failing test**

Add to `tests/enigma/test_pitch.py`:

```python
from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.pitch import (
    SpelledNote,
    StaffTransposition,
    read_transposition,
    spell_note,
)


def _staff_spec(transposition: Record | None) -> Record:
    fields: dict[str, object] = {}
    if transposition is not None:
        fields["transposition"] = transposition
    return Record(tag="staffSpec", attrs={}, text=None, fields=fields)


def _transposition(interval: str, adjust: str) -> Record:
    keysig = Record(
        tag="keysig",
        attrs={},
        text=None,
        fields={"interval": interval, "adjust": adjust},
    )
    return Record(tag="transposition", attrs={}, text=None, fields={"keysig": keysig})


def test_read_transposition_reads_interval_and_adjust() -> None:
    got = read_transposition(_staff_spec(_transposition("1", "2")))
    assert got == StaffTransposition(interval=1, adjust=2)


def test_read_transposition_zero_is_concert() -> None:
    got = read_transposition(_staff_spec(_transposition("0", "0")))
    assert got == StaffTransposition(0, 0)
    assert got.is_concert is True


def test_read_transposition_absent_defaults_to_concert() -> None:
    assert read_transposition(_staff_spec(None)) == StaffTransposition(0, 0)


def test_is_concert_false_when_transposing() -> None:
    assert StaffTransposition(1, 2).is_concert is False


def test_spell_note_concert_staff_written_equals_concert() -> None:
    result = spell_note(_note(6), D_MAJOR, StaffTransposition(0, 0))
    assert result == SpelledNote(written=SpelledPitch("C", 1, 5), concert=SpelledPitch("C", 1, 5))
    assert result.written.name == "C#5"


def test_spell_note_bb_staff_written_and_concert() -> None:
    # B-flat staff, concert C major. harm_lev 0 = written tonic D; sounds C.
    result = spell_note(_note(0), C_MAJOR, StaffTransposition(interval=1, adjust=2))
    assert result.written.name == "D4"
    assert result.concert.name == "C4"


def test_spelled_note_and_staff_transposition_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        StaffTransposition(0, 0).interval = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        spell_note(_note(0), C_MAJOR, StaffTransposition(0, 0)).written = SpelledPitch("C", 0, 4)  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enigma/test_pitch.py -k "transposition or spell_note or is_concert" -v`
Expected: FAIL — `cannot import name 'StaffTransposition'`.

- [ ] **Step 3: Add the integration layer**

In `src/finale_file_parser/enigma/pitch.py`, add `Record` to imports:

```python
from finale_file_parser.enigma.document import Record
```

Add at the end of the module:

```python
@dataclass(frozen=True)
class StaffTransposition:
    """A staff's transposition: how its written pitch sits above concert."""

    interval: int
    """Diatonic steps the written pitch sits above concert."""

    adjust: int
    """The written key signature's shift, in fifths."""

    @property
    def is_concert(self) -> bool:
        """True when the staff is concert pitch (no transposition)."""
        return self.interval == 0 and self.adjust == 0


def read_transposition(staff_spec: Record) -> StaffTransposition:
    """Read a staffSpec's transposition, defaulting to concert pitch when absent.

    Raises ValueError if a present interval/adjust field is not an integer (malformed
    input fails loudly rather than silently spelling the wrong pitch).
    """
    transposition = staff_spec.fields.get("transposition")
    if not isinstance(transposition, Record):
        return StaffTransposition(interval=0, adjust=0)
    keysig = transposition.fields.get("keysig")
    if not isinstance(keysig, Record):
        return StaffTransposition(interval=0, adjust=0)
    interval = keysig.fields.get("interval")
    adjust = keysig.fields.get("adjust")
    return StaffTransposition(
        interval=int(interval) if isinstance(interval, str) and interval else 0,
        adjust=int(adjust) if isinstance(adjust, str) and adjust else 0,
    )


@dataclass(frozen=True)
class SpelledNote:
    """A note spelled as both its written and its concert (sounding) pitch."""

    written: SpelledPitch
    """The pitch as printed on the (possibly transposing) staff."""

    concert: SpelledPitch
    """The sounding pitch."""


def spell_note(
    note: Note, concert_key: KeySignature, transposition: StaffTransposition
) -> SpelledNote:
    """Spell a note into both its written and concert (sounding) pitch."""
    written_key = transpose_key(concert_key, transposition.interval, transposition.adjust)
    written = spell_pitch(note, written_key)
    concert = transpose_pitch(written, transposition.interval, transposition.adjust)
    return SpelledNote(written=written, concert=concert)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/enigma/test_pitch.py -v`
Expected: PASS (all tests). Then confirm the full unit suite: `uv run pytest tests/ -q`.

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/enigma/pitch.py tests/enigma/test_pitch.py
git commit -m "feat: spell a note into written and concert pitch via staff transposition"
```

---

### Task 6: Exports and format documentation

Export the new public names and document the transposition encoding.

**Files:**
- Modify: `src/finale_file_parser/enigma/__init__.py`
- Modify: `src/finale_file_parser/__init__.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ROADMAP.md`
- Test: `tests/test_package_exports.py` (create if absent; otherwise extend the existing package-export test — check first with `ls tests/`)

**Interfaces:**
- Consumes: the eight public names from `enigma.pitch`.
- Produces: `SpelledPitch`, `SpelledNote`, `StaffTransposition`, `spell_pitch`, `transpose_key`, `transpose_pitch`, `spell_note`, `read_transposition` importable from `finale_file_parser` and `finale_file_parser.enigma`.

- [ ] **Step 1: Write the failing test**

Check for an existing export test first: `ls tests/ | grep -i export`. If one exists, add the assertion there; otherwise create `tests/test_package_exports.py`:

```python
import finale_file_parser
from finale_file_parser import enigma


def test_pitch_names_exported_from_package_root() -> None:
    for name in (
        "SpelledPitch",
        "SpelledNote",
        "StaffTransposition",
        "spell_pitch",
        "transpose_key",
        "transpose_pitch",
        "spell_note",
        "read_transposition",
    ):
        assert hasattr(finale_file_parser, name), name
        assert hasattr(enigma, name), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package_exports.py -v`
Expected: FAIL — `AssertionError: SpelledPitch`.

- [ ] **Step 3: Add the exports**

In `src/finale_file_parser/enigma/__init__.py`, add the import block (alphabetical among the enigma imports) and the `__all__` entries:

```python
from finale_file_parser.enigma.pitch import (
    SpelledNote,
    SpelledPitch,
    StaffTransposition,
    read_transposition,
    spell_note,
    spell_pitch,
    transpose_key,
    transpose_pitch,
)
```

Add these eight names to that module's `__all__`.

In `src/finale_file_parser/__init__.py`, add the same eight names to the `from finale_file_parser.enigma import (...)` block and to the root `__all__` (keep the existing alphabetical/grouped ordering).

- [ ] **Step 4: Document the encoding**

In `docs/ARCHITECTURE.md`, under the "Known format facts" material, add a "Pitch spelling and transposition" subsection covering:
- `harm_lev` = diatonic scale degree from the tonic (octaves included, `harm_lev = 0` = tonic nearest middle C); `harm_alt` = chromatic alteration relative to the key.
- Spelling: tonic letter + `harm_lev` → letter/octave (octave boundary at C); key accidental (order `F C G D A E B`) + `harm_alt` → alteration.
- Transposition: a `staffSpec.transposition.keysig` holds `interval` (diatonic steps the written pitch sits above concert; `7` = octave) and `adjust` (written key-signature shift, in fifths). Written key = concert key with `fifths += adjust`. Concert pitch = written pitch dropped `interval` diatonic steps and `T = ((7·adjust) mod 12) + 12·(interval÷7)` semitones.
- The corroboration table (the six corpus signatures → B♭/F/E♭ instruments and the octave family), the "each added sharp is a perfect fifth" law, and the written-storage argument (`measSpec` carries one concert key per measure; the transposition transposes the key signature). Mark the instrument decode and written-storage as **inferred but strongly corroborated** (no independent ground truth), mirroring the `mode = 1 ⇒ minor` note.
- `noKeyOpt` appears only on octave transpositions (where `adjust = 0` already leaves the key unchanged); `setToClef` is display-only. Neither is consumed.

In `docs/ROADMAP.md`, check off the **Pitch spelling** item under "Next up" and note that `SpelledNote` gives written + concert pitch; leave the following item (tuplet scaling / clefs / time signatures) as the next target.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_package_exports.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finale_file_parser/__init__.py src/finale_file_parser/enigma/__init__.py tests/ docs/ARCHITECTURE.md docs/ROADMAP.md
git commit -m "feat: export pitch spelling API and document the transposition encoding"
```

---

### Task 7: Corpus sweep — every note spells, scale degree preserved

The only check against real archives. Skipped when `corpus/` is absent. Asserts a genuine invariant, not a tautology: for every note, the concert pitch's *printed* accidental (its alteration minus the concert key's accidental for its letter) equals the original `harm_alt` — which holds iff `transpose_key`/`transpose_pitch` correctly preserve scale degree. Verified 0 violations over 50,024 transposing-staff notes during design.

**Files:**
- Create: `tests/enigma/test_pitch_corpus_sweep.py`

**Interfaces:**
- Consumes: `parse_enigma`, `score_xml`, `locate_entries`, `read_entry`, `spell_note`, `read_transposition`, `decode_key`, and an independent reconstruction of the key-accidental rule (deliberately not importing `pitch._key_accidental`, so the test can catch an error there too).

- [ ] **Step 1: Write the test**

Create `tests/enigma/test_pitch_corpus_sweep.py`:

```python
"""Sweep the full local corpus, spelling every note into written and concert pitch.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted third-party
material and is gitignored; these assertions are the only check against real archives.

The core assertion is a genuine invariant, not the spelling definition: a key
transposition must preserve scale degree, so each concert pitch's printed accidental
(alteration minus the concert key's accidental for its letter) must equal the note's
original harm_alt. This was verified to hold with 0 violations over 50,024
transposing-staff notes during design; any mismatch here is a real defect in
transpose_key/transpose_pitch, not a reason to loosen the assertion.

Report counts only -- never a corpus filename, pitch name, lyric, or text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.key import decode_key
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.pitch import StaffTransposition, read_transposition, spell_note
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401

# Independent reconstruction of the key-accidental rule (NOT imported from pitch, so a
# bug there is caught rather than mirrored).
_SHARP_ORDER = "FCGDAEB"
_FLAT_ORDER = "BEADGCF"


def _printed_accidental(letter: str, alteration: int, fifths: int) -> int:
    if fifths > 0 and letter in _SHARP_ORDER[:fifths]:
        key_acc = 1
    elif fifths < 0 and letter in _FLAT_ORDER[:-fifths]:
        key_acc = -1
    else:
        key_acc = 0
    return alteration - key_acc


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_corpus_note_spells_and_preserves_scale_degree() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    notes_spelled = 0
    for path in paths:
        doc = parse_enigma(score_xml(path))
        location = locate_entries(doc)
        for entry_record in doc.entries.of_tag("entry"):
            entnum = int(entry_record.attrs["entnum"])
            placed = location.get(entnum)
            if placed is None:
                continue
            concert_key = decode_key(placed.key_signature)
            staff_spec = doc.others.get("staffSpec", placed.staff)
            transposition = (
                read_transposition(staff_spec)
                if staff_spec is not None
                else StaffTransposition(0, 0)
            )
            for note in read_entry(entry_record).notes:
                spelled = spell_note(note, concert_key, transposition)
                printed = _printed_accidental(
                    spelled.concert.letter, spelled.concert.alteration, concert_key.fifths
                )
                assert printed == note.harm_alt
                notes_spelled += 1

    assert notes_spelled > 0
```

- [ ] **Step 2: Run the sweep**

Run: `uv run pytest tests/enigma/test_pitch_corpus_sweep.py -v`
Expected: PASS locally (corpus present). Confirm it reports a non-zero note count and does not raise. If `corpus/` is absent it is skipped — that is acceptable but verify locally where the corpus exists.

- [ ] **Step 3: Confirm the corpus is untouched and the full gate is green**

Run: `git status --short corpus/` (expect no output — corpus unchanged/gitignored) and `make check`.
Expected: `make check` passes (lint, format, `mypy --strict`, full pytest).

- [ ] **Step 4: Commit**

```bash
git add tests/enigma/test_pitch_corpus_sweep.py
git commit -m "test: sweep every corpus note through spelling, asserting scale-degree invariance"
```

---

## Self-Review

**Spec coverage:**
- `SpelledPitch` + `spell_pitch` → Task 2. ✓
- `transpose_key` → Task 3. ✓
- `transpose_pitch` → Task 4. ✓
- `StaffTransposition`, `read_transposition`, `SpelledNote`, `spell_note` → Task 5. ✓
- `name` accidental format (naturals, single/double sharps/flats) → Task 2 (`test_double_accidental_names`). ✓
- `UnsupportedKeyError` on out-of-range written key → Task 3 (`test_transpose_key_out_of_range_raises`). ✓
- Exports + `docs/ARCHITECTURE.md` + `docs/ROADMAP.md` → Task 6. ✓
- Corpus sweep with the scale-degree invariant, counts only → Task 7. ✓
- `tonic_for` reuse (spec's "same tables `decode_key` uses") → Task 1. ✓

**Type consistency:** `transpose_key(key, interval, adjust)`, `transpose_pitch(pitch, interval, adjust)`, `spell_note(note, concert_key, transposition)`, `read_transposition(staff_spec) -> StaffTransposition`, `spell_note -> SpelledNote` are used identically across tasks and match the spec's Public interface. `_OCTAVE = 7`, `_LETTERS = "CDEFGAB"`, and the `T` formula are consistent between Tasks 2 and 4.

**Placeholder scan:** No placeholders, TODOs, or "similar to Task N" references — every step carries complete code or a concrete edit list. The `staff_spec is None` branch in Task 7 uses `StaffTransposition(0, 0)` directly.
