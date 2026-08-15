"""The expressions the corpus actually places, read back out of it.

The shape of the result is the evidence that a library was not mistaken for a
score. A palette read by accident gives a flat count -- roughly one of every
entry per document. Real usage is steeply uneven: `f` and `mf` many times over,
`ffff` a handful of times in four hundred documents.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.expressions import expressions_by_measure
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.formats.dynamics import GRADED_DYNAMICS

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


class _Reading:
    def __init__(self) -> None:
        self.markings: Counter[str] = Counter()
        self.categories: Counter[str] = Counter()
        self.total = 0
        self.documents = 0
        self.documents_with_a_dynamic = 0
        self.empty_text = 0
        self.staves: set[int] = set()
        self.layers: Counter[str] = Counter()
        self.rehearsal = 0
        self.rehearsal_documents = 0
        self.rehearsal_labels: set[str] = set()


@pytest.fixture(scope="module")
def reading() -> _Reading:
    out = _Reading()
    for path in sorted(CORPUS.rglob("*.musx")):
        try:
            document = parse_enigma(score_xml(path))
        except (FinaleFileError, OSError):
            continue
        out.documents += 1
        found = expressions_by_measure(document)
        has_dynamic = False
        marks_here = 0
        for (staff, _measure), items in found.items():
            for expression in items:
                out.total += 1
                out.categories[expression.category] += 1
                out.staves.add(staff)
                out.layers[str(expression.layer)] += 1
                if not expression.text:
                    out.empty_text += 1
                if expression.is_rehearsal:
                    marks_here += 1
                    out.rehearsal_labels.add(expression.text)
                if expression.marking:
                    out.markings[expression.marking] += 1
                    has_dynamic = True
        out.documents_with_a_dynamic += has_dynamic
        out.rehearsal += marks_here
        out.rehearsal_documents += marks_here > 0
    return out


def test_the_sweep_reaches_the_whole_corpus(reading: _Reading) -> None:
    """Pinned so a sweep that quietly stops early fails rather than passes."""
    assert reading.documents >= 395, f"only {reading.documents} documents parsed"
    assert reading.total >= 11000, f"only {reading.total} expressions placed"
    assert reading.documents_with_a_dynamic >= 300


def test_nothing_placed_has_empty_text(reading: _Reading) -> None:
    """An expression with nothing to print is dropped at the reader, so none
    should survive to here -- otherwise a consumer prints a blank direction."""
    assert reading.empty_text == 0


def test_the_distribution_is_a_score_not_a_library(reading: _Reading) -> None:
    """The check that catches the classic error in this format.

    Every document ships all sixteen dynamics. Had the definitions been read
    instead of the assignments, each would appear about as often as every other
    and roughly once per document. Real music is nothing like that: the middle
    of the range dominates and the extremes are rare.
    """
    counts = reading.markings
    assert counts["f"] > counts["ff"] > counts["ffff"]
    assert counts["p"] > counts["pp"] > counts["pppp"]
    assert counts["mf"] > counts["fff"]
    # A palette would give ~1 per document per entry; f alone beats that many
    # times over, and ffff falls far below it.
    assert counts["f"] > reading.documents
    assert counts["ffff"] < reading.documents // 4


def test_the_common_dynamics_are_all_used_somewhere(reading: _Reading) -> None:
    """Every rung of the ladder from ffff to pppp is placed by some document,
    which is what makes the naming testable end to end."""
    for entry in GRADED_DYNAMICS:
        assert entry.marking is not None
        assert reading.markings[entry.marking] > 0, f"{entry.marking} is never placed"


def test_the_categories_are_the_documents_own_words(reading: _Reading) -> None:
    """Read from `markingsCategory`, never inferred from the marking."""
    assert set(reading.categories) <= {
        "dynamics",
        "tempoMarks",
        "tempoAlts",
        "expressiveText",
        "techniqueText",
        "rehearsalMarks",
        "misc",
        "",
    }
    assert reading.categories["dynamics"] > 5000


def test_expressions_land_on_more_than_one_staff(reading: _Reading) -> None:
    """The reason this is keyed by staff rather than measure: parts differ."""
    assert len(reading.staves) > 8


def test_most_markings_name_a_layer_and_many_do_not(reading: _Reading) -> None:
    """Both cases are real, so both must survive the read: a marking attached to
    layer 1, and one attached to the staff with no layer at all."""
    assert reading.layers["1"] > 1000
    assert reading.layers["None"] > 500


REHEARSAL_MARKS = 90
"""Rehearsal marks the corpus places, of 113 assignments carrying `^rehearsal()`.

The other 23 are accounted for: 21 are a score-wide copy of a mark the same
measure already places on a real staff, and 2 carry no readable
`rehearsalMarkStyle` and so have no label to print.
"""

REHEARSAL_DOCUMENTS = 10


def test_rehearsal_marks_are_labelled_from_the_style_the_file_gives(
    reading: _Reading,
) -> None:
    """The label is not in the file -- the text is the bare `^rehearsal()` insert
    and `plain_text` correctly yields nothing, which is why all 113 were dropped
    before this existed.

    `rehearsalMarkStyle` says how to work it out, and for `measNum` -- 99 of the
    113 -- the answer is the measure number, so no convention is involved. Only
    the `letters` marks are numbered by position, and this asserts both kinds
    actually appear, so a change that silently reduced the feature to one style
    would fail.
    """
    assert reading.rehearsal == REHEARSAL_MARKS
    assert reading.rehearsal_documents == REHEARSAL_DOCUMENTS
    numeric = {label for label in reading.rehearsal_labels if label.isdigit()}
    lettered = {label for label in reading.rehearsal_labels if not label.isdigit()}
    assert numeric, "no measure-number rehearsal mark reached the sweep"
    assert lettered >= {"A", "B", "C"}, f"the letter sequence is missing: {sorted(lettered)}"


def test_a_rehearsal_mark_always_carries_a_label(reading: _Reading) -> None:
    """`<rehearsal>` with no text is not a rehearsal mark. A mark whose style is
    unreadable is dropped at the reader rather than emitted empty."""
    assert "" not in reading.rehearsal_labels
