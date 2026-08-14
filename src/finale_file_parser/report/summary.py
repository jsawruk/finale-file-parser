"""Turning built objects into the report's two upper depths.

Pure functions over a `Score` and an `EnigmaDocument`, so they can be tested
without opening a file, and so a later renderer (a server, a terminal UI) gets
them unchanged.
"""

from __future__ import annotations

import collections
from typing import TypedDict

from finale_file_parser.enigma.document import EnigmaDocument
from finale_file_parser.enigma.mus_document import UNTRANSLATED
from finale_file_parser.ir import Event, Measure, Pitch, Score

__all__ = [
    "DocumentSummary",
    "MeasureSummary",
    "MusicEvent",
    "MusicMeasure",
    "MusicPart",
    "MusicTree",
    "MusicVoice",
    "PartSummary",
    "ScoreSummary",
    "ScoreTotals",
    "music_tree",
    "summarise_document",
    "summarise_score",
]


class MeasureSummary(TypedDict):
    """Typed shape of a per-measure summary."""

    number: int
    time: str | None
    clef: str | None
    key: int | None
    events: int
    pitches: int


def _measure(measure: Measure) -> MeasureSummary:
    events = [event for voice in measure.voices for event in voice.events]
    time = f"{measure.time.beats}/{measure.time.beat_type}" if measure.time else None
    return {
        "number": measure.number,
        "time": time,
        "clef": measure.clef_sign,
        "key": measure.key_fifths,
        "events": len(events),
        "pitches": sum(len(event.pitches) for event in events),
    }


class PartSummary(TypedDict):
    """Typed shape of a per-part summary."""

    id: str
    name: str
    measures: list[MeasureSummary]


class ScoreTotals(TypedDict):
    """Typed shape of the score-level totals in a `ScoreSummary`."""

    parts: int
    measures: int
    events: int
    pitches: int


class ScoreSummary(TypedDict):
    """Typed shape of a score summary."""

    parts: list[PartSummary]
    totals: ScoreTotals


def summarise_score(score: Score) -> ScoreSummary:
    """Per part, per measure -- not only totals.

    A measure that came out empty is exactly what someone diagnosing a bad
    conversion is looking for, and a total hides it.
    """
    parts: list[PartSummary] = [
        {
            "id": part.id,
            "name": part.name,
            "measures": [_measure(measure) for measure in part.measures],
        }
        for part in score.parts
    ]
    measures: list[MeasureSummary] = [m for part in parts for m in part["measures"]]
    return {
        "parts": parts,
        "totals": {
            "parts": len(parts),
            "measures": len(measures),
            "events": sum(m["events"] for m in measures),
            "pitches": sum(m["pitches"] for m in measures),
        },
    }


_STEP_ALTER = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}


def _pitch(pitch: Pitch) -> str:
    """`F#4`. The alteration is spelled, not folded into the step, because a
    reader chasing a spelling bug needs to see which of the two it got wrong."""
    return f"{pitch.step}{_STEP_ALTER.get(pitch.alteration, f'?{pitch.alteration}')}{pitch.octave}"


class MusicEvent(TypedDict):
    """One event as the music tree shows it."""

    duration: str
    pitches: list[str]
    rest: bool
    tie: str | None
    grace: bool


class MusicVoice(TypedDict):
    """One layer of one measure. `mirrors` names the other staves showing this
    same music, and is empty for the ordinary case."""

    number: int
    events: list[MusicEvent]
    mirrors: list[int]


class MusicMeasure(TypedDict):
    """One measure of one part, its layers kept apart."""

    number: int
    voices: list[MusicVoice]


class MusicPart(TypedDict):
    """One part of the music tree."""

    id: str
    name: str
    staff: int | None
    measures: list[MusicMeasure]


class MusicTree(TypedDict):
    """Typed shape of the music tree."""

    parts: list[MusicPart]


def _event(event: Event) -> MusicEvent:
    tie = None
    if event.tie_start and event.tie_end:
        tie = "continue"
    elif event.tie_start:
        tie = "start"
    elif event.tie_end:
        tie = "stop"
    return {
        "duration": str(event.duration),
        "pitches": [_pitch(pitch) for pitch in event.pitches],
        "rest": not event.pitches,
        "tie": tie,
        "grace": event.is_grace,
    }


def _staff_number(part_id: str) -> int | None:
    """`build_score` names a part `P<staff>`, which is how a measure in this
    tree is matched to the placements that put music there. Returns None rather
    than guessing if that ever stops being true."""
    return int(part_id[1:]) if part_id.startswith("P") and part_id[1:].isdigit() else None


def music_tree(
    score: Score, mirrors: dict[tuple[int, int, int], list[int]] | None = None
) -> MusicTree:
    """The score as staff, measure, layer, event -- the shape the music has,
    rather than the shape the file stores.

    `mirrors` maps a `(staff, measure, layer)` cell to the other staves that
    display the same entries, so a mirrored layer can say so. It is passed in
    rather than derived here because working it out needs the document's
    cross-pool links, and this module is pure over the IR.

    **A mirrored passage appears under every staff that shows it.** That is not
    duplication in the report's sense -- it is what Finale prints, and what the
    exported MusicXML contains, because MusicXML has no mirror of its own.
    """
    found = mirrors or {}
    parts: list[MusicPart] = []
    for part in score.parts:
        staff = _staff_number(part.id)
        measures: list[MusicMeasure] = []
        for measure in part.measures:
            voices: list[MusicVoice] = [
                {
                    "number": voice.number,
                    "events": [_event(event) for event in voice.events],
                    "mirrors": found.get((staff, measure.number, voice.number), [])
                    if staff is not None
                    else [],
                }
                for voice in measure.voices
            ]
            measures.append({"number": measure.number, "voices": voices})
        parts.append({"id": part.id, "name": part.name, "staff": staff, "measures": measures})
    return {"parts": parts}


_POOLS = ("header", "mappings", "options", "others", "details", "entries", "texts")


class DocumentSummary(TypedDict):
    """Typed shape of a document summary."""

    version: str
    pools: dict[str, dict[str, int]]
    untranslated: list[str]


def summarise_document(document: EnigmaDocument) -> DocumentSummary:
    """Record counts by pool and tag, plus what this reader does not carry."""
    pools: dict[str, dict[str, int]] = {}
    for name in _POOLS:
        counts: collections.Counter[str] = collections.Counter()
        for record in getattr(document, name).records:
            counts[record.tag] += 1
        pools[name] = dict(counts)
    return {
        "version": document.version,
        "pools": pools,
        "untranslated": list(UNTRANSLATED),
    }
