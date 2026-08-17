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
    for record in document.details.of_tag(_ASSIGNMENT):
        if "part" in record.attrs:
            continue
        entnum = field_int(record.attrs.get("entnum"))
        note_id = field_int(record.fields.get("noteID"))
        note_code = field_int(record.fields.get("noteCode"))
        if entnum is None or note_id is None or note_code is None:
            continue
        entry_record = document.entries.get(entnum)
        if entry_record is None:
            continue
        note_counts.setdefault(entnum, len(read_entry(entry_record).notes))
        out.setdefault(entnum, {})[note_id - 1] = note_code
    return out, note_counts


def _routes(document: EnigmaDocument) -> dict[int, int]:
    out: dict[int, int] = {}
    for record in document.others.of_tag(_ROUTE):
        if "part" in record.attrs:
            continue
        staff = field_int(record.attrs.get("cmper"))
        map_id = field_int(record.fields.get("percMapRefID"))
        if staff is not None and map_id is not None:
            out[staff] = map_id
    return out


def _definitions(document: EnigmaDocument) -> dict[tuple[int, int], Record]:
    out: dict[tuple[int, int], Record] = {}
    for record in document.others.of_tag(_DEFINITION):
        if "part" in record.attrs:
            continue
        map_id = field_int(record.attrs.get("cmper"))
        note_code = field_int(record.attrs.get("inci", "0"))
        if map_id is not None and note_code is not None:
            out[(map_id, note_code)] = record
    return out


def _appearance(record: Record) -> PercussionAppearance:
    harm_lev = field_int(record.fields.get("harmLev"))
    percussion_type = field_int(record.fields.get("percNoteType"))
    double_whole = field_int(record.fields.get("dwholeNotehead"))
    whole = field_int(record.fields.get("wholeNotehead"))
    half = field_int(record.fields.get("halfNotehead"))
    closed = field_int(record.fields.get("closedNotehead"))
    if harm_lev is None:
        raise MalformedPercussionError("harmLev is not an integer")
    if percussion_type is None:
        raise MalformedPercussionError("percNoteType is not an integer")
    if double_whole is None:
        raise MalformedPercussionError("dwholeNotehead is not an integer")
    if whole is None:
        raise MalformedPercussionError("wholeNotehead is not an integer")
    if half is None:
        raise MalformedPercussionError("halfNotehead is not an integer")
    if closed is None:
        raise MalformedPercussionError("closedNotehead is not an integer")
    return PercussionAppearance(
        harm_lev=harm_lev,
        percussion_type=percussion_type,
        double_whole_notehead=double_whole,
        whole_notehead=whole,
        half_notehead=half,
        closed_notehead=closed,
    )
