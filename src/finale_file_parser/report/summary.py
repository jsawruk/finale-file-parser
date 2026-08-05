"""Turning built objects into the report's two upper depths.

Pure functions over a `Score` and an `EnigmaDocument`, so they can be tested
without opening a file, and so a later renderer (a server, a terminal UI) gets
them unchanged.
"""

from __future__ import annotations

import collections

from finale_file_parser.enigma.document import EnigmaDocument
from finale_file_parser.enigma.mus_document import UNTRANSLATED
from finale_file_parser.ir import Measure, Score

__all__ = ["summarise_document", "summarise_score"]


def _measure(measure: Measure) -> dict[str, object]:
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
    parts: list[dict[str, object]] = [
        {
            "id": part.id,
            "name": part.name,
            "measures": [_measure(measure) for measure in part.measures],
        }
        for part in score.parts
    ]
    measures: list[dict[str, object]] = [
        m
        for part in parts
        for m in part["measures"]  # type: ignore[attr-defined]
    ]
    return {
        "parts": parts,
        "totals": {
            "parts": len(parts),
            "measures": len(measures),
            "events": sum(int(m["events"]) for m in measures),  # type: ignore[call-overload]
            "pitches": sum(int(m["pitches"]) for m in measures),  # type: ignore[call-overload]
        },
    }


_POOLS = ("header", "mappings", "options", "others", "details", "entries", "texts")


def summarise_document(document: EnigmaDocument) -> dict[str, object]:
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
