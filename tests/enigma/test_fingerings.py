"""Unit tests for fingerings.

Finale has no fingering object -- a fingering is an articulation whose character
is a numeral -- so the tests that matter are about the boundary between the two:
what counts as a numeral, and what the articulation reader must not claim.
"""

from __future__ import annotations

import pytest

from finale_file_parser.enigma.articulations import ARTICULATION_CHARACTERS
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
from finale_file_parser.enigma.fingerings import FINGERING_CHARACTERS, fingerings_by_entry

EMPTY: tuple[Record, ...] = ()


def document(
    *, definitions: dict[int, int], assignments: tuple[tuple[int, int], ...]
) -> EnigmaDocument:
    others = tuple(
        Record(
            tag="articDef",
            attrs={"cmper": str(cmper)},
            text="",
            fields={"charMain": str(character)},
        )
        for cmper, character in definitions.items()
    )
    details = tuple(
        Record(
            tag="articAssign",
            attrs={"entnum": str(entnum), "inci": str(index)},
            text="",
            fields={"articDef": str(definition)},
        )
        for index, (entnum, definition) in enumerate(assignments)
    )
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=others),
        details=DetailsPool(records=details),
        entries=EntriesPool(records=EMPTY),
        texts=TextsPool(records=EMPTY),
    )


@pytest.mark.parametrize(
    ("character", "digit"), [(49, "1"), (50, "2"), (51, "3"), (52, "4"), (53, "5")]
)
def test_each_numeral_resolves_to_its_digit(character: int, digit: str) -> None:
    doc = document(definitions={1: character}, assignments=((7, 1),))
    assert fingerings_by_entry(doc) == {7: (digit,)}


def test_zero_is_not_a_fingering() -> None:
    """Three corpus definitions carry `0` and none is ever assigned, so nothing
    says whether it means an open string or an unused slot."""
    doc = document(definitions={1: 48}, assignments=((7, 1),))
    assert fingerings_by_entry(doc) == {}


def test_an_articulation_character_is_not_a_fingering() -> None:
    doc = document(definitions={1: 46}, assignments=((7, 1),))
    assert fingerings_by_entry(doc) == {}


def test_the_two_tables_do_not_overlap() -> None:
    """A character claimed by both readers would be printed twice, once as an
    articulation and once as a fingering."""
    assert not set(FINGERING_CHARACTERS) & set(ARTICULATION_CHARACTERS)


def test_a_chord_can_carry_several_fingerings() -> None:
    doc = document(definitions={1: 49, 2: 51}, assignments=((7, 1), (7, 2)))
    assert fingerings_by_entry(doc) == {7: ("1", "3")}


def test_a_repeated_assignment_is_counted_once() -> None:
    """A `.mus` restates an assignment; printing it twice puts two 3s on one
    note."""
    doc = document(definitions={1: 51}, assignments=((7, 1), (7, 1)))
    assert fingerings_by_entry(doc) == {7: ("3",)}


def test_an_assignment_naming_a_missing_definition_is_dropped() -> None:
    assert fingerings_by_entry(document(definitions={}, assignments=((7, 3),))) == {}


def test_a_part_variant_definition_is_ignored() -> None:
    variant = Record(
        tag="articDef", attrs={"cmper": "1", "part": "1"}, text="", fields={"charMain": "49"}
    )
    doc = document(definitions={1: 46}, assignments=((7, 1),))
    doc.others = OthersPool(records=(*doc.others.records, variant))
    assert fingerings_by_entry(doc) == {}
