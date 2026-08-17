"""Typed crosswalk for the DCL percussion palette."""

from __future__ import annotations

import pytest

import finale_file_parser.enigma as enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import ByteOrder
from finale_file_parser.enigma.mus_rows import MusRowRecord, MusRows


def _words(order: ByteOrder, *values: int) -> bytes:
    return b"".join(value.to_bytes(2, order) for value in values)


@pytest.mark.parametrize("order", ["little", "big"])
def test_dcl_percussion_maps_join_names_playback_and_appearance(order: ByteOrder) -> None:
    """Changing either byte order or any of the three record joins breaks this."""
    rows = MusRows(
        others={
            ("DL", 2): MusRowRecord(
                tag="DL",
                cmper=2,
                payload=b"Bass Clef Entry, Gen MIDI Playback\0",
                incidences=3,
            )
        },
        details={
            ("DF", 2, 41): MusRowRecord(
                tag="DF",
                cmper=2,
                cmper2=41,
                payload=_words(order, 44, 1, 121, 89, 0),
                incidences=1,
            ),
            ("DF", 2, 52): MusRowRecord(
                tag="DF",
                cmper=2,
                cmper2=52,
                payload=_words(order, 38, 7, 207, 250, 0),
                incidences=1,
            ),
            ("DN", 2, 41): MusRowRecord(
                tag="DN",
                cmper=2,
                cmper2=41,
                payload=b"Hi-Hat Foot\0".ljust(20, b"\0"),
                incidences=2,
            ),
            ("DN", 2, 52): MusRowRecord(
                tag="DN",
                cmper=2,
                cmper2=52,
                payload=b"Snare\0".ljust(10, b"\0"),
                incidences=1,
            ),
        },
        byte_order=order,
    )

    (percussion_map,) = enigma.dcl_percussion_maps(rows)

    assert percussion_map.map_id == 2
    assert percussion_map.name == "Bass Clef Entry, Gen MIDI Playback"
    assert [entry.input_note for entry in percussion_map.entries] == [41, 52]
    foot, snare = percussion_map.entries
    assert (
        foot.playback_note,
        foot.staff_position,
        foot.notehead_values,
        foot.trailing_value,
        foot.name,
    ) == (44, 1, (121, 89), 0, "Hi-Hat Foot")
    assert (
        snare.playback_note,
        snare.staff_position,
        snare.notehead_values,
        snare.trailing_value,
        snare.name,
    ) == (38, 7, (207, 250), 0, "Snare")


def test_a_dcl_percussion_row_must_hold_exactly_five_words() -> None:
    """A truncated row must be refused instead of shifting field boundaries."""
    rows = MusRows(
        details={
            ("DF", 1, 35): MusRowRecord(
                tag="DF", cmper=1, cmper2=35, payload=b"\x00" * 8, incidences=1
            )
        }
    )

    with pytest.raises(CorruptScoreError, match="DF.*8 bytes.*expected 10"):
        enigma.dcl_percussion_maps(rows)


def test_a_dcl_percussion_name_cannot_point_to_a_missing_map_entry() -> None:
    """Silently dropping an orphaned name would make the crosswalk incomplete."""
    rows = MusRows(
        details={
            ("DN", 1, 35): MusRowRecord(
                tag="DN",
                cmper=1,
                cmper2=35,
                payload=b"Acoustic Bass Drum\0".ljust(20, b"\0"),
                incidences=2,
            )
        }
    )

    with pytest.raises(CorruptScoreError, match="DN.*map 1 input note 35.*no DF"):
        enigma.dcl_percussion_maps(rows)


@pytest.mark.parametrize(
    ("input_note", "playback_note", "field"),
    [(128, 35, "input note"), (35, 128, "playback note")],
)
def test_a_dcl_percussion_note_must_be_in_the_midi_range(
    input_note: int, playback_note: int, field: str
) -> None:
    rows = MusRows(
        details={
            ("DF", 1, input_note): MusRowRecord(
                tag="DF",
                cmper=1,
                cmper2=input_note,
                payload=_words("little", playback_note, 0, 0, 0, 0),
                incidences=1,
            )
        }
    )

    with pytest.raises(CorruptScoreError, match=rf"DF.*{field}.*128.*0\.\.127"):
        enigma.dcl_percussion_maps(rows)


def test_big_endian_dcl_names_use_the_mac_encoding() -> None:
    name = "Tambouriné"
    rows = MusRows(
        others={
            ("DL", 1): MusRowRecord(
                tag="DL",
                cmper=1,
                payload=name.encode("mac_roman") + b"\0",
                incidences=1,
            )
        },
        details={
            ("DF", 1, 35): MusRowRecord(
                tag="DF",
                cmper=1,
                cmper2=35,
                payload=_words("big", 35, 0, 0, 0, 0),
                incidences=1,
            )
        },
        byte_order="big",
    )

    (percussion_map,) = enigma.dcl_percussion_maps(rows)

    assert percussion_map.name == name
