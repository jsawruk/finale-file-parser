"""Tests for clefs."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from finale_file_parser.enigma.clef import (
    Clef,
    ClefSign,
    clef_definitions,
    clefs_by_measure,
    default_clefs,
)
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
from finale_file_parser.enigma.models import CorruptScoreError

TREBLE_CHAR, BASS_CHAR, C_CHAR = 38, 63, 66


def _clef(
    *,
    clef_char: int | None = None,
    adjust: int = 0,
    y_displacement: int = 0,
    shape_id: int | None = None,
) -> Clef:
    return Clef(
        index=0,
        clef_char=clef_char,
        adjust=adjust,
        y_displacement=y_displacement,
        shape_id=shape_id,
    )


@pytest.mark.parametrize(
    ("char", "sign"),
    [
        (TREBLE_CHAR, ClefSign.G),
        (BASS_CHAR, ClefSign.F),
        (C_CHAR, ClefSign.C),
        (999, ClefSign.UNKNOWN),
        (None, ClefSign.UNKNOWN),
    ],
)
def test_sign_from_character(char: int | None, sign: ClefSign) -> None:
    """An unrecognised character must stay UNKNOWN rather than defaulting.

    Guessing would silently mis-notate a staff; the corpus only confirms 38 and 63.
    """
    assert _clef(clef_char=char).sign is sign


def test_shape_clef_reports_shape_not_its_character() -> None:
    """A shape clef has no character; index 16 in the corpus is one."""
    clef = _clef(clef_char=None, shape_id=2)
    assert clef.is_shape
    assert clef.sign is ClefSign.SHAPE


def _document(
    *,
    options: Sequence[Record] = (),
    others: Sequence[Record] = (),
    details: Sequence[Record] = (),
) -> EnigmaDocument:
    return EnigmaDocument(
        version="18.0",
        header=Pool(records=()),
        mappings=Pool(records=()),
        options=OptionsPool(records=tuple(options)),
        others=OthersPool(records=tuple(others)),
        details=DetailsPool(records=tuple(details)),
        entries=EntriesPool(records=()),
        texts=TextsPool(records=()),
    )


def _clef_options(*defs: dict[str, str]) -> Record:
    children = tuple(Record(tag="clefDef", attrs={}, text="", fields=d) for d in defs)
    return Record(tag="clefOptions", attrs={}, text="", fields={"clefDef": children})


def test_reads_the_definition_table() -> None:
    document = _document(
        options=[
            _clef_options(
                {"clefChar": "38", "adjust": "-10", "clefYDisp": "-6"},
                {"adjust": "-10", "shapeID": "2"},
            )
        ]
    )
    table = clef_definitions(document)
    assert table[0] == Clef(index=0, clef_char=38, adjust=-10, y_displacement=-6, shape_id=None)
    assert table[1].is_shape and table[1].sign is ClefSign.SHAPE


def test_no_clef_options_yields_an_empty_table() -> None:
    assert clef_definitions(_document()) == {}


def test_absent_default_clef_means_treble_not_missing() -> None:
    """`defaultClef` is omitted when it is 0.

    Skipping staves without the field would drop every treble-clef staff.
    """
    staff = Record(tag="staffSpec", attrs={"cmper": "1"}, text="", fields={"staffLines": "5"})
    assert default_clefs(_document(others=[staff])) == {1: 0}


def test_clefs_by_measure_uses_the_gfhold_clef() -> None:
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "2", "cmper2": "7"}, text="", fields={"clefID": "3"}
    )
    assert clefs_by_measure(_document(details=[gfhold])) == {(2, 7): 3}


def test_gfhold_without_a_clef_falls_back_to_the_staff_default() -> None:
    """Every corpus gfhold carries clefID, but a caller must never get "no clef"."""
    staff = Record(tag="staffSpec", attrs={"cmper": "2"}, text="", fields={"defaultClef": "16"})
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "2", "cmper2": "7"}, text="", fields={"frame1": "1"}
    )
    assert clefs_by_measure(_document(others=[staff], details=[gfhold])) == {(2, 7): 16}


def test_non_numeric_definition_field_raises() -> None:
    document = _document(options=[_clef_options({"clefChar": "treble"})])
    with pytest.raises(CorruptScoreError, match="not an integer"):
        clef_definitions(document)
