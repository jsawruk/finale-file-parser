"""What reaches the IR, not what the reader found.

`test_expressions_corpus_sweep` measures `expressions_by_measure` and it passes.
It cannot see this: 913 of the 11,543 expressions that reader returns never reach
a `Measure`, because `build_score` keys them by staff and 267 documents name a
staff no `Part` was built for. The sweep that was supposed to prove the feature
worked end to end only ever asked the reader whether the reader had read.

So this file asserts on the **delivered** object. The drop is pinned exactly, in
both directions: it must not grow, and if it shrinks the cause has been fixed and
the number here should say so.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.expressions import expressions_by_measure
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.errors import FinaleFileError

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

READ = 11543
"""Expressions `expressions_by_measure` returns across the corpus."""

PLACED = 10630
"""Expressions that reach a `Measure` in the IR."""

DROPPED_TO_A_STAFF_LIST = 596
"""Assigned with `staffAssign = -1`, which means the expression belongs to a
**staff list** rather than to one staff.

The file says so itself: all 746 corpus assignments carrying `staffAssign = -1`
also carry `staffGroup` *and* `staffList`, where a positive-staff assignment
almost never does (138 of 11,687). What is missing is the list's contents.
`staffList` selects a `categoryStaffListScore` record, whose repeated `inst`
field is `-1` in 6,215 of 6,419 incidences -- but the rest name real staves, and
`-1` appears *beside* them in tuples like `('-1', '9', '13')`. So `-1` cannot
simply be read as "every staff": that would place a marking on staves the list
may exclude. Left unresolved rather than guessed.
"""

DROPPED_ON_A_SILENT_STAFF = 317
"""Assigned to a staff that holds no notes anywhere in the document.

`build_score` builds one `Part` per staff that has music, so a staff carrying
only an expression gets no part and its marking has nowhere to go. Whether such
a staff should become an empty part is a question about part construction, not
about expressions, and changing it would move every part count in the project.
"""


class _Reading:
    def __init__(self) -> None:
        self.read = 0
        self.placed = 0
        self.documents = 0
        self.affected = 0
        self.dropped_by_staff: Counter[int] = Counter()


@pytest.fixture(scope="module")
def reading() -> _Reading:
    out = _Reading()
    for path in sorted(CORPUS.rglob("*.musx")):
        try:
            document = parse_enigma(score_xml(path))
            score = build_score(document)
        except (FinaleFileError, OSError):
            continue
        out.documents += 1
        found = expressions_by_measure(document)
        read = sum(len(items) for items in found.values())
        placed = sum(len(m.expressions) for part in score.parts for m in part.measures)
        out.read += read
        out.placed += placed
        if placed == read:
            continue
        out.affected += 1
        staves = {
            int(part.id[1:])
            for part in score.parts
            if part.id.startswith("P") and part.id[1:].lstrip("-").isdigit()
        }
        for (staff, _measure), items in found.items():
            if staff not in staves:
                out.dropped_by_staff[staff] += len(items)
    return out


def test_the_sweep_reaches_the_whole_corpus(reading: _Reading) -> None:
    assert reading.documents >= 395, f"only {reading.documents} documents built"
    assert reading.read == READ, f"the reader now returns {reading.read}, not {READ}"


def test_the_gap_between_read_and_placed_is_exactly_what_is_documented(
    reading: _Reading,
) -> None:
    """Pinned in both directions.

    Larger means a new way of losing a marking. Smaller means one of the two
    causes above has been fixed, and the constants here should record it rather
    than being quietly relaxed.
    """
    assert reading.placed == PLACED, f"{reading.placed} reach the IR, not {PLACED}"
    dropped = reading.read - reading.placed
    assert dropped == DROPPED_TO_A_STAFF_LIST + DROPPED_ON_A_SILENT_STAFF, (
        f"{dropped} expressions are dropped; the documented causes account for "
        f"{DROPPED_TO_A_STAFF_LIST + DROPPED_ON_A_SILENT_STAFF}"
    )


def test_both_causes_are_the_ones_documented(reading: _Reading) -> None:
    """Not just the total: each cause separately, so a fix to one cannot be
    masked by a regression in the other."""
    assert reading.dropped_by_staff[-1] == DROPPED_TO_A_STAFF_LIST
    on_a_real_staff = sum(n for staff, n in reading.dropped_by_staff.items() if staff >= 0)
    assert on_a_real_staff == DROPPED_ON_A_SILENT_STAFF
    assert set(reading.dropped_by_staff) - {-1} <= {1, 2, 3, 4, 5}, (
        "a staff number outside the documented range is losing markings"
    )


def test_most_expressions_do_reach_the_ir(reading: _Reading) -> None:
    """The gap is a known edge, not the common case: 92% arrive."""
    assert reading.placed / reading.read > 0.92
    assert reading.affected < reading.documents, "some document must place all of its markings"
