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

_Field = str | tuple[str, ...] | Record | tuple[Record, ...]


def _note(harm_lev: str, harm_alt: str = "0", **flags: str) -> Record:
    fields: dict[str, _Field] = {"harmLev": harm_lev, "harmAlt": harm_alt, "isValid": ""}
    fields.update(flags)
    return Record(tag="note", attrs={}, text="", fields=fields)


def _entry(dura: str, notes: tuple[Record, ...] = (), **extra: str) -> Record:
    fields: dict[str, _Field] = {
        "dura": dura,
        "numNotes": str(len(notes)),
        "isValid": "",
    }
    if notes:
        fields["note"] = notes if len(notes) > 1 else notes[0]
    fields.update(extra)
    return Record(tag="entry", attrs={"entnum": "1"}, text="", fields=fields)


def test_quarter_note_single_pitch() -> None:
    entry: Entry = read_entry(_entry("1024", (_note("0"),)))
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
    d: Duration = read_entry(_entry("1536", (_note("1"),))).duration
    assert d.base is NoteValue.QUARTER
    assert d.dots == 1
    assert d.whole_notes == Fraction(3, 8)


def test_double_dotted_half() -> None:
    d = read_entry(_entry("3584", (_note("0"),))).duration  # 2048+1024+512
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
    n: Note = read_entry(_entry("1024", (_note("-1"),))).notes[0]
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
