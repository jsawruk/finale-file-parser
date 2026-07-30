"""Tests for tuplet ratios and sounded durations."""

from __future__ import annotations

from fractions import Fraction

import pytest

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.tuplet import (
    EntryChain,
    Tuplet,
    sounded_durations,
)

EIGHTH = 512
QUARTER = 1024


def triplet(unit: int = EIGHTH) -> Tuplet:
    """Three in the time of two."""
    return Tuplet(
        symbolic_number=3, symbolic_duration=unit, reference_number=2, reference_duration=unit
    )


def test_triplet_ratio_and_span() -> None:
    tuplet = triplet()
    assert tuplet.ratio == Fraction(2, 3)
    assert tuplet.span == 3 * EIGHTH


def test_ratio_handles_differing_units() -> None:
    """Five sixteenths in the time of one eighth."""
    tuplet = Tuplet(
        symbolic_number=5, symbolic_duration=256, reference_number=1, reference_duration=EIGHTH
    )
    assert tuplet.ratio == Fraction(512, 1280) == Fraction(2, 5)


def test_untupleted_entries_keep_their_written_duration() -> None:
    chain = EntryChain(order=[1, 2], written_edu={1: QUARTER, 2: EIGHTH})
    assert sounded_durations(chain, {}) == {1: QUARTER, 2: EIGHTH}


def test_triplet_scales_exactly_its_span() -> None:
    """The tuplet covers three eighths; the fourth entry is outside it."""
    chain = EntryChain(
        order=[1, 2, 3, 4],
        written_edu={1: EIGHTH, 2: EIGHTH, 3: EIGHTH, 4: QUARTER},
    )
    got = sounded_durations(chain, {1: (triplet(),)})
    assert got[1] == got[2] == got[3] == Fraction(2 * EIGHTH, 3)
    assert sum([got[1], got[2], got[3]]) == 2 * EIGHTH, "a triplet must occupy two eighths"
    assert got[4] == QUARTER, "the entry after the tuplet must be unscaled"


def test_tuplet_span_is_measured_in_time_not_entries() -> None:
    """A triplet of unequal notes (quarter + two eighths) still spans three eighths.

    Retiring the tuplet after a fixed number of entries instead of by accumulated
    written time scales the wrong notes here.
    """
    chain = EntryChain(order=[1, 2, 3], written_edu={1: QUARTER, 2: EIGHTH, 3: QUARTER})
    got = sounded_durations(chain, {1: (triplet(),)})
    assert got[1] == Fraction(2 * QUARTER, 3)
    assert got[2] == Fraction(2 * EIGHTH, 3)
    assert got[3] == QUARTER, "the tuplet's span is used up before entry 3"


def test_entry_that_exhausts_the_span_is_still_scaled() -> None:
    """Off-by-one guard: retiring before scaling drops the last note of a tuplet."""
    chain = EntryChain(order=[1, 2], written_edu={1: EIGHTH, 2: 2 * EIGHTH})
    got = sounded_durations(chain, {1: (triplet(),)})
    assert got[2] == Fraction(2 * 2 * EIGHTH, 3), "the entry completing the span is inside it"


def test_nested_tuplets_multiply() -> None:
    chain = EntryChain(order=[1], written_edu={1: EIGHTH})
    got = sounded_durations(chain, {1: (triplet(), triplet())})
    assert got[1] == EIGHTH * Fraction(2, 3) * Fraction(2, 3)


def test_missing_written_duration_raises() -> None:
    chain = EntryChain(order=[1], written_edu={})
    with pytest.raises(CorruptScoreError, match="written duration"):
        sounded_durations(chain, {})


@pytest.mark.parametrize(
    "fields",
    [
        {"symbolicNum": "0", "symbolicDur": "512", "refNum": "2", "refDur": "512"},
        {"symbolicNum": "3", "symbolicDur": "512", "refNum": "2"},
        {"symbolicNum": "x", "symbolicDur": "512", "refNum": "2", "refDur": "512"},
    ],
)
def test_malformed_tuplet_definition_raises(fields: dict[str, str]) -> None:
    from finale_file_parser.enigma.document import Record
    from finale_file_parser.enigma.tuplet import read_tuplet

    record = Record(tag="tupletDef", attrs={"entnum": "1"}, text="", fields=fields)
    with pytest.raises(CorruptScoreError):
        read_tuplet(record)


def test_grace_notes_sound_for_no_time() -> None:
    """A grace note has a written duration but occupies no time.

    Treating one as ordinary overflows its measure: four grace notes push a 4/4
    measure to 6144 EDU against a capacity of 4096, which is exactly what was
    observed in the corpus before this was handled.
    """
    chain = EntryChain(
        order=[1, 2],
        written_edu={1: EIGHTH, 2: QUARTER},
        grace_notes=frozenset({1}),
    )
    got = sounded_durations(chain, {})
    assert got[1] == 0
    assert got[2] == QUARTER


def test_grace_notes_do_not_consume_a_tuplet_span() -> None:
    """A grace note inside a triplet must not eat part of its span."""
    chain = EntryChain(
        order=[1, 2, 3, 4],
        written_edu={1: EIGHTH, 2: EIGHTH, 3: EIGHTH, 4: EIGHTH},
        grace_notes=frozenset({1}),
    )
    got = sounded_durations(chain, {2: (triplet(),)})
    assert got[1] == 0
    assert got[2] == got[3] == got[4] == Fraction(2 * EIGHTH, 3)


def test_a_linked_part_tuplet_override_is_not_read_as_a_tuplet() -> None:
    """A part variant carries only what it overrides.

    All 12 in the corpus are `shared="true"` and hold bracket-hook geometry and
    nothing else -- no `symbolicNum`, because the score record has it. Reading one
    as a tuplet definition raised, which cost three documents; reading one that
    *did* carry a ratio would be worse, since an entry's tuplets are a tuple and
    the override would arrive as a second, nested tuplet.
    """
    from finale_file_parser.enigma.document import DetailsPool, EnigmaDocument, Pool, Record
    from finale_file_parser.enigma.tuplet import tuplets_by_entry

    score = Record(
        tag="tupletDef",
        attrs={"entnum": "1", "inci": "0"},
        text="",
        fields={"symbolicNum": "3", "symbolicDur": "512", "refNum": "2", "refDur": "512"},
    )
    override = Record(
        tag="tupletDef",
        attrs={"entnum": "1", "inci": "0", "part": "2", "shared": "true"},
        text="",
        fields={"leftHookLen": "-18", "rightHookLen": "-18"},
    )
    empty: tuple[Record, ...] = ()
    document = EnigmaDocument(
        version="test",
        header=Pool(records=empty),
        mappings=Pool(records=empty),
        options=Pool(records=empty),  # type: ignore[arg-type]
        others=Pool(records=empty),  # type: ignore[arg-type]
        details=DetailsPool(records=(score, override)),
        entries=Pool(records=empty),  # type: ignore[arg-type]
        texts=Pool(records=empty),  # type: ignore[arg-type]
    )
    by_entry = tuplets_by_entry(document)
    assert len(by_entry[1]) == 1
    assert by_entry[1][0].symbolic_number == 3
