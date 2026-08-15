"""Expressions read from a `.mus`, checked against the `.musx` holding the same music.

The oracle is what makes this more than a self-consistent read: for 91 documents
the corpus has both containers, so the markings can be compared triple by triple.
They agree on 1,464 of 1,476 `(staff, measure, marking)` triples.

Report counts only -- never a corpus filename, title, or lyric.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from corpus_files import corpus_paths, oracle_pairs

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.expressions import expressions_by_measure
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.errors import FinaleFileError

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

PLACED = 2974
"""Markings read from the `.mus` corpus.

Was 3,136 before shape assignments were excluded: 114 of those were a
`shapeExprID` read as if it named an expression. See
`mus_others.TAG_MEAS_EXPR_ASSIGN`.

Then 3,022, before the reader began dropping a score-wide copy of a marking the
same measure already places on a real staff. The 48 fewer are that, in this
container.
"""

DOCUMENTS = 186
"""`.mus` documents carrying at least one. All are 2011-era; a 2001-2005 document
carries none, because `^DY` is not decoded -- see `mus_document.UNTRANSLATED`."""

AGREE = 1441
"""`(staff, measure, marking)` triples both containers place.

Was 1,464. The 23 fewer are not a loss of agreement: a score-wide marking is
keyed on staff -1 here, so a redundant copy formed its own `(-1, measure,
marking)` triple that both containers agreed on. Dropping the redundancy removed
those from both sides at once, and `DISAGREE` did not move.
"""

DISAGREE = 12
"""Triples one places and the other does not, out of 1,453.

Unchanged when the score-wide redundancy was dropped, which is the check that
matters: that change removed 23 agreeing triples and no disagreeing ones, so it
cost nothing in cross-container fidelity.

Was 52 before the shape flag. The remainder are markings the `.mus` path misses,
not spurious ones it invents -- `test_the_disagreement_is_not_the_mus_path
_inventing_markings` asserts that direction, which is the one that matters: a
missing dynamic is a gap, an invented one is wrong output.
"""


class _Reading:
    def __init__(self) -> None:
        self.placed = 0
        self.documents = 0
        self.markings: Counter[str] = Counter()
        self.categories: Counter[str] = Counter()
        self.layers: Counter[str] = Counter()
        self.read = 0


@pytest.fixture(scope="module")
def reading() -> _Reading:
    out = _Reading()
    for path in corpus_paths(".mus") + corpus_paths(".MUS"):
        try:
            document = read_mus_document(path)
        except (CorruptScoreError, OSError, ValueError, KeyError):
            continue
        out.read += 1
        found = expressions_by_measure(document)
        placed = sum(len(items) for items in found.values())
        out.placed += placed
        out.documents += placed > 0
        for items in found.values():
            for expression in items:
                out.markings[expression.marking or ""] += 1
                out.categories[expression.category] += 1
                out.layers[str(expression.layer)] += 1
    return out


@pytest.fixture(scope="module")
def compared() -> tuple[int, int, Counter[str]]:
    """Agreements, disagreements, and which side each disagreement came from."""
    agree = disagree = 0
    sides: Counter[str] = Counter()
    for mus, musx in oracle_pairs():
        try:
            here = expressions_by_measure(read_mus_document(mus))
            there = expressions_by_measure(parse_enigma(score_xml(musx)))
        except (CorruptScoreError, FinaleFileError, OSError, ValueError, KeyError):
            continue
        if not here and not there:
            continue
        ours = {(s, m, e.marking) for (s, m), items in here.items() for e in items}
        theirs = {(s, m, e.marking) for (s, m), items in there.items() for e in items}
        agree += len(ours & theirs)
        disagree += len(ours ^ theirs)
        sides["only in the .mus"] += len(ours - theirs)
        sides["only in the .musx"] += len(theirs - ours)
    return agree, disagree, sides


def test_the_mus_corpus_yields_the_expressions_it_did(reading: _Reading) -> None:
    """Pinned so a sweep that quietly stops early fails rather than passes."""
    assert reading.read >= 450, f"only {reading.read} documents read"
    assert reading.placed == PLACED, f"{reading.placed} markings placed, not {PLACED}"
    assert reading.documents == DOCUMENTS


def test_the_dynamics_are_named_from_the_description(reading: _Reading) -> None:
    """A `.mus` has no `^fontMus` markup and no decoded category, so `descStr` is
    the only signal -- and it is enough for every graded dynamic the corpus uses.
    """
    for marking in ("p", "mf", "mp", "f", "ff", "pp", "ppp"):
        assert reading.markings[marking] > 0, f"{marking} is never named in a .mus"
    assert reading.markings["p"] > 500
    assert reading.markings[""] > 0, "unnamed markings exist too -- tempo and technique words"


def test_a_mus_expression_reports_no_category_and_no_layer(reading: _Reading) -> None:
    """Neither is identified in the 241 record, so neither is invented. Absent is
    the honest answer and this pins it: if a future decode fills them in, this
    fails and says so."""
    assert set(reading.categories) == {""}
    assert set(reading.layers) == {"None"}


def test_the_two_containers_agree(compared: tuple[int, int, Counter[str]]) -> None:
    agree, disagree, _sides = compared
    assert agree == AGREE, f"{agree} triples agree, not {AGREE}"
    assert disagree == DISAGREE, f"{disagree} disagree, not {DISAGREE}"
    assert agree / (agree + disagree) > 0.99


def test_the_disagreement_is_not_the_mus_path_inventing_markings(
    compared: tuple[int, int, Counter[str]],
) -> None:
    """The direction that matters.

    A marking the `.mus` places and the `.musx` does not is wrong output -- a
    dynamic in a score that has none there. One the `.musx` places and the `.mus`
    misses is only a gap. Before the shape flag at `+11` was found, 44 of the 52
    disagreements were the wrong direction; that is what the flag fixed, and this
    keeps it fixed.
    """
    _agree, _disagree, sides = compared
    assert sides["only in the .mus"] <= 5, (
        f"the .mus path places {sides['only in the .mus']} markings the .musx does not"
    )
