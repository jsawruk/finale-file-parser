"""Decode the named percussion-map palette in a DCL-era ``.mus``.

The three records form one table. ``DL`` names a map, ``DF`` gives one input
note's playback and written appearance, and ``DN`` names that same input note.
Only the first two ``DF`` payload words have established semantics; the two
notehead values and trailing word stay raw rather than acquiring guessed names.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import ByteOrder
from finale_file_parser.enigma.mus_rows import MusRowRecord, MusRows

__all__ = ["DclPercussionEntry", "DclPercussionMap", "dcl_percussion_maps"]

_MAP_NAME = "DL"
_MAP_ENTRY = "DF"
_ENTRY_NAME = "DN"
_ENTRY_BYTES = 10
_TEXT_ENCODING: dict[ByteOrder, str] = {"big": "mac_roman", "little": "cp1252"}
"""DCL's big-endian files are Mac-origin; its little-endian files are Windows."""


@dataclass(frozen=True)
class DclPercussionEntry:
    """One input note in a DCL percussion map."""

    input_note: int
    playback_note: int
    staff_position: int
    notehead_values: tuple[int, int]
    trailing_value: int
    name: str | None = None


@dataclass(frozen=True)
class DclPercussionMap:
    """A DCL percussion map and its input-note palette."""

    map_id: int
    name: str | None
    entries: tuple[DclPercussionEntry, ...]


def dcl_percussion_maps(rows: MusRows) -> tuple[DclPercussionMap, ...]:
    """Join ``DL``, ``DF`` and ``DN`` records into typed percussion maps.

    The result is a palette, not proof that a score uses a map. DCL staff-to-map
    selection is not decoded, so this function deliberately stops before score
    placement or IR construction.
    """
    encoding = _TEXT_ENCODING[rows.byte_order]
    definitions = {
        (record.cmper, record.cmper2): record
        for record in rows.details.values()
        if record.tag == _MAP_ENTRY
    }
    names = {
        (record.cmper, record.cmper2): _text(record, encoding)
        for record in rows.details.values()
        if record.tag == _ENTRY_NAME
    }
    for map_id, input_note in names:
        if (map_id, input_note) not in definitions:
            raise CorruptScoreError(
                f"DN map {map_id} input note {input_note} has no DF percussion entry"
            )

    by_map: defaultdict[int, list[DclPercussionEntry]] = defaultdict(list)
    for (map_id, input_note), record in definitions.items():
        _check_note(map_id, "input note", input_note)
        if len(record.payload) != _ENTRY_BYTES:
            raise CorruptScoreError(
                f"DF map {map_id} input note {input_note} is {len(record.payload)} bytes; "
                f"expected {_ENTRY_BYTES}"
            )
        playback, position, notehead_a, notehead_b, trailing = (
            int.from_bytes(record.payload[at : at + 2], rows.byte_order)
            for at in range(0, _ENTRY_BYTES, 2)
        )
        _check_note(map_id, "playback note", playback)
        by_map[map_id].append(
            DclPercussionEntry(
                input_note=input_note,
                playback_note=playback,
                staff_position=_signed(position),
                notehead_values=(notehead_a, notehead_b),
                trailing_value=trailing,
                name=names.get((map_id, input_note)),
            )
        )

    map_names = {
        record.cmper: _text(record, encoding)
        for record in rows.others.values()
        if record.tag == _MAP_NAME
    }
    return tuple(
        DclPercussionMap(
            map_id=map_id,
            name=map_names.get(map_id),
            entries=tuple(sorted(by_map[map_id], key=lambda entry: entry.input_note)),
        )
        for map_id in sorted(by_map)
    )


def _text(record: MusRowRecord, encoding: str) -> str:
    return record.payload.split(b"\0", 1)[0].decode(encoding, errors="replace").rstrip()


def _check_note(map_id: int, field: str, value: int) -> None:
    if not 0 <= value <= 127:
        raise CorruptScoreError(f"DF map {map_id} {field} {value} is outside 0..127")


def _signed(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value
