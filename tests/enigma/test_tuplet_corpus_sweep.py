"""Check tuplet scaling against real scores, using measures that must add up.

Skipped wherever corpus/ is absent (e.g. CI).

The check is independent of the tuplet code: a measure's entries must sound for
exactly the time its time signature allows. Written durations do *not* satisfy
that wherever a tuplet occurs, so the number of measures that balance is a direct
measure of whether scaling works -- not a restatement of it.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.tuplet import entry_chain, sounded_durations, tuplets_by_entry

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

MIN_DOCUMENTS_WITH_TUPLETS = 5
MIN_BALANCED_FRACTION = 0.99
"""Measured: 1,420 of 1,423 layer-measures balance once scaled (99.8%).

Each layer independently fills its measure, so the grouping is
(staff, measure, layer). Grouping by (staff, measure) alone scores only 1,248 of
1,333, because a two-layer measure then sums to exactly twice its time signature.

The 3 that remain sit at ratios below 1 (5/6, 1/2) -- a layer holding fewer notes
than the measure allows, which is ordinary notation rather than a decode problem.
"""


def _measure_capacity(document: EnigmaDocument) -> dict[int, int]:
    """Written EDU each measure holds, for measures that state a time signature."""
    out: dict[int, int] = {}
    for record in document.others.records:
        if record.tag != "measSpec":
            continue
        beats, divbeat = record.fields.get("beats"), record.fields.get("divbeat")
        if isinstance(beats, str) and isinstance(divbeat, str):
            out[int(record.attrs["cmper"])] = int(beats) * int(divbeat)
    return out


def _documents_with_tuplets() -> list[Path]:
    out = []
    for path in sorted(CORPUS.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".musx":
            document = parse_enigma(score_xml(path))
            if tuplets_by_entry(document):
                out.append(path)
            if len(out) >= 12:
                break
    return out


def test_scaling_makes_measures_balance() -> None:
    documents = _documents_with_tuplets()
    assert len(documents) >= MIN_DOCUMENTS_WITH_TUPLETS

    measures = balanced_sounded = balanced_written = 0
    for path in documents:
        document = parse_enigma(score_xml(path))
        chain = entry_chain(document)
        sounded = sounded_durations(chain, tuplets_by_entry(document))
        location = locate_entries(document)
        capacity = _measure_capacity(document)

        # Grouped by layer as well as (staff, measure): layers fill the measure
        # independently, so summing across them double-counts the time.
        by_measure: dict[tuple[int, int, int], Fraction] = defaultdict(Fraction)
        written_by_measure: dict[tuple[int, int, int], int] = defaultdict(int)
        for entnum, duration in sounded.items():
            for here in location.get(entnum, ()):
                # every placement, not just the first: a mirrored staff's measure
                # genuinely holds this music, and skipping it would read as a
                # measure that fails to fill its time signature
                key = (here.staff, here.measure, here.layer)
                by_measure[key] += duration
                written_by_measure[key] += chain.written_edu[entnum]

        for key, total in by_measure.items():
            expected = capacity.get(key[1])
            if not expected:
                continue
            measures += 1
            balanced_sounded += total == expected
            balanced_written += written_by_measure[key] == expected

    assert measures > 0
    assert balanced_sounded >= MIN_BALANCED_FRACTION * measures, (
        f"only {balanced_sounded} of {measures} layer-measures balance once scaled"
    )
    # The point of the whole module: written durations do not balance where a
    # tuplet occurs. If this ever stops holding, the sweep has stopped proving
    # anything and is just asserting that addition works.
    assert balanced_written < balanced_sounded, (
        "written durations balance as often as sounded ones -- "
        "this corpus no longer exercises tuplet scaling"
    )
