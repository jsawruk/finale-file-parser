"""Tests for time signatures."""

from __future__ import annotations

import pytest

from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.timesig import (
    TimeSignature,
    display_time_signature,
    read_time_signature,
)

QUARTER, EIGHTH, HALF = 1024, 512, 2048
DOTTED_QUARTER = 1536


def _spec(**fields: str) -> Record:
    return Record(tag="measSpec", attrs={"cmper": "1"}, text="", fields=fields)


@pytest.mark.parametrize(
    ("beats", "division", "expected"),
    [
        (4, QUARTER, "4/4"),
        (3, QUARTER, "3/4"),
        (2, HALF, "2/2"),
        (1, EIGHTH, "1/8"),
        (2, DOTTED_QUARTER, "6/8"),
        (3, DOTTED_QUARTER, "9/8"),
        (1, DOTTED_QUARTER, "3/8"),
    ],
)
def test_conventional_notation(beats: int, division: int, expected: str) -> None:
    """Enigma stores divisions, not a numerator over a denominator.

    Compound meters are the reason: 6/8 is stored as two dotted-quarter divisions,
    so reporting `beats` as the numerator would call it 2/8.
    """
    assert str(TimeSignature(beats=beats, division_edu=division)) == expected


@pytest.mark.parametrize(
    ("division", "compound"),
    [(QUARTER, False), (HALF, False), (EIGHTH, False), (DOTTED_QUARTER, True), (3072, True)],
)
def test_compound_detection(division: int, compound: bool) -> None:
    assert TimeSignature(beats=2, division_edu=division).is_compound is compound


def test_total_edu() -> None:
    assert TimeSignature(beats=4, division_edu=QUARTER).total_edu == 4096
    assert TimeSignature(beats=2, division_edu=DOTTED_QUARTER).total_edu == 3072


def test_reads_a_measure_spec() -> None:
    signature = read_time_signature(_spec(beats="6", divbeat="512"))
    assert signature == TimeSignature(beats=6, division_edu=512)


@pytest.mark.parametrize(
    "fields",
    [
        {"divbeat": "1024"},
        {"beats": "4"},
        {"beats": "0", "divbeat": "1024"},
        {"beats": "4", "divbeat": "-1"},
        {"beats": "x", "divbeat": "1024"},
    ],
)
def test_malformed_measure_spec_raises(fields: dict[str, str]) -> None:
    with pytest.raises(CorruptScoreError):
        read_time_signature(_spec(**fields))


def test_undividable_division_raises() -> None:
    """A division that is not a notatable note value has no denominator."""
    with pytest.raises(CorruptScoreError, match="notatable"):
        _ = TimeSignature(beats=1, division_edu=1000).denominator


def test_display_signature_is_none_without_the_flag() -> None:
    """`dispBeats`/`dispDivbeat` are present on every measure but hold a default.

    Reading them unconditionally reports a display signature for 1,937 of 2,622
    corpus measures that do not have one -- usually claiming 4/4 over a 3/4 bar.
    """
    spec = _spec(beats="3", divbeat="1024", dispBeats="4", dispDivbeat="1024")
    assert display_time_signature(spec) is None


def test_display_signature_is_read_when_flagged() -> None:
    spec = _spec(beats="3", divbeat="1024", dispBeats="4", dispDivbeat="1024", useDisplayTimesig="")
    assert display_time_signature(spec) == TimeSignature(beats=4, division_edu=1024)
