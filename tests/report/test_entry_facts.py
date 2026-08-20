"""Unit tests for the report's entry facts. No corpus: every document here is
built in process, so CI runs these even though `corpus/` is gitignored."""

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
from finale_file_parser.report.entry_facts import Reference, references_to

EMPTY: tuple[Record, ...] = ()


def _doc(
    details: tuple[Record, ...] = EMPTY,
    others: tuple[Record, ...] = EMPTY,
    entries: tuple[Record, ...] = EMPTY,
) -> EnigmaDocument:
    """A document holding only the pools a test needs."""
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=others),
        details=DetailsPool(records=details),
        entries=EntriesPool(records=entries),
        texts=TextsPool(records=EMPTY),
    )


def test_references_name_only_records_holding_this_entnum() -> None:
    """A record counts as a reference when it names the entry, not when it
    merely sits in the same measure -- otherwise "points at" becomes "is near"."""
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})
    other = Record(tag="articAssign", attrs={"entnum": "11", "inci": "0"}, text="", fields={})
    doc = _doc(details=(artic, other))

    assert references_to(doc, 9) == (
        Reference(pool="details", tag="articAssign", key="(entnum 9, inci 0)"),
    )
