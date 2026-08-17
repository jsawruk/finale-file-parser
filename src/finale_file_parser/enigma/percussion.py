"""Resolve Finale percussion assignments onto placed entry notes."""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record, field_int
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.errors import FinaleFileError

__all__ = [
    "MalformedPercussionError",
    "PercussionAppearance",
    "PercussionNote",
    "percussion_notes",
]

_ASSIGNMENT = "percussionNoteCode"
_DEFINITION = "percussionNoteInfo"
_ROUTE = "playbackRoute"


class MalformedPercussionError(FinaleFileError):
    """Percussion records do not form a consistent placed-note mapping."""


@dataclass(frozen=True)
class PercussionAppearance:
    harm_lev: int
    percussion_type: int
    double_whole_notehead: int
    whole_notehead: int
    half_notehead: int
    closed_notehead: int


@dataclass(frozen=True)
class PercussionNote:
    map_id: int
    note_code: int
    appearance: PercussionAppearance | None


def _required_int(value: object, name: str) -> int:
    parsed = field_int(value)
    if parsed is None:
        raise MalformedPercussionError(f"{name} is not an integer: {value!r}")
    return parsed


def percussion_notes(
    document: EnigmaDocument,
) -> dict[tuple[int, int], tuple[PercussionNote | None, ...]]:
    assignments, note_counts = _assignments(document)
    if not assignments:
        return {}
    placements = locate_entries(document)
    routes = _routes(document)
    definitions = _definitions(document)
    out: dict[tuple[int, int], tuple[PercussionNote | None, ...]] = {}
    for entnum, by_index in assignments.items():
        for placement in placements.get(entnum, ()):
            map_id = routes.get(placement.staff)
            if map_id is None:
                continue
            notes: list[PercussionNote | None] = [None] * note_counts[entnum]
            for note_index, note_code in by_index.items():
                record = definitions.get((map_id, note_code))
                notes[note_index] = PercussionNote(
                    map_id=map_id,
                    note_code=note_code,
                    appearance=None if record is None else _appearance(record),
                )
            value = tuple(notes)
            previous = out.setdefault((entnum, placement.staff), value)
            if previous != value:
                raise MalformedPercussionError(
                    f"entry {entnum} resolves differently twice on staff {placement.staff}"
                )
    return out


def _assignments(document: EnigmaDocument) -> tuple[dict[int, dict[int, int]], dict[int, int]]:
    out: dict[int, dict[int, int]] = {}
    note_counts: dict[int, int] = {}
    seen: set[tuple[int, int]] = set()
    for record in document.details.of_tag(_ASSIGNMENT):
        if "part" in record.attrs:
            continue
        entnum = _required_int(record.attrs.get("entnum"), "entnum")
        inci = _required_int(record.attrs.get("inci", "0"), "inci")
        note_id = _required_int(record.fields.get("noteID"), "noteID")
        note_code = _required_int(record.fields.get("noteCode"), "noteCode")
        identity = (entnum, note_id)
        if identity in seen:
            raise MalformedPercussionError(
                f"duplicate percussion assignment for entry {entnum} noteID {note_id}"
            )
        seen.add(identity)
        if inci != note_id - 1:
            raise MalformedPercussionError(
                f"percussion assignment inci={inci} disagrees with noteID={note_id}"
            )
        note_count = note_counts.get(entnum)
        if note_count is None:
            entry_record = document.entries.get(entnum)
            if entry_record is None:
                raise MalformedPercussionError(
                    f"percussion assignment names missing entry {entnum}"
                )
            note_count = len(read_entry(entry_record).notes)
            note_counts[entnum] = note_count
        if not 1 <= note_id <= note_count:
            raise MalformedPercussionError(
                f"noteID={note_id} outside entry {entnum} with {note_count} note(s)"
            )
        out.setdefault(entnum, {})[note_id - 1] = note_code
    return out, note_counts


def _routes(document: EnigmaDocument) -> dict[int, int]:
    out: dict[int, int] = {}
    seen: set[int] = set()
    for record in document.others.of_tag(_ROUTE):
        if "part" in record.attrs:
            continue
        staff = _required_int(record.attrs.get("cmper"), "cmper")
        if staff in seen:
            raise MalformedPercussionError(f"duplicate percussion route for staff {staff}")
        seen.add(staff)
        map_ref = record.fields.get("percMapRefID")
        if map_ref is not None:
            out[staff] = _required_int(map_ref, "percMapRefID")
    return out


def _definitions(document: EnigmaDocument) -> dict[tuple[int, int], Record]:
    out: dict[tuple[int, int], Record] = {}
    for record in document.others.of_tag(_DEFINITION):
        if "part" in record.attrs:
            continue
        map_id = _required_int(record.attrs.get("cmper"), "cmper")
        note_code = _required_int(record.attrs.get("inci", "0"), "inci")
        identity = (map_id, note_code)
        if identity in out:
            raise MalformedPercussionError(
                f"duplicate percussion definition for map {map_id} noteCode {note_code}"
            )
        out[identity] = record
    return out


def _appearance(record: Record) -> PercussionAppearance:
    harm_lev = _required_int(record.fields.get("harmLev"), "harmLev")
    percussion_type = _required_int(record.fields.get("percNoteType"), "percNoteType")
    double_whole = _required_int(record.fields.get("dwholeNotehead"), "dwholeNotehead")
    whole = _required_int(record.fields.get("wholeNotehead"), "wholeNotehead")
    half = _required_int(record.fields.get("halfNotehead"), "halfNotehead")
    closed = _required_int(record.fields.get("closedNotehead"), "closedNotehead")
    return PercussionAppearance(
        harm_lev=harm_lev,
        percussion_type=percussion_type,
        double_whole_notehead=double_whole,
        whole_notehead=whole,
        half_notehead=half,
        closed_notehead=closed,
    )
