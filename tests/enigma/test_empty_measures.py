"""Unit tests for the measures a part rests through.

`build_score` used to make a measure only where a staff had entries, so a part
silent through a bar simply skipped it and its measure numbering jumped. These
cover the three pieces that fixes: the rest itself, the clef that has to survive
the silence, and the measure list the part is measured against.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
)
from finale_file_parser.enigma.repeats import Repeats
from finale_file_parser.enigma.timesig import TimeSignature as EnigmaTimeSignature
from finale_file_parser.enigma.to_ir import (
    _carried_clefs,
    _Cell,
    _measure,
    _measure_numbers,
    _measure_rest,
)

EMPTY: tuple[Record, ...] = ()
QUARTER_EDU = 1024


def document(*others: Record) -> EnigmaDocument:
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=others),
        details=DetailsPool(records=EMPTY),
        entries=EntriesPool(records=EMPTY),
        texts=TextsPool(records=EMPTY),
    )


def cell() -> _Cell:
    return _Cell(events_by_layer={}, key_raw=0)


def staff_spec(number: int, default_clef: int) -> Record:
    return Record(
        tag="staffSpec",
        attrs={"cmper": str(number)},
        text="",
        fields={"defaultClef": str(default_clef)},
    )


@pytest.mark.parametrize(
    ("beats", "division", "expected"),
    [(4, QUARTER_EDU, Fraction(1)), (3, QUARTER_EDU, Fraction(3, 4)), (2, 1536, Fraction(3, 4))],
)
def test_a_measure_rest_lasts_as_long_as_the_measure(
    beats: int, division: int, expected: Fraction
) -> None:
    """Not a whole note: a 3/4 measure rest is 3/4 long. Writing a whole note
    instead overfills every bar that is not 4/4, and 6/8 (2 x 1536 EDU) is the
    case that catches a naive beats/4."""
    rest = _measure_rest(EnigmaTimeSignature(beats=beats, division_edu=division))
    assert rest.duration == expected
    assert rest.is_measure_rest
    assert rest.is_rest


def test_a_measure_rest_without_a_time_signature_falls_back_to_a_whole() -> None:
    assert _measure_rest(None).duration == Fraction(1)


def test_a_silent_measure_still_becomes_a_measure() -> None:
    """The whole point: a part with nothing in bar 2 still has bar 2. A reader
    meeting a gap in the numbering cannot tell a silent bar from a lost one."""
    measure = _measure(
        staff=1,
        number=2,
        previous=1,
        cells={},
        keys={1: 0, 2: 0},
        signatures={2: EnigmaTimeSignature(beats=4, division_edu=QUARTER_EDU)},
        clef_table={},
        clef_at={},
        repeats=Repeats(by_measure={}),
    )
    assert measure.number == 2
    assert [voice.number for voice in measure.voices] == [1]
    events = measure.voices[0].events
    assert len(events) == 1
    assert events[0].is_measure_rest
    assert events[0].duration == Fraction(1)


def test_a_silent_measure_knows_its_key() -> None:
    """The key belongs to the measure, not to the staff's notes, so a part that
    is resting is still in the right key -- and a part silent through the
    opening bars must not report C major there."""
    measure = _measure(
        staff=1,
        number=1,
        previous=None,
        cells={},
        keys={1: 3},
        signatures={},
        clef_table={},
        clef_at={},
        repeats=Repeats(by_measure={}),
    )
    assert measure.key_fifths == 3


def test_a_clef_survives_a_silence() -> None:
    """`gfhold` is where clefs live, and a measure a staff rests through has no
    `gfhold` at all. Without carrying it forward the part loses its clef the
    moment it falls silent and re-announces it on returning."""
    clef_at = {(1, 1): 4, (1, 5): 4}
    carried = _carried_clefs(document(staff_spec(1, 0)), [1], [1, 2, 3, 4, 5], clef_at)
    assert [carried[(1, n)] for n in range(1, 6)] == [4, 4, 4, 4, 4]


def test_the_staff_default_applies_before_the_first_gfhold() -> None:
    """A part that does not play until bar 3 still needs a clef in bar 1."""
    carried = _carried_clefs(document(staff_spec(1, 7)), [1], [1, 2, 3], {(1, 3): 7})
    assert carried[(1, 1)] == 7


def test_a_real_clef_change_still_registers() -> None:
    carried = _carried_clefs(document(staff_spec(1, 0)), [1], [1, 2, 3], {(1, 1): 0, (1, 3): 4})
    assert [carried[(1, n)] for n in (1, 2, 3)] == [0, 0, 4]


def test_the_measure_list_comes_from_the_document_not_from_the_music() -> None:
    """A bar the whole ensemble rests through is still a bar. Taking the
    measures that hold entries drops 1,375 of them across the corpus, and the
    parts then start at 3 with no way to tell that 1 and 2 existed."""
    keys = {1: 0, 2: 0, 3: 0, 4: 0}
    assert _measure_numbers(keys, {(1, 3): cell(), (1, 4): cell()}) == [1, 2, 3, 4]


def test_a_document_with_no_measure_records_falls_back_to_the_music() -> None:
    """A malformed file still exports what it has."""
    assert _measure_numbers({}, {(1, 2): cell(), (1, 5): cell()}) == [2, 5]
