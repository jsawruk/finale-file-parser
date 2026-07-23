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
from typing import cast

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
    try:
        base = NoteValue(base_edu)
    except ValueError as exc:
        raise MalformedEntryError(f"dura {edu} base has no note value") from exc
    return Duration(edu=edu, base=base, dots=dots)


def _notes(record: Record) -> tuple[Note, ...]:
    raw = record.fields.get("note")
    records: tuple[Record, ...]
    if raw is None:
        records = ()
    elif isinstance(raw, Record):
        records = (raw,)
    elif isinstance(raw, tuple) and all(isinstance(r, Record) for r in raw):
        records = cast(tuple[Record, ...], raw)
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
