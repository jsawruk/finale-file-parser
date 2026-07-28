"""Unit tests for text repeats.

The case that matters most is the one the corpus makes easy to get wrong: every
document carries a full palette of definitions, and only an assignment puts a
marking in the music. A reader that trusts the palette prints a D.S. in every
score there is.
"""

from __future__ import annotations

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
from finale_file_parser.enigma.jumps import jumps_by_measure

EMPTY: tuple[Record, ...] = ()

PALETTE = ("D.C. al Fine", "D.S. al Coda", "Fine", "To Coda #")
"""What every corpus document carries whether it uses any of it or not."""


def definition(repnum: int, text: str, *, part: str | None = None) -> Record:
    attrs = {"cmper": str(repnum)}
    if part is not None:
        attrs["part"] = part
    return Record(tag="textRepeatText", attrs=attrs, text="", fields={"rptText": text})


def assignment(measure: int, repnum: int, *, inci: int = 0, part: str | None = None) -> Record:
    attrs = {"cmper": str(measure), "inci": str(inci)}
    if part is not None:
        attrs["part"] = part
    return Record(tag="textRepeatAssign", attrs=attrs, text="", fields={"repnum": str(repnum)})


def palette() -> tuple[Record, ...]:
    return tuple(definition(index + 1, text) for index, text in enumerate(PALETTE))


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


def test_the_palette_alone_places_nothing() -> None:
    """Every one of the 401 corpus documents carries these definitions, most
    using none of them. Reading the palette puts a D.S. in every score."""
    assert jumps_by_measure(document(*palette())) == {}


def test_an_assignment_places_its_words_at_its_measure() -> None:
    doc = document(*palette(), assignment(measure=12, repnum=3))
    assert jumps_by_measure(doc) == {12: ("Fine",)}


def test_a_measure_can_carry_two_markings() -> None:
    doc = document(*palette(), assignment(10, 1), assignment(10, 3, inci=1))
    assert jumps_by_measure(doc) == {10: ("D.C. al Fine", "Fine")}


def test_an_assignment_naming_a_definition_with_no_text_is_dropped() -> None:
    """Five of the corpus's 17 assignments name a `textRepeatDef` that exists
    while its `textRepeatText` does not -- the file simply has no words for
    them, and a bare number is not a marking."""
    assert jumps_by_measure(document(*palette(), assignment(4, 99))) == {}


def test_a_marking_that_is_a_font_glyph_is_not_printed_as_text() -> None:
    """`%` is the segno in a music font. Emitting it as words puts a literal
    percent sign in the score, and the definitions carrying one have no
    `fontID` to identify the glyph with."""
    doc = document(definition(1, "%"), assignment(7, 1))
    assert jumps_by_measure(doc) == {}


def test_a_marking_containing_a_digit_is_still_words() -> None:
    """ "To Coda 2" is words with a number in it, not a glyph."""
    doc = document(definition(1, "To Coda 2"), assignment(7, 1))
    assert jumps_by_measure(doc) == {7: ("To Coda 2",)}


def test_part_records_are_ignored() -> None:
    doc = document(*palette(), assignment(5, 3, part="1"))
    assert jumps_by_measure(doc) == {}


def test_a_part_variant_definition_does_not_shadow_the_score_text() -> None:
    doc = document(definition(1, "Fine"), definition(1, "D.C.", part="1"), assignment(9, 1))
    assert jumps_by_measure(doc) == {9: ("Fine",)}


def test_markup_is_stripped_from_the_words() -> None:
    """The corpus stores some markings with Finale's inline font markup around
    them; printing that verbatim puts control codes in the score."""
    doc = document(definition(1, "^fontTxt(Times,0,0)Fine"), assignment(3, 1))
    assert jumps_by_measure(doc) == {3: ("Fine",)}
