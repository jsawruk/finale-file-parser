"""Check clefs against the local corpus.

Skipped wherever corpus/ is absent (e.g. CI).

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from finale_file_parser.enigma.clef import (
    ClefSign,
    clef_definitions,
    clefs_by_measure,
)
from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

SAMPLE = 40
TABLE_SIZE = 18
"""Every corpus document defines exactly this many clefs."""
MIN_PLACEMENTS = 5000


def _archives() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*")) if p.is_file() and p.suffix.lower() == ".musx"][
        :SAMPLE
    ]


def test_every_measure_resolves_to_a_known_clef() -> None:
    """No measure may resolve to UNKNOWN, and every index must be in the table.

    An UNKNOWN here would mean a clef character the mapping does not cover, which
    is exactly the case that would silently mis-notate a staff on export.
    """
    signs: Counter[ClefSign] = Counter()
    placements = 0
    for path in _archives():
        document = parse_enigma(score_xml(path))
        table = clef_definitions(document)
        assert len(table) == TABLE_SIZE, f"clef table has {len(table)} entries"
        for index in clefs_by_measure(document).values():
            placements += 1
            assert index in table, f"clef index {index} is not in the table"
            signs[table[index].sign] += 1

    assert placements >= MIN_PLACEMENTS
    assert signs[ClefSign.UNKNOWN] == 0, f"{signs[ClefSign.UNKNOWN]} placements have no known sign"
    assert signs[ClefSign.G] > 0 and signs[ClefSign.F] > 0
    assert signs[ClefSign.SHAPE] > 0, "no shape clef in the sample; that path is untested"


def test_shape_clefs_carry_a_shape_not_a_character() -> None:
    """The two are mutually exclusive: a shape clef has no `clefChar`."""
    checked = 0
    for path in _archives()[:10]:
        document = parse_enigma(score_xml(path))
        for clef in clef_definitions(document).values():
            if clef.is_shape:
                assert clef.clef_char is None
                checked += 1
            else:
                assert clef.shape_id is None
    assert checked > 0
