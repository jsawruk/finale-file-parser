"""The 2001-2005 clef table.

`^95` holds what the later era calls `clefOptions`. Before this the whole DCL
cohort exported no clef at all -- a consumer given none assumes treble, so a
bass staff read an octave and a half wrong.
"""

from __future__ import annotations

import pytest

from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.mus_document import (
    _ROWS_CLEF_OPTIONS,
    _ROWS_CLEF_STRIDE,
    _rows_options,
)
from finale_file_parser.enigma.mus_others import OPTIONS_CMPER
from finale_file_parser.enigma.mus_payload import ByteOrder
from finale_file_parser.enigma.mus_rows import MusRowRecord, MusRows


def _rows(payload: bytes, order: ByteOrder = "little") -> MusRows:
    record = MusRowRecord(
        tag=_ROWS_CLEF_OPTIONS, cmper=OPTIONS_CMPER, cmper2=0, payload=payload, incidences=1
    )
    return MusRows(
        others={(_ROWS_CLEF_OPTIONS, OPTIONS_CMPER): record},
        details={},
        byte_order=order,
    )


def _entry(adjust: int, clef_char: int, order: ByteOrder) -> bytes:
    """One 18-byte clef entry: adjust at +0, clefChar at +2, the rest zero."""
    out = bytearray(_ROWS_CLEF_STRIDE)
    out[0:2] = adjust.to_bytes(2, order, signed=True)
    out[2:4] = clef_char.to_bytes(2, order)
    return bytes(out)


def _definitions(options: Record) -> tuple[Record, ...]:
    """The clef entries, narrowed from the field union a `Record` allows."""
    raw = options.fields["clefDef"]
    assert isinstance(raw, tuple)
    assert all(isinstance(entry, Record) for entry in raw)
    return raw  # type: ignore[return-value]


@pytest.mark.parametrize("order", ["little", "big"])
def test_the_table_is_read_in_the_documents_own_byte_order(order: ByteOrder) -> None:
    """37 corpus documents carry this table big-endian. Read little-endian, a
    clefChar of 38 becomes 9,728 -- a different character, so a different clef,
    reported with no sign that anything went wrong."""
    options = _rows_options(_rows(_entry(-10, 38, order), order))
    assert len(options) == 1
    first = _definitions(options[0])[0]
    assert first.fields["clefChar"] == "38"
    assert first.fields["adjust"] == "-10"


def test_every_entry_becomes_a_definition() -> None:
    payload = b"".join(_entry(0, char, "little") for char in (38, 63, 66))
    definitions = _definitions(_rows_options(_rows(payload))[0])
    assert [d.fields["clefChar"] for d in definitions] == ["38", "63", "66"]


def test_a_payload_that_is_not_whole_entries_yields_no_table() -> None:
    """The stride is known, so a payload that does not divide by it is not this
    record. A mis-strided table would produce plausible wrong clefs, which is
    worse than none: nothing on the page would say the clefs were guesses."""
    assert _rows_options(_rows(b"\x00" * (_ROWS_CLEF_STRIDE + 3))) == []


def test_a_document_without_the_record_yields_no_table() -> None:
    empty = MusRows(others={}, details={}, byte_order="little")
    assert _rows_options(empty) == []
