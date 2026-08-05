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
from finale_file_parser.ir import Measure, Score

__all__ = ["summarise_document", "summarise_score"]


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


def summarise_score(score: Score) -> dict[str, object]:
    """Per part, per measure -- not only totals.

    A measure that came out empty is exactly what someone diagnosing a bad
    conversion is looking for, and a total hides it.
    """

    class PartSummary(TypedDict):
        """Typed shape of a per-part summary."""

        id: str
        name: str
        measures: list[MeasureSummary]

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
