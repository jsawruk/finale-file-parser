"""Unit tests for barline styles."""

from __future__ import annotations

import pytest

from finale_file_parser.enigma.barlines import barline_styles
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


def measure(number: int, style: str | None = None, *, part: str | None = None) -> Record:
    attrs = {"cmper": str(number)}
    if part is not None:
        attrs["part"] = part
    fields = {} if style is None else {"barline": style}
    return Record(tag="measSpec", attrs=attrs, text="", fields=fields)


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


@pytest.mark.parametrize(
    ("name", "expected"), [("double", "light-light"), ("final", "light-heavy")]
)
def test_each_named_style_maps_to_its_musicxml_bar_style(name: str, expected: str) -> None:
    assert barline_styles(document(measure(4, name))) == {4: expected}


def test_an_ordinary_barline_needs_no_element() -> None:
    """`normal` is the default. Writing it out would put a `<bar-style>` on
    21,517 corpus measures and say nothing with any of them."""
    assert barline_styles(document(measure(1, "normal"), measure(2))) == {}


def test_an_unknown_style_is_ignored() -> None:
    assert barline_styles(document(measure(3, "dashed"))) == {}


def test_part_records_are_ignored() -> None:
    """A part can override a barline; honouring it would give the score a double
    bar it does not have."""
    doc = document(measure(5, "normal"), measure(5, "double", part="1"))
    assert barline_styles(doc) == {}
