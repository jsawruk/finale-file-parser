"""Tests for the legacy .mus payload decoder."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from finale_file_parser.enigma.blast import blast_decompress
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import MAX_MUS_PAYLOAD, read_mus_payload

BANNER_OFFSET = 0x20
DCL_OFFSET = 0x20A


def _mus_header(year: int) -> bytearray:
    """A minimal plaintext .mus header carrying a banner year."""
    header = bytearray(b"\x00" * DCL_OFFSET)
    header[0:18] = b"ENIGMA BINARY FILE"
    banner = f"Finale(R) {year} Copyright (c) 1987-2000 Coda".encode("latin-1")
    header[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
    return header


def _dcl_file(year: int = 2005) -> bytes:
    """A .mus-shaped file whose payload is the reference DCL stream."""
    return bytes(_mus_header(year)) + bytes([0x00, 0x04, 0x82, 0x24, 0x25, 0x8F, 0x80, 0x7F])


def _zlib_file(payload: bytes, year: int = 2012) -> bytes:
    header = _mus_header(year)
    # Pad out to where the preamble would end, then append a real zlib stream.
    return bytes(header) + b"\x00" * 12 + zlib.compress(payload, 9)


def test_reads_a_dcl_payload(tmp_path: Path) -> None:
    path = tmp_path / "old.mus"
    path.write_bytes(_dcl_file())
    assert read_mus_payload(path) == b"AIAIAIAIAIAIA"


def test_reads_a_zlib_chain_payload(tmp_path: Path) -> None:
    payload = b"Times New Roman\x00" * 500
    path = tmp_path / "new.mus"
    path.write_bytes(_zlib_file(payload))
    assert read_mus_payload(path) == payload


def test_concatenated_zlib_streams_are_all_returned(tmp_path: Path) -> None:
    """The newer format stores several streams back to back, not one."""
    first, second = b"A" * 5000, b"B" * 6000
    header = _mus_header(2012)
    body = zlib.compress(first, 9) + zlib.compress(second, 9)
    path = tmp_path / "chain.mus"
    path.write_bytes(bytes(header) + b"\x00" * 12 + body)
    assert read_mus_payload(path) == first + second


def test_falls_back_to_the_other_scheme_when_the_year_disagrees(tmp_path: Path) -> None:
    """A DCL payload behind a 2012 banner must still decode.

    The banner picks the order to try, not the only thing tried -- an
    unrecognised or mislabelled variant should stay readable.
    """
    path = tmp_path / "mislabelled.mus"
    path.write_bytes(_dcl_file(year=2012))
    assert read_mus_payload(path) == b"AIAIAIAIAIAIA"


def test_undecodable_payload_raises(tmp_path: Path) -> None:
    path = tmp_path / "junk.mus"
    path.write_bytes(bytes(_mus_header(2005)) + bytes(range(256)) * 8)
    with pytest.raises(CorruptScoreError, match="neither scheme"):
        read_mus_payload(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_mus_payload(tmp_path / "absent.mus")


def test_stray_zlib_magic_does_not_derail_the_scan(tmp_path: Path) -> None:
    """`78 9c` occurs by chance a few times per real file.

    A coincidental pair must be stepped over, not treated as a stream, and must
    not stall the scan.
    """
    payload = b"real payload " * 500
    header = _mus_header(2012)
    body = b"\x78\x9c\x00\x01" + zlib.compress(payload, 9)
    path = tmp_path / "stray.mus"
    path.write_bytes(bytes(header) + body)
    assert read_mus_payload(path) == payload


def test_inflation_cap_is_enforced(tmp_path: Path) -> None:
    """A zip bomb must be refused while inflating, not after.

    Deleting the in-loop budget check turns this from an error into a
    multi-gigabyte allocation.
    """
    bomb = zlib.compress(b"\x00" * (MAX_MUS_PAYLOAD + 4096), 9)
    path = tmp_path / "bomb.mus"
    path.write_bytes(bytes(_mus_header(2012)) + b"\x00" * 12 + bomb)
    with pytest.raises(CorruptScoreError):
        read_mus_payload(path)


def test_dcl_stream_larger_than_the_cap_is_refused(tmp_path: Path) -> None:
    """Same guarantee on the DCL path."""
    # distance 1, long length: expands enormously from a tiny input.
    path = tmp_path / "old_bomb.mus"
    path.write_bytes(_dcl_file())
    # Decoding with a tiny cap must refuse rather than return a partial result.
    data = path.read_bytes()
    with pytest.raises(Exception, match="output cap"):
        blast_decompress(data, DCL_OFFSET, 4)
