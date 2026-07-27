"""Unit tests for articulation resolution.

An articulation's identity is a music-font character, so these tests build the
`articAssign` -> `articDef` -> `charMain` chain and check what comes out. The
part worth guarding is what happens to characters the table does not know:
nothing, rather than a guess.
"""

from __future__ import annotations

import pytest

from finale_file_parser.enigma.articulations import (
    ARTICULATION_CHARACTERS,
    articulations_by_entry,
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
    ("character", "name"),
    [(46, "staccato"), (62, "accent"), (45, "tenuto"), (94, "strong-accent"), (44, "breath-mark")],
)
def test_each_known_character_resolves(character: int, name: str) -> None:
    doc = document(definitions={1: character}, assignments=((7, 1),))
    assert articulations_by_entry(doc) == {7: (name,)}


def test_an_unknown_character_produces_nothing() -> None:
    """The corpus assigns 29 distinct characters and the table knows five. A
    guess would print the wrong mark on a real note, which is worse than a bare
    one."""
    doc = document(definitions={1: 217}, assignments=((7, 1),))
    assert articulations_by_entry(doc) == {}


def test_an_entry_can_carry_several_marks() -> None:
    doc = document(definitions={1: 46, 2: 62}, assignments=((7, 1), (7, 2)))
    assert articulations_by_entry(doc) == {7: ("staccato", "accent")}


def test_an_assignment_naming_a_missing_definition_is_dropped() -> None:
    doc = document(definitions={}, assignments=((7, 3),))
    assert articulations_by_entry(doc) == {}


def test_a_part_variant_definition_is_ignored() -> None:
    """Score records only, as everywhere else -- a part override would shadow
    the score's definition."""
    variant = Record(
        tag="articDef",
        attrs={"cmper": "1", "part": "1"},
        text="",
        fields={"charMain": "62"},
    )
    doc = document(definitions={1: 46}, assignments=((7, 1),))
    doc.others = OthersPool(records=(*doc.others.records, variant))
    assert articulations_by_entry(doc) == {7: ("staccato",)}


def test_the_table_covers_only_characters_with_evidence() -> None:
    """A regression guard on scope: the table is deliberately small, and
    growing it should be a deliberate act with evidence attached."""
    assert set(ARTICULATION_CHARACTERS) == {44, 45, 46, 62, 94}
