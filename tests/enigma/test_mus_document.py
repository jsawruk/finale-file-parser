"""Unit tests for the `.mus` -> `EnigmaDocument` adapter.

The three pool readers are stubbed, so these cover the translation itself: which
records are emitted, and the two places where *omitting* a field is the correct
translation rather than writing a zero.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction

import pytest

from finale_file_parser.enigma import mus_details
from finale_file_parser.enigma import mus_document as adapter
from finale_file_parser.enigma.clef import ClefSign, clef_definitions
from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.mus_details import (
    TAG_LYRIC_VERSE,
    TAG_TUPLET_DEF,
    MusDetailRecord,
)
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_others import (
    OPTIONS_CMPER,
    TAG_CLEF_OPTIONS,
    TAG_STAFF_SPEC,
    MusOther,
)
from finale_file_parser.enigma.pitch import read_transposition
from finale_file_parser.enigma.tuplet import tuplets_by_entry

PATH = "unused.mus"
"""Every reader is stubbed, so no file is ever opened."""

FRAME_SPEC = 146
MEAS_SPEC = 176
GFHOLD = 1044


def meas_spec_payload(width: int, key: int, beats: int, divbeat: int) -> bytes:
    return b"".join(v.to_bytes(2, "little") for v in (width, key, beats, divbeat))


def gfhold_payload(clef: int, frame1: int, frame2: int = 0) -> bytes:
    return (
        clef.to_bytes(2, "little")
        + bytes(4)
        + frame1.to_bytes(2, "little")
        + frame2.to_bytes(2, "little")
        + bytes(10)
    )


@pytest.fixture
def pools(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Install the three pool readers' returns, and the banner year, for one test."""

    def install(
        others: tuple[MusOther, ...] = (),
        details: tuple[MusDetailRecord, ...] = (),
        entries: tuple[Record, ...] = (),
        texts: tuple[Record, ...] = (),
        year: int | None = 2011,
    ) -> None:
        monkeypatch.setattr(adapter, "read_mus_others", lambda _p: others)
        monkeypatch.setattr(adapter, "read_mus_details", lambda _p: details)
        monkeypatch.setattr(adapter, "read_mus_entry_records", lambda _p: entries)
        monkeypatch.setattr(adapter, "_texts_records", lambda _p: list(texts))
        monkeypatch.setattr(adapter, "_banner_year", lambda _p: year)

    return install


def clef_entry(stride: int, adjust: int, char: int, ydisp: int, shape: int = 0) -> bytes:
    """One clef-table entry in the layout the given stride implies."""
    offsets = adapter._CLEF_FIELD_OFFSETS[stride]
    entry = bytearray(stride)
    for name, value in (
        ("adjust", adjust),
        ("clefChar", char),
        ("clefYDisp", ydisp),
        ("shapeID", shape),
    ):
        at = offsets[name]
        entry[at : at + 2] = value.to_bytes(2, "little", signed=value < 0)
    return bytes(entry)


def test_translates_a_frame_spec(pools: Callable[..., None]) -> None:
    pools(
        others=(MusOther(FRAME_SPEC, 3, 0, (9).to_bytes(4, "little") + (10).to_bytes(4, "little")),)
    )
    record = read_mus_document(PATH).others.get("frameSpec", 3)
    assert record is not None
    assert (record.fields["startEntry"], record.fields["endEntry"]) == ("9", "10")


def test_translates_a_measure_s_key_and_beats(pools: Callable[..., None]) -> None:
    pools(others=(MusOther(MEAS_SPEC, 1, 0, meas_spec_payload(305, 253, 2, 1024)),))
    record = read_mus_document(PATH).others.get("measSpec", 1)
    assert record is not None
    key_sig = record.fields["keySig"]
    assert isinstance(key_sig, Record) and key_sig.fields["key"] == "253"
    assert (record.fields["beats"], record.fields["divbeat"]) == ("2", "1024")


def test_a_zero_key_becomes_no_key_signature_at_all(pools: Callable[..., None]) -> None:
    """`.mus` stores 0 where a `.musx` omits the element, and an absent key means
    "inherit the previous measure's". Writing `key="0"` instead would silently
    turn every inheriting measure into C major."""
    pools(others=(MusOther(MEAS_SPEC, 2, 0, meas_spec_payload(305, 0, 2, 1024)),))
    record = read_mus_document(PATH).others.get("measSpec", 2)
    assert record is not None
    assert "keySig" not in record.fields


def test_marks_a_part_variant_and_leaves_the_score_record_unmarked(
    pools: Callable[..., None],
) -> None:
    """Downstream modules select score records by the *absence* of `part`."""
    pools(
        others=(
            MusOther(MEAS_SPEC, 1, 0, meas_spec_payload(305, 253, 2, 1024)),
            MusOther(MEAS_SPEC, 1, 1, meas_spec_payload(600, 253, 2, 1024)),
        )
    )
    document = read_mus_document(PATH)
    score = document.others.get("measSpec", 1)
    variant = document.others.get("measSpec", 1, part=1)
    assert score is not None and "part" not in score.attrs
    assert variant is not None and variant.attrs["part"] == "1"


def test_translates_a_gfhold_with_two_layers(pools: Callable[..., None]) -> None:
    pools(details=(MusDetailRecord(GFHOLD, 2, 7, 0, gfhold_payload(3, 32, 33)),))
    record = read_mus_document(PATH).details.get("gfhold", 2, 7)
    assert record is not None
    assert (record.attrs["cmper1"], record.attrs["cmper2"]) == ("2", "7")
    assert (record.fields["clefID"], record.fields["frame1"]) == ("3", "32")
    assert record.fields["frame2"] == "33"


def test_an_empty_layer_slot_is_omitted(pools: Callable[..., None]) -> None:
    """A frame of 0 means the layer holds nothing. Emitting `frame2="0"` would
    send `locate_entries` looking for a frameSpec numbered 0."""
    pools(details=(MusDetailRecord(GFHOLD, 1, 1, 0, gfhold_payload(0, 32, 0)),))
    record = read_mus_document(PATH).details.get("gfhold", 1, 1)
    assert record is not None
    assert "frame2" not in record.fields


def test_passes_entry_records_through(pools: Callable[..., None]) -> None:
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    pools(entries=(entry,))
    assert read_mus_document(PATH).entries.get(9) is entry


def test_skips_record_types_it_cannot_translate(pools: Callable[..., None]) -> None:
    """An undecoded payload is left out, never guessed at."""
    # 140 is fretboardSymbol and 1043 fretboard: both identified by key
    # sequence only, so neither is translated.
    pools(
        others=(MusOther(140, 1, 0, bytes(84)),),
        details=(MusDetailRecord(1043, 1, 1, 0, bytes(40)),),
    )
    document = read_mus_document(PATH)
    assert document.others.records == ()
    assert document.details.records == ()


def test_skips_a_payload_too_short_for_its_fields(pools: Callable[..., None]) -> None:
    pools(
        others=(MusOther(FRAME_SPEC, 3, 0, b"\x09\x00"),),
        details=(MusDetailRecord(GFHOLD, 1, 1, 0, b"\x00\x00"),),
    )
    document = read_mus_document(PATH)
    assert document.others.records == ()
    assert document.details.records == ()


@pytest.mark.parametrize(("year", "stride"), [(2011, 18), (2012, 20)])
def test_translates_the_clef_table_in_either_era_layout(
    pools: Callable[..., None], year: int, stride: int
) -> None:
    """2012 moved `clefYDisp` and `shapeID`; the banner year picks the layout."""
    payload = clef_entry(stride, -10, 38, -6) + clef_entry(stride, 2, 63, -2)
    pools(others=(MusOther(TAG_CLEF_OPTIONS, OPTIONS_CMPER, 0, payload),), year=year)
    table = clef_definitions(read_mus_document(PATH))
    assert len(table) == 2
    assert (table[0].clef_char, table[0].adjust, table[0].y_displacement) == (38, -10, -6)
    assert (table[1].clef_char, table[1].adjust, table[1].y_displacement) == (63, 2, -2)


def test_a_shape_clef_keeps_its_shape_id(pools: Callable[..., None]) -> None:
    pools(
        others=(MusOther(TAG_CLEF_OPTIONS, OPTIONS_CMPER, 0, clef_entry(18, -10, 0, 0, shape=50)),)
    )
    table = clef_definitions(read_mus_document(PATH))
    assert (table[0].shape_id, table[0].clef_char) == (50, None)
    assert table[0].sign is ClefSign.SHAPE


def test_a_zero_clef_char_becomes_an_absent_field(pools: Callable[..., None]) -> None:
    """Absent means "there is no character"; `clefChar="0"` would be a real
    character, and `Clef.sign` must report UNKNOWN rather than inventing one."""
    pools(others=(MusOther(TAG_CLEF_OPTIONS, OPTIONS_CMPER, 0, clef_entry(18, -10, 0, -6)),))
    table = clef_definitions(read_mus_document(PATH))
    assert table[0].clef_char is None
    assert table[0].sign is ClefSign.UNKNOWN


def test_skips_a_clef_table_that_is_not_a_whole_number_of_entries(
    pools: Callable[..., None],
) -> None:
    """A mis-strided table would yield plausible wrong clefs, so emit none."""
    pools(others=(MusOther(TAG_CLEF_OPTIONS, OPTIONS_CMPER, 0, clef_entry(18, -10, 38, -6)[:-3]),))
    assert clef_definitions(read_mus_document(PATH)) == {}


def test_skips_the_clef_table_when_the_era_is_unknown(pools: Callable[..., None]) -> None:
    """No banner year means no way to know the entry width."""
    pools(
        others=(MusOther(TAG_CLEF_OPTIONS, OPTIONS_CMPER, 0, clef_entry(18, -10, 38, -6)),),
        year=None,
    )
    assert clef_definitions(read_mus_document(PATH)) == {}


def tuplet_payload(sym_num: int, sym_dur: int, ref_num: int, ref_dur: int) -> bytes:
    return b"".join(v.to_bytes(2, "little") for v in (sym_num, sym_dur, ref_num, ref_dur)) + bytes(
        22
    )


def test_translates_a_tuplet_and_keys_it_by_entry(pools: Callable[..., None]) -> None:
    """A detail hanging off an entry packs the 32-bit entnum into the two key
    fields, high word first."""
    pools(details=(MusDetailRecord(TAG_TUPLET_DEF, 1, 4660, 0, tuplet_payload(3, 512, 2, 512)),))
    record = mus_details.entry_key(MusDetailRecord(TAG_TUPLET_DEF, 1, 4660, 0, b""))
    assert record == 70196
    tuplets = tuplets_by_entry(read_mus_document(PATH))
    assert list(tuplets) == [70196]
    assert tuplets[70196][0].ratio == Fraction(2, 3)


def test_a_tuplet_ratio_is_not_inverted(pools: Callable[..., None]) -> None:
    """Every corpus tuplet is 3:2, so nothing in the data distinguishes
    `symbolicNum` from `refNum`. A 5:4 case would come out 4/5 if the pairs were
    swapped, and 5/4 if not."""
    pools(details=(MusDetailRecord(TAG_TUPLET_DEF, 0, 9, 0, tuplet_payload(5, 256, 4, 256)),))
    assert tuplets_by_entry(read_mus_document(PATH))[9][0].ratio == Fraction(4, 5)


def test_skips_a_tuplet_payload_too_short_for_its_fields(pools: Callable[..., None]) -> None:
    pools(details=(MusDetailRecord(TAG_TUPLET_DEF, 0, 9, 0, b"\x03\x00"),))
    assert tuplets_by_entry(read_mus_document(PATH)) == {}


def staff_spec_payload(transposition: int) -> bytes:
    payload = bytearray(84)
    payload[20:22] = transposition.to_bytes(2, "little")
    return bytes(payload)


@pytest.mark.parametrize(
    ("stored", "adjust"),
    [(0x0000, 0), (0x0101, 1), (0x0042, 2), (0x0F83, 3)],
)
def test_reads_the_transposition_key_alteration(
    pools: Callable[..., None], stored: int, adjust: int
) -> None:
    """The alteration is the low nibble; the upper bits are something else and
    are deliberately not interpreted."""
    pools(others=(MusOther(TAG_STAFF_SPEC, 1, 0, staff_spec_payload(stored)),))
    record = read_mus_document(PATH).others.get("staffSpec", 1)
    assert record is not None
    assert read_transposition(record).adjust == adjust


def test_a_negative_alteration_is_sign_and_magnitude(pools: Callable[..., None]) -> None:
    """Bit 3 is the sign, as `eeppd.txt` documents for a note TCD -- not two's
    complement, under which 0x9 would read as -7 rather than -1. Every corpus
    value is positive, so nothing in the corpus distinguishes these."""
    pools(others=(MusOther(TAG_STAFF_SPEC, 1, 0, staff_spec_payload(0x0009)),))
    record = read_mus_document(PATH).others.get("staffSpec", 1)
    assert record is not None
    assert read_transposition(record).adjust == -1


def test_the_transposition_interval_is_left_absent(pools: Callable[..., None]) -> None:
    """The `.mus` does not store it. Absent reads as 0, which is right for the
    written pitch and wrong for the concert pitch -- see UNTRANSLATED."""
    pools(others=(MusOther(TAG_STAFF_SPEC, 1, 0, staff_spec_payload(0x0042)),))
    record = read_mus_document(PATH).others.get("staffSpec", 1)
    assert record is not None
    assert read_transposition(record).interval == 0


def test_a_concert_staff_gets_no_transposition_record(pools: Callable[..., None]) -> None:
    pools(others=(MusOther(TAG_STAFF_SPEC, 1, 0, staff_spec_payload(0)),))
    record = read_mus_document(PATH).others.get("staffSpec", 1)
    assert record is not None
    assert "transposition" not in record.fields


def lyric_payload(*groups: tuple[int, int, bool]) -> bytes:
    """A lyrDataVerse payload: one 20-byte group per verse."""
    out = bytearray()
    for number, syll, extend in groups:
        block = bytearray(20)
        block[0:2] = number.to_bytes(2, "little")
        block[2:4] = syll.to_bytes(2, "little")
        block[8:10] = (1 if extend else 0).to_bytes(2, "little")
        out += block
    return bytes(out)


def test_one_mus_lyric_record_becomes_one_record_per_verse(
    pools: Callable[..., None],
) -> None:
    """A `.mus` packs every verse into one record; a `.musx` writes one each.
    Splitting here is what lets one lyrics module read both."""
    pools(
        details=(
            MusDetailRecord(TAG_LYRIC_VERSE, 0, 9, 0, lyric_payload((1, 3, False), (2, 4, True))),
        )
    )
    found = read_mus_document(PATH).details.of_tag("lyrDataVerse")
    assert [(r.attrs["entnum"], r.fields["lyricNumber"], r.fields["syll"]) for r in found] == [
        ("9", "1", "3"),
        ("9", "2", "4"),
    ]
    assert "wext" not in found[0].fields
    assert "wext" in found[1].fields


def test_a_repeated_lyric_assignment_is_emitted_once(pools: Callable[..., None]) -> None:
    """A `.mus` repeats an entry's assignments, usually as two identical
    records. Emitting both would sing every syllable twice."""
    payload = lyric_payload((1, 3, False))
    pools(
        details=(
            MusDetailRecord(TAG_LYRIC_VERSE, 0, 9, 0, payload),
            MusDetailRecord(TAG_LYRIC_VERSE, 0, 9, 1, payload),
        )
    )
    assert len(read_mus_document(PATH).details.of_tag("lyrDataVerse")) == 1


def test_an_empty_verse_slot_is_skipped(pools: Callable[..., None]) -> None:
    pools(details=(MusDetailRecord(TAG_LYRIC_VERSE, 0, 9, 0, lyric_payload((0, 0, False))),))
    assert read_mus_document(PATH).details.of_tag("lyrDataVerse") == ()


def test_reports_what_it_does_not_translate() -> None:
    """`UNTRANSLATED` is the module's contract with its callers; an empty tuple
    would claim full fidelity."""
    assert adapter.UNTRANSLATED
    assert all(isinstance(gap, str) and gap for gap in adapter.UNTRANSLATED)
