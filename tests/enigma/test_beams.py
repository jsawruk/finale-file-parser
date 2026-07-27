"""Unit tests for beam grouping.

The module is pure -- durations and one bit in, beams out -- so these tests are
written as small musical situations rather than as documents. The cases that
matter are the ones the corpus is thin on: hooks, and groups that change
duration partway through.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from finale_file_parser.enigma.beams import BeamedNote, beams_for
from finale_file_parser.ir import Beam

EIGHTH = Fraction(1, 8)
SIXTEENTH = Fraction(1, 16)
DOTTED_EIGHTH = Fraction(3, 16)
QUARTER = Fraction(1, 4)


def note(
    duration: Fraction, *, dots: int = 0, rest: bool = False, starts: bool = False
) -> BeamedNote:
    return BeamedNote(written_duration=duration, dots=dots, is_rest=rest, starts_group=starts)


def types(result: list[tuple[Beam, ...]], level: int = 1) -> list[str | None]:
    return [next((b.type for b in beams if b.number == level), None) for beams in result]


def test_a_run_of_eighths_beams_begin_continue_end() -> None:
    result = beams_for([note(EIGHTH, starts=True)] + [note(EIGHTH) for _ in range(3)])
    assert types(result) == ["begin", "continue", "continue", "end"]


def test_the_beam_bit_starts_a_new_group() -> None:
    """Eight eighths flagged on the first and fifth are two groups of four --
    the pattern the corpus shows."""
    notes = [note(EIGHTH, starts=(index in (0, 4))) for index in range(8)]
    assert types(beams_for(notes)) == [
        "begin",
        "continue",
        "continue",
        "end",
        "begin",
        "continue",
        "continue",
        "end",
    ]


def test_a_lone_eighth_carries_no_beam() -> None:
    """One note is written with a flag, not a beam."""
    assert beams_for([note(EIGHTH, starts=True)]) == [()]


def test_an_unbeamable_note_breaks_the_group() -> None:
    notes = [note(EIGHTH, starts=True), note(QUARTER), note(EIGHTH), note(EIGHTH)]
    assert types(beams_for(notes)) == [None, None, "begin", "end"]


def test_a_rest_breaks_the_group() -> None:
    notes = [note(EIGHTH, starts=True), note(EIGHTH, rest=True), note(EIGHTH), note(EIGHTH)]
    assert types(beams_for(notes)) == [None, None, "begin", "end"]


def test_sixteenths_carry_a_second_beam() -> None:
    notes = [note(SIXTEENTH, starts=True)] + [note(SIXTEENTH) for _ in range(3)]
    result = beams_for(notes)
    assert types(result, 1) == ["begin", "continue", "continue", "end"]
    assert types(result, 2) == ["begin", "continue", "continue", "end"]


def test_a_dotted_eighth_still_beams_once() -> None:
    """Dots do not add beams: 3/16 is written as an eighth and beams like one."""
    result = beams_for([note(DOTTED_EIGHTH, dots=1, starts=True), note(SIXTEENTH)])
    assert types(result, 1) == ["begin", "end"]
    assert types(result, 2) == [None, "backward hook"]


def test_a_sixteenth_opening_a_group_hooks_forward() -> None:
    """The hook points at the note it belongs with, which for the first note of
    a group is the one after it."""
    result = beams_for([note(SIXTEENTH, starts=True), note(DOTTED_EIGHTH, dots=1)])
    assert types(result, 2) == ["forward hook", None]


def test_a_secondary_run_beams_rather_than_hooks() -> None:
    """Two adjacent sixteenths inside an eighth-note group get a real second
    beam, not two hooks."""
    notes = [note(EIGHTH, starts=True), note(SIXTEENTH), note(SIXTEENTH), note(EIGHTH)]
    assert types(beams_for(notes), 2) == [None, "begin", "end", None]


@pytest.mark.parametrize(
    ("duration", "dots", "expected"),
    [(EIGHTH, 0, 1), (SIXTEENTH, 0, 2), (Fraction(1, 32), 0, 3), (DOTTED_EIGHTH, 1, 1)],
)
def test_beam_count_follows_the_note_value(duration: Fraction, dots: int, expected: int) -> None:
    notes = [note(duration, dots=dots, starts=True), note(duration, dots=dots)]
    assert len(beams_for(notes)[0]) == expected


def test_every_level_that_begins_also_ends() -> None:
    """An unbalanced level would render as a beam running off the group."""
    notes = [
        note(EIGHTH, starts=True),
        note(SIXTEENTH),
        note(SIXTEENTH),
        note(Fraction(1, 32)),
        note(Fraction(1, 32)),
        note(EIGHTH),
    ]
    for beams in (beams_for(notes),):
        for level in (1, 2, 3):
            kinds = [t for t in types(beams, level) if t]
            assert kinds.count("begin") == kinds.count("end")
