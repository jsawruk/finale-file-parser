"""Tests for the PKWARE DCL decompressor."""

from __future__ import annotations

import pytest

from finale_file_parser.enigma.blast import CorruptDclStreamError, blast_decompress

REFERENCE_STREAM = bytes([0x00, 0x04, 0x82, 0x24, 0x25, 0x8F, 0x80, 0x7F])
REFERENCE_PLAINTEXT = b"AIAIAIAIAIAIA"
"""The vector documented in blast.c's own header comment. This is the only
external check on the port; without it a subtly wrong table would produce
plausible garbage instead of an obvious failure."""

CAP = 1 << 20


def test_decodes_the_reference_vector() -> None:
    assert blast_decompress(REFERENCE_STREAM, 0, CAP) == REFERENCE_PLAINTEXT


def test_decodes_from_a_nonzero_start_offset() -> None:
    padded = b"\xde\xad\xbe\xef" + REFERENCE_STREAM
    assert blast_decompress(padded, 4, CAP) == REFERENCE_PLAINTEXT


@pytest.mark.parametrize("flag", [2, 7, 0xFF])
def test_rejects_invalid_literal_flag(flag: int) -> None:
    stream = bytes([flag]) + REFERENCE_STREAM[1:]
    with pytest.raises(CorruptDclStreamError, match="literal flag"):
        blast_decompress(stream, 0, CAP)


@pytest.mark.parametrize("bits", [0, 3, 7, 0xFF])
def test_rejects_invalid_dictionary_selector(bits: int) -> None:
    stream = REFERENCE_STREAM[:1] + bytes([bits]) + REFERENCE_STREAM[2:]
    with pytest.raises(CorruptDclStreamError, match="dictionary size"):
        blast_decompress(stream, 0, CAP)


@pytest.mark.parametrize("start", [-1, 7, 8, 99])
def test_rejects_a_start_offset_with_no_room_for_a_header(start: int) -> None:
    with pytest.raises(CorruptDclStreamError, match="no room"):
        blast_decompress(REFERENCE_STREAM, start, CAP)


def test_rejects_truncated_input() -> None:
    with pytest.raises(CorruptDclStreamError, match="truncated|Huffman|back-reference"):
        blast_decompress(REFERENCE_STREAM[:4], 0, CAP)


def test_enforces_the_output_cap() -> None:
    """The cap must be enforced *while* decoding, not after.

    Deleting the in-loop check makes this hang or exhaust memory rather than
    fail, which is the whole point of the limit.
    """
    with pytest.raises(CorruptDclStreamError, match="output cap"):
        blast_decompress(REFERENCE_STREAM, 0, 4)


def test_cap_is_not_off_by_one() -> None:
    """A cap exactly at the output size must still succeed."""
    assert blast_decompress(REFERENCE_STREAM, 0, len(REFERENCE_PLAINTEXT))


def test_rejects_garbage_rather_than_looping() -> None:
    garbage = bytes([0x00, 0x04]) + bytes(range(256)) * 4
    with pytest.raises(CorruptDclStreamError):
        blast_decompress(garbage, 0, CAP)
