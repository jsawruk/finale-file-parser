"""Tests for the 2001-2005 `.mus` row reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma import blast
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    ByteOrder,
)
from finale_file_parser.enigma.mus_rows import read_mus_rows

BANNER_OFFSET = 0x20
CONTAINER_START = 0x200


def _length_code_bits(symbol: int) -> list[int]:
    """The bits `blast` consumes to decode `symbol` from the length code."""
    table = blast._LENGTH_CODE
    index = first = 0
    for length in range(1, 16):
        count = table.count[length]
        for offset in range(count):
            if table.symbol[index + offset] == symbol:
                code = first + offset
                return [((code >> (length - 1 - bit)) & 1) ^ 1 for bit in range(length)]
        index += count
        first = (first + count) << 1
    raise AssertionError(f"length code has no symbol {symbol}")


def _dcl_literal_stream(raw: bytes) -> bytes:
    """A DCL stream storing `raw` as uncoded literals."""
    bits: list[int] = []
    for byte in raw:
        bits.append(0)
        bits.extend((byte >> i) & 1 for i in range(8))
    bits.append(1)
    bits.extend(_length_code_bits(15))
    bits.extend([1] * 8)
    out = bytearray(b"\x00\x04")
    for start in range(0, len(bits), 8):
        out.append(sum(bit << i for i, bit in enumerate(bits[start : start + 8])))
    return bytes(out)


def _mus_file(others: bytes, details: bytes, order: ByteOrder = "big") -> bytes:
    """A 2005-era .mus carrying the given `others` and `details` pool bytes."""
    header = bytearray(b"\x00" * CONTAINER_START)
    header[0:18] = b"ENIGMA BINARY FILE"
    banner = b"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic"
    header[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner

    def record(kind: int, raw: bytes) -> bytes:
        if not raw:
            return kind.to_bytes(2, order) + (6).to_bytes(4, order)
        stream = _dcl_literal_stream(raw)
        return (
            kind.to_bytes(2, order)
            + (10 + len(stream)).to_bytes(4, order)
            + b"\x00\x00\x00\x00"
            + stream
        )

    return (
        bytes(header)
        + record(POOL_OTHERS, others)
        + record(POOL_DETAILS, details)
        + record(POOL_ENTRIES, b"")
        + record(POOL_TEXT, b"")
    )


def _others_row(tag: str, cmper: int, values: list[int], order: ByteOrder = "big") -> bytes:
    """One 16-byte `others` row: cmper, tag, then six u16 values."""
    assert len(values) == 6
    tag_word = (ord(tag[0]) << 8) | ord(tag[1])
    return (
        cmper.to_bytes(2, order)
        + tag_word.to_bytes(2, order)
        + b"".join(v.to_bytes(2, order) for v in values)
    )


def _details_row(
    tag: str, cmper1: int, cmper2: int, values: list[int], order: ByteOrder = "big"
) -> bytes:
    """One 16-byte `details` row: two comparators, tag, then five u16 values."""
    assert len(values) == 5
    tag_word = (ord(tag[0]) << 8) | ord(tag[1])
    return (
        cmper1.to_bytes(2, order)
        + cmper2.to_bytes(2, order)
        + tag_word.to_bytes(2, order)
        + b"".join(v.to_bytes(2, order) for v in values)
    )


@pytest.mark.parametrize("order", ["big", "little"])
def test_reads_a_row_under_each_byte_order(tmp_path: Path, order: ByteOrder) -> None:
    """The tag is a u16, so its two characters swap on a little-endian file.

    Reading the pair verbatim finds no known tag in the 102 little-endian corpus
    documents -- every one of them looked as though it had no staff spec at all.
    """
    others = _others_row("MS", 1, [600, 0, 4, 1024, 1, 16], order)
    path = tmp_path / f"{order}.mus"
    path.write_bytes(_mus_file(others, b"", order))

    rows = read_mus_rows(path)
    assert rows.byte_order == order
    record = rows.others[("MS", 1)]
    assert record.incidences == 1
    assert int.from_bytes(record.payload[4:6], order) == 4  # beats
    assert int.from_bytes(record.payload[6:8], order) == 1024  # divbeat


def test_incidences_under_one_key_concatenate(tmp_path: Path) -> None:
    """A record too big for one row runs on into further rows under the same key.

    `etfspec.pdf` calls these incidences and says a staff spec takes three of
    them, so a reader that kept only the first would see a third of the record.
    """
    others = (
        _others_row("IS", 1, [0, 0, 0, 0, 0, 0])
        + _others_row("IS", 1, [0, 0, 5, 0, 0, 0])
        + _others_row("IS", 1, [0xFCFC, 0xFCFC, 0xFFFC, 50, 0, 0])
    )
    path = tmp_path / "staff.mus"
    path.write_bytes(_mus_file(others, b""))

    record = read_mus_rows(path).others[("IS", 1)]
    assert record.incidences == 3
    assert len(record.payload) == 36
    # botLines, from the spec's own worked example.
    assert int.from_bytes(record.payload[16:18], "big") == 5
    # fullName: the text-block number naming the staff.
    assert int.from_bytes(record.payload[30:32], "big") == 50


def test_details_carry_two_comparators(tmp_path: Path) -> None:
    details = _details_row("GF", 3, 7, [0, 0, 75, 12, 0])
    path = tmp_path / "gf.mus"
    path.write_bytes(_mus_file(_others_row("MS", 1, [0] * 6), details))

    rows = read_mus_rows(path)
    record = rows.details[("GF", 3, 7)]
    assert (record.cmper, record.cmper2) == (3, 7)
    assert len(record.payload) == 10
    assert int.from_bytes(record.payload[6:8], "big") == 12


def test_records_keep_file_order(tmp_path: Path) -> None:
    """Rows are sorted by tag in the file, and a reader must not resort them."""
    others = b"".join(_others_row("MS", n, [0] * 6) for n in (1, 2, 3))
    path = tmp_path / "order.mus"
    path.write_bytes(_mus_file(others, b""))
    assert [key for key in read_mus_rows(path).others] == [("MS", 1), ("MS", 2), ("MS", 3)]


def test_a_pool_that_is_not_whole_rows_is_refused(tmp_path: Path) -> None:
    """Every corpus pool is a whole number of rows; a remainder means we misread it."""
    path = tmp_path / "ragged.mus"
    path.write_bytes(_mus_file(_others_row("MS", 1, [0] * 6) + b"\x00\x00\x00", b""))
    with pytest.raises(CorruptScoreError, match="not a whole number of 16-byte rows"):
        read_mus_rows(path)


def test_a_zlib_era_file_is_refused(tmp_path: Path) -> None:
    """Only the 2001-2005 container labels its pools, and this reader needs that."""
    import zlib

    header = bytearray(b"\x00" * 0x216)
    header[0:18] = b"ENIGMA BINARY FILE"
    banner = b"Finale(R) 2012 Copyright (c) 1987-2011 MakeMusic"
    header[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
    path = tmp_path / "new.mus"
    path.write_bytes(bytes(header) + zlib.compress(b"Times New Roman\x00" * 500, 9))
    with pytest.raises(CorruptScoreError, match="no labelled record pools"):
        read_mus_rows(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_mus_rows(tmp_path / "absent.mus")
