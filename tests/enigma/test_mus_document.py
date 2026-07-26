"""Unit tests for the `.mus` -> `EnigmaDocument` adapter.

The three pool readers are stubbed, so these cover the translation itself: which
records are emitted, and the two places where *omitting* a field is the correct
translation rather than writing a zero.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from finale_file_parser.enigma import mus_document as adapter
from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.mus_details import MusDetailRecord
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_others import MusOther

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
    """Install the three pool readers' returns for one test."""

    def install(
        others: tuple[MusOther, ...] = (),
        details: tuple[MusDetailRecord, ...] = (),
        entries: tuple[Record, ...] = (),
    ) -> None:
        monkeypatch.setattr(adapter, "read_mus_others", lambda _p: others)
        monkeypatch.setattr(adapter, "read_mus_details", lambda _p: details)
        monkeypatch.setattr(adapter, "read_mus_entry_records", lambda _p: entries)

    return install


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
    pools(
        others=(MusOther(231, 1, 0, bytes(84)),),
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


def test_reports_what_it_does_not_translate() -> None:
    """`UNTRANSLATED` is the module's contract with its callers; an empty tuple
    would claim full fidelity."""
    assert adapter.UNTRANSLATED
    assert all(isinstance(gap, str) and gap for gap in adapter.UNTRANSLATED)
