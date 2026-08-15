"""What reaches the IR, not what the reader found.

`test_expressions_corpus_sweep` measures `expressions_by_measure` and it passes.
It could not see that 913 of the expressions that reader returned never reached a
`Measure`: `build_score` keys them by staff, and 267 documents named a staff no
`Part` was built for. The sweep meant to prove the feature end to end only ever
asked the reader whether the reader had read.

So this file asserts on the **delivered** object.

**596 of that 913 are now recovered.** A score expression -- `staffAssign = -1`,
meaning a staff list -- is placed on the topmost part, which is where such a
marking is engraved; see `to_ir._place_score_wide` for why that is a convention
rather than a decode. What remains is one cause, pinned in both directions: it
must not grow, and if it shrinks the constant here should say so.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.expressions import SCORE_WIDE_STAFF, expressions_by_measure
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.errors import FinaleFileError

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

READ = 11642
"""Expressions `expressions_by_measure` returns across the corpus.

Was 11,462. The 180 more are dynamics the file names in `descStr` but has no
expression text for; they were dropped for having nothing to print, and
`<dynamics><mp/></dynamics>` never needed a character.
"""

PLACED = 11277
"""Expressions that reach a `Measure` in the IR.

Was 11,145. The 132 more are textless dynamics; the other 48 of the 180
recovered land on a staff with no notes and are lost downstream instead.
"""

SCORE_WIDE = 515
"""Markings the file attaches to a staff list rather than a staff, as delivered.

Not 596. That was the count before redundant copies were dropped: 746 corpus
assignments carry `staffAssign = -1`, 596 of them survived the reader's other
checks, and 81 of those were a second copy of a marking the same measure already
places on a real staff. 515 remain, and every one reaches the top part.

Pinned as a *placed* count rather than a lost one -- if it falls, score
expressions have stopped arriving again.
"""

DROPPED_ON_A_SILENT_STAFF = 365
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
        self.score_wide = 0
        self.on_the_top_part = 0


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
        out.score_wide += sum(
            1
            for (staff, _m), items in found.items()
            for e in items
            if staff == SCORE_WIDE_STAFF and e.score_wide
        )
        # The topmost part is the first in score order, which is the staff
        # layout order -- not the lowest staff number. `staff_order` puts them in
        # the order the document lays them out, and two corpus documents lay five
        # staves out as 1 2 5 3 4.
        top = score.parts[0].id if score.parts else None
        out.on_the_top_part += sum(
            1
            for part in score.parts
            if part.id == top
            for measure in part.measures
            for e in measure.expressions
            if e.score_wide
        )
        if placed == read:
            continue
        out.affected += 1
        staves = {
            int(part.id[1:])
            for part in score.parts
            if part.id.startswith("P") and part.id[1:].lstrip("-").isdigit()
        }
        for (staff, _measure), items in found.items():
            # A score-wide marking names staff -1 by design and is moved onto a
            # real part, so it is not a drop -- counting it as one is what made
            # an earlier reading of this sweep report 32 phantom losses.
            if staff != SCORE_WIDE_STAFF and staff not in staves:
                out.dropped_by_staff[staff] += len(items)
    return out


def test_the_sweep_reaches_the_whole_corpus(reading: _Reading) -> None:
    assert reading.documents >= 395, f"only {reading.documents} documents built"
    assert reading.read == READ, f"the reader now returns {reading.read}, not {READ}"


def test_the_gap_between_read_and_placed_is_exactly_what_is_documented(
    reading: _Reading,
) -> None:
    """Pinned in both directions.

    Larger means a new way of losing a marking. Smaller means the remaining cause
    has been fixed, and the constant here should record it rather than being
    quietly relaxed.
    """
    assert reading.placed == PLACED, f"{reading.placed} reach the IR, not {PLACED}"
    dropped = reading.read - reading.placed
    assert dropped == DROPPED_ON_A_SILENT_STAFF, (
        f"{dropped} expressions are dropped; the documented cause accounts for "
        f"{DROPPED_ON_A_SILENT_STAFF}"
    )


def test_the_only_remaining_cause_is_the_silent_staff(reading: _Reading) -> None:
    """One cause, and no score-wide marking among the losses -- those are placed
    now, and counting them as dropped is what made an earlier reading of this
    sweep report 32 phantom losses."""
    assert reading.dropped_by_staff[-1] == 0
    on_a_real_staff = sum(n for staff, n in reading.dropped_by_staff.items() if staff >= 0)
    assert on_a_real_staff == DROPPED_ON_A_SILENT_STAFF
    assert set(reading.dropped_by_staff) <= {1, 2, 3, 4, 5}, (
        "a staff number outside the documented range is losing markings"
    )


def test_every_score_wide_marking_lands_on_the_top_part(reading: _Reading) -> None:
    """The recovery, asserted where it is delivered rather than where it is read.

    Both halves matter: the reader must still find them, and `to_ir` must move
    every one onto a real part. If `_place_score_wide` stopped running, the second
    number would fall to zero while the first stayed put.
    """
    assert reading.score_wide == SCORE_WIDE, f"{reading.score_wide} read, not {SCORE_WIDE}"
    assert reading.on_the_top_part == SCORE_WIDE, (
        f"{reading.on_the_top_part} of {SCORE_WIDE} score-wide markings reached the top part"
    )


def test_most_expressions_do_reach_the_ir(reading: _Reading) -> None:
    """The gap is a known edge, not the common case: 96.9% arrive.

    Was 97.2%. It slipped because recovering the textless dynamics added 180 to
    the numerator's input and only 132 to the numerator -- 48 of them are
    assigned to a staff with no notes, so they join the one remaining cause. A
    ratio that falls while the absolute count rises is not a regression, which is
    why the exact counts above are the real guard and this is only a floor.
    """
    assert reading.placed / reading.read > 0.96
    assert reading.affected < reading.documents, "some document must place all of its markings"
