# Typed Entry/Note Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `read_entry(record: Record) -> Entry` — turn a generic `entry`/`note` Record into typed music (duration, rest-or-not, pitch encoding).

**Architecture:** A pure `enigma/music.py` transforming one parsed `entry` Record into an `Entry` value. `Duration` decodes EDU to a base note-value + dots; `Note` carries the key-relative pitch encoding with key-independent derived structure. No cross-pool links, no key.

**Design spec:** `docs/superpowers/specs/2026-07-23-typed-entries-design.md`. Read it first — and `docs/eeppd.txt`'s "Note Record / TCD" section for the pitch encoding.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`. Stdlib + defusedxml only (this slice adds no imports beyond stdlib `fractions`/`enum`/`dataclasses`).
- **`read_entry` is pure over one `Record`** — no I/O, no calls to `score_xml`/`parse_enigma`/`open_musx`. A caller composes `read_entry(doc.entries.get(entnum))`.
- **EDU: a whole note is 4096.** Duration decodes to a base (largest power-of-two note value that divides `edu` with the remainder forming dots) plus dots. Verified 100% clean across 34,066 corpus entries.
- **Rest ⟺ `numNotes == 0`.** This matched the nested `note` count exactly across all 27,474 corpus entries; use it, not `isNote`.
- **`numNotes` must equal the number of `note` records** — a disagreement is malformed input.
- **Pitch is key-relative and NOT spelled here.** `harm_lev` = diatonic displacement from the key's tonic (0 = tonic at middle C, +7 = one octave); `harm_alt` = alteration relative to the key (0 natural, +1 sharp, −1 flat). `diatonic_step`/`octave_offset` use floor semantics (`harm_lev % 7`, `harm_lev // 7`) — verified correct for negatives (below middle C).
- **Tie flags are Enigma booleans** — present (with empty text) = true: `tie_start = "tieStart" in note_record.fields`.
- **`MalformedEntryError`** (new, subclasses `FinaleFileError`) — non-integer `dura`; `dura` that does not decode to base+dots or exceeds a whole note; `numNotes` disagreeing with the note count; non-integer `harmLev`/`harmAlt`; a record whose tag is not `entry`. Corpus has 0 such cases.
- `corpus/` is gitignored copyrighted material — no corpus bytes in fixtures; every test input constructed in-test; never print a corpus record value.
- Verify by mutation. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

---

### Task 1: The typed model

**Files:**
- Create: `src/finale_file_parser/enigma/music.py`
- Modify: `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/__init__.py`, `tests/test_public_api.py`
- Test: `tests/enigma/test_music.py`

**Interfaces:**
- Consumes: `Record` from `enigma.document`; `FinaleFileError` from `finale_file_parser.errors`.
- Produces: `NoteValue` (enum), `Duration`, `Note`, `Entry` (frozen dataclasses), `read_entry(record) -> Entry`, `MalformedEntryError`. All exported from `finale_file_parser.enigma` and the package root.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/test_music.py`. Build `entry` Records directly (not from XML) via the parser's own `Record`, so the test exercises `read_entry`, not parsing:

```python
from fractions import Fraction

import pytest

from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.music import (
    Duration,
    Entry,
    MalformedEntryError,
    Note,
    NoteValue,
    read_entry,
)


def _note(harm_lev: str, harm_alt: str = "0", **flags: str) -> Record:
    fields: dict[str, object] = {"harmLev": harm_lev, "harmAlt": harm_alt, "isValid": ""}
    fields.update(flags)
    return Record(tag="note", attrs={}, text="", fields=fields)


def _entry(dura: str, notes: tuple[Record, ...] = (), **extra: str) -> Record:
    fields: dict[str, object] = {
        "dura": dura,
        "numNotes": str(len(notes)),
        "isValid": "",
    }
    if notes:
        fields["note"] = notes if len(notes) > 1 else notes[0]
    fields.update(extra)
    return Record(tag="entry", attrs={"entnum": "1"}, text="", fields=fields)


def test_quarter_note_single_pitch() -> None:
    entry = read_entry(_entry("1024", (_note("0"),)))
    assert entry.entnum == 1
    assert entry.is_rest is False
    assert entry.duration.base is NoteValue.QUARTER
    assert entry.duration.dots == 0
    assert entry.duration.edu == 1024
    assert entry.duration.whole_notes == Fraction(1, 4)
    assert len(entry.notes) == 1
    assert entry.notes[0].harm_lev == 0
    assert entry.notes[0].harm_alt == 0


def test_dotted_quarter() -> None:
    d = read_entry(_entry("1536", (_note("1"),))).duration
    assert d.base is NoteValue.QUARTER
    assert d.dots == 1
    assert d.whole_notes == Fraction(3, 8)


def test_double_dotted_half() -> None:
    d = read_entry(_entry("3584", (_note("0"),))).duration   # 2048+1024+512
    assert d.base is NoteValue.HALF
    assert d.dots == 2


def test_rest_has_no_notes() -> None:
    entry = read_entry(_entry("1024"))
    assert entry.is_rest is True
    assert entry.notes == ()


def test_chord_multiple_notes() -> None:
    entry = read_entry(_entry("512", (_note("0"), _note("2"), _note("4"))))
    assert entry.is_rest is False
    assert [n.harm_lev for n in entry.notes] == [0, 2, 4]


def test_note_below_middle_c_octave_and_degree() -> None:
    # harm_lev = -1 is the diatonic step just below the tonic: degree 6, octave -1
    n = read_entry(_entry("1024", (_note("-1"),))).notes[0]
    assert n.diatonic_step == 6
    assert n.octave_offset == -1
    # +7 is one octave up
    up = read_entry(_entry("1024", (_note("7"),))).notes[0]
    assert up.diatonic_step == 0
    assert up.octave_offset == 1


def test_alteration_sign() -> None:
    assert read_entry(_entry("1024", (_note("0", "1"),))).notes[0].harm_alt == 1
    assert read_entry(_entry("1024", (_note("0", "-1"),))).notes[0].harm_alt == -1


def test_tie_flags() -> None:
    n = read_entry(_entry("1024", (_note("0", tieStart="", tieEnd=""),))).notes[0]
    assert n.tie_start is True
    assert n.tie_end is True
    plain = read_entry(_entry("1024", (_note("0"),))).notes[0]
    assert plain.tie_start is False
    assert plain.tie_end is False


def test_whole_note_fraction() -> None:
    assert read_entry(_entry("4096", (_note("0"),))).duration.whole_notes == Fraction(1, 1)


def test_frozen() -> None:
    entry = read_entry(_entry("1024", (_note("0"),)))
    with pytest.raises((AttributeError, TypeError)):
        entry.is_rest = True  # type: ignore[misc]


def test_rejects_non_entry_record() -> None:
    with pytest.raises(MalformedEntryError, match="entry"):
        read_entry(Record(tag="note", attrs={}, text="", fields={}))


def test_rejects_non_integer_dura() -> None:
    with pytest.raises(MalformedEntryError):
        read_entry(_entry("notanumber"))


def test_rejects_undecodable_dura() -> None:
    # 1000 is not a base power-of-two note value plus dots
    with pytest.raises(MalformedEntryError, match="decode"):
        read_entry(_entry("1000", (_note("0"),)))


def test_rejects_numnotes_disagreeing_with_note_count() -> None:
    # One note record, but numNotes claims five.
    bad = Record(
        tag="entry",
        attrs={"entnum": "1"},
        text="",
        fields={"dura": "1024", "numNotes": "5", "isValid": "", "note": _note("0")},
    )
    with pytest.raises(MalformedEntryError, match="numNotes"):
        read_entry(bad)


def test_rejects_non_integer_harmlev() -> None:
    with pytest.raises(MalformedEntryError):
        read_entry(_entry("1024", (_note("x"),)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma/test_music.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.enigma.music'`

- [ ] **Step 3: Write the implementation**

Create `src/finale_file_parser/enigma/music.py`:

```python
"""Typed musical values over generic EnigmaXML entry/note records.

`read_entry` turns one `entry` Record into an `Entry`: its written duration, whether
it is a rest, and its notes. Pitch is the key-relative Enigma encoding (harmLev /
harmAlt) — spelling absolute pitches needs the key and is a separate slice. See
docs/superpowers/specs/2026-07-23-typed-entries-design.md and docs/eeppd.txt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from finale_file_parser.enigma.document import Record
from finale_file_parser.errors import FinaleFileError

_WHOLE_EDU = 4096
_DIATONIC_STEPS = 7


class MalformedEntryError(FinaleFileError):
    """An entry/note record could not be read as typed music."""


class NoteValue(Enum):
    """A base written note value, in EDU (a whole note is 4096)."""

    WHOLE = 4096
    HALF = 2048
    QUARTER = 1024
    EIGHTH = 512
    SIXTEENTH = 256
    THIRTY_SECOND = 128
    SIXTY_FOURTH = 64
    ONE_TWENTY_EIGHTH = 32


@dataclass(frozen=True)
class Duration:
    """A written duration: a base note value plus augmentation dots."""

    edu: int
    base: NoteValue
    dots: int

    @property
    def whole_notes(self) -> Fraction:
        """The duration as a fraction of a whole note (edu / 4096)."""
        return Fraction(self.edu, _WHOLE_EDU)


@dataclass(frozen=True)
class Note:
    """One pitch. Encoding is relative to the key; not spelled here."""

    harm_lev: int
    """Diatonic displacement from the key's tonic (tonic at middle C = 0, +7 = one octave)."""

    harm_alt: int
    """Alteration relative to the key: 0 natural, +1 sharp, -1 flat. Not the shown accidental."""

    tie_start: bool
    tie_end: bool

    @property
    def diatonic_step(self) -> int:
        """Scale degree from the tonic, 0..6 (key-relative; not a letter name)."""
        return self.harm_lev % _DIATONIC_STEPS

    @property
    def octave_offset(self) -> int:
        """Octaves from the middle-C tonic octave (floor division; negative below)."""
        return self.harm_lev // _DIATONIC_STEPS


@dataclass(frozen=True)
class Entry:
    """A musical event: a note, chord, or rest."""

    entnum: int
    duration: Duration
    is_rest: bool
    notes: tuple[Note, ...]


def read_entry(record: Record) -> Entry:
    """Read one `entry` Record as a typed `Entry`.

    Raises:
        MalformedEntryError: the record is not a well-formed entry.
    """
    if record.tag != "entry":
        raise MalformedEntryError(f"expected an <entry> record, got <{record.tag}>")
    entnum = _int(record.attrs.get("entnum"), "entnum")
    duration = _duration(record)
    notes = _notes(record)
    num_notes = _int(_scalar(record, "numNotes"), "numNotes")
    if num_notes != len(notes):
        raise MalformedEntryError(
            f"numNotes={num_notes} disagrees with {len(notes)} note record(s)"
        )
    return Entry(entnum=entnum, duration=duration, is_rest=num_notes == 0, notes=notes)


def _duration(record: Record) -> Duration:
    edu = _int(_scalar(record, "dura"), "dura")
    if edu <= 0 or edu > _WHOLE_EDU:
        raise MalformedEntryError(f"dura {edu} is out of range")
    base_edu = _WHOLE_EDU
    while base_edu > edu:
        base_edu //= 2
    total = base_edu
    add = base_edu
    dots = 0
    while total < edu:
        add //= 2
        if add == 0:
            raise MalformedEntryError(f"dura {edu} does not decode to a note value")
        total += add
        dots += 1
    if total != edu:
        raise MalformedEntryError(f"dura {edu} does not decode to a note value")
    return Duration(edu=edu, base=NoteValue(base_edu), dots=dots)


def _notes(record: Record) -> tuple[Note, ...]:
    raw = record.fields.get("note")
    if raw is None:
        records: tuple[Record, ...] = ()
    elif isinstance(raw, Record):
        records = (raw,)
    elif isinstance(raw, tuple) and all(isinstance(r, Record) for r in raw):
        records = raw
    else:
        raise MalformedEntryError("note field is not record(s)")
    return tuple(_note(r) for r in records)


def _note(record: Record) -> Note:
    return Note(
        harm_lev=_int(_scalar(record, "harmLev"), "harmLev"),
        harm_alt=_int(_scalar(record, "harmAlt"), "harmAlt"),
        tie_start="tieStart" in record.fields,
        tie_end="tieEnd" in record.fields,
    )


def _scalar(record: Record, name: str) -> str:
    value = record.fields.get(name)
    if not isinstance(value, str):
        raise MalformedEntryError(f"<{record.tag}> field {name!r} is missing or not scalar")
    return value


def _int(value: str | None, name: str) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MalformedEntryError(f"{name} is not an integer: {value!r}") from exc
```

Note `NoteValue(base_edu)` raises `ValueError` if `base_edu` is not an enum member (e.g. a base
below the smallest listed). Wrap that too — a base smaller than `ONE_TWENTY_EIGHTH` should raise
`MalformedEntryError`, not a bare `ValueError`. Add a `try/except ValueError` around the
`NoteValue(base_edu)` construction, raising `MalformedEntryError(f"dura {edu} base has no note value")`.

Export `read_entry`, `Entry`, `Note`, `Duration`, `NoteValue`, `MalformedEntryError` from
`enigma/__init__.py` and the package root; add them to `EXPECTED_PUBLIC_NAMES` in
`tests/test_public_api.py`. Satisfy the derived public-API reachability test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: PASS — the new music tests plus everything else unchanged.

- [ ] **Step 5: Mutation-verify**

| Mutation | Test that must fail |
|---|---|
| `is_rest` keyed on `isNote` presence instead of `num_notes == 0` | `test_rest_has_no_notes` (build a rest that has no `isNote`) — if it still passes, add that case |
| Drop the `num_notes != len(notes)` check | `test_rejects_numnotes_disagreeing_with_note_count` |
| `octave_offset` uses `int(harm_lev / 7)` (truncation) instead of `//` | `test_note_below_middle_c_octave_and_degree` |
| Duration accepts any `edu` (skip the base+dots exactness check) | `test_rejects_undecodable_dura` |
| `tie_start` always `False` | `test_tie_flags` |

The truncation-vs-floor mutation is the important one: `int(-1/7)` is `0` but `-1 // 7` is `-1`, so a
note just below the tonic would report the wrong octave. Confirm the test catches it.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests
git commit -m "feat: add typed Entry/Note/Duration model over entry records"
```

---

### Task 2: Corpus sweep

**Files:** Create `tests/enigma/test_music_corpus_sweep.py`. Skips when `corpus/` is absent.

- [ ] **Step 1: Write the test**

Compose `read_entry` over every `entry` in all 401 archives (`parse_enigma(score_xml(path))`, then `for r in doc.entries.of_tag("entry"): read_entry(r)`). Assert:

- **every entry reads without raising** — 401/401 archives, all entries. This is the core: the
  survey said 100% clean, so any `MalformedEntryError` is a real finding.
- the `is_rest ⟺ len(notes) == 0` invariant holds for every entry read.
- every `duration.edu` re-multiplies correctly: `duration.whole_notes == Fraction(edu, 4096)`.
- across the sweep, at least one rest, one single note, and one chord (≥2 notes) are seen — so the
  sweep exercises all three shapes against real data.

Assert the file list is non-empty first. **If an observed value disagrees, report it rather than
adjusting the assertion.** Report counts only — never a corpus record value, pitch, or lyric.

Note the enigma corpus sweeps are slow (~80-120s decode+parse). Keep this focused.

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/enigma/test_music_corpus_sweep.py -v` — expected pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/enigma -v; mv /tmp/corpus-parked corpus`

Expected: this sweep skipped, other enigma tests pass. **Confirm `corpus/` is restored and reports
639 files.**

- [ ] **Step 3: Commit**

```bash
git add tests/enigma/test_music_corpus_sweep.py
git commit -m "test: read every corpus entry through the typed model"
```

---

### Task 3: Documentation

**Files:** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Add `enigma/music.py` to Modules. Add a "Known format facts — entries and pitch" subsection: `dura`
is the written note value in EDU (whole = 4096), decoding to base + dots (tuplet scaling is a
separate detail, not yet modelled); a rest is `numNotes == 0`; pitch is `harmLev` (diatonic
displacement from the key's tonic) + `harmAlt` (alteration relative to the key), so absolute
spelling needs the key. Cite `docs/eeppd.txt`. Note the model is key-independent and stops at the
cross-pool boundary.

- [ ] **Step 2: `docs/ROADMAP.md`**

Mark typed entries done. Set the next item to **pitch spelling** — resolve `harmLev`/`harmAlt` plus
the key (via minimal `gfhold → frameSpec → measSpec` linkage) into absolute spelled pitches; note
this is the first slice that needs cross-pool link resolution. After that: tuplet duration scaling,
then the detail records (beams/stems/articulations/lyrics), toward a MusicXML exporter.

- [ ] **Step 3: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record the typed entry/note model and queue pitch spelling"
```

---

## Completion

After Task 3, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed (`read_entry` → typed `Entry`/`Note`/`Duration`); that
duration decodes the written note value (tuplets deferred) and pitch is the key-relative encoding
(spelling deferred, next slice); the mutation results (especially floor-vs-truncation for octave);
that the corpus sweep reads every entry in 401 archives and skips in CI; and that `read_entry`
raises `MalformedEntryError` on bad input rather than degrading.
