"""Tests for the legacy .mus payload decoder."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from finale_file_parser.enigma import mus_payload
from finale_file_parser.enigma.blast import blast_decompress
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import (
    MAX_MUS_PAYLOAD,
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    ByteOrder,
    read_mus_payload,
    read_mus_pools,
)

BANNER_OFFSET = 0x20
CONTAINER_START = 0x200
DCL_OFFSET = 0x20A
"""Where the first DCL stream begins: the container start plus a record header."""

REFERENCE_DCL = bytes([0x00, 0x04, 0x82, 0x24, 0x25, 0x8F, 0x80, 0x7F])
"""blast.c's own test vector. Decodes to `AIAIAIAIAIAIA`."""
REFERENCE_TEXT = b"AIAIAIAIAIAIA"


def _mus_header(year: int) -> bytearray:
    """A minimal plaintext .mus header carrying a banner year."""
    header = bytearray(b"\x00" * CONTAINER_START)
    header[0:18] = b"ENIGMA BINARY FILE"
    banner = f"Finale(R) {year} Copyright (c) 1987-2000 Coda".encode("latin-1")
    header[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
    return header


def _pool_record(kind: int, stream: bytes, order: ByteOrder = "big") -> bytes:
    """One pool record: kind, total length, checksum, then the DCL stream."""
    length = 10 + len(stream)
    return (
        kind.to_bytes(2, order)
        + length.to_bytes(4, order)
        + b"\xde\xad\xbe\xef"  # checksum: read by Finale, not by this reader
        + stream
    )


def _empty_pool_record(kind: int, order: ByteOrder = "big") -> bytes:
    """The six-byte record an empty pool gets: no checksum, no stream."""
    return kind.to_bytes(2, order) + (6).to_bytes(4, order)


def _dcl_file(year: int = 2005, order: ByteOrder = "big", records: bytes | None = None) -> bytes:
    """A .mus-shaped file whose payload is a container of DCL pool records."""
    if records is None:
        records = _pool_record(POOL_OTHERS, REFERENCE_DCL, order)
    return bytes(_mus_header(year)) + records


def _zlib_file(payload: bytes, year: int = 2012) -> bytes:
    header = _mus_header(year)
    # Pad out to where the preamble would end, then append a real zlib stream.
    return bytes(header) + b"\x00" * 12 + zlib.compress(payload, 9)


def test_reads_a_dcl_payload(tmp_path: Path) -> None:
    path = tmp_path / "old.mus"
    path.write_bytes(_dcl_file())
    assert read_mus_payload(path) == REFERENCE_TEXT


@pytest.mark.parametrize("order", ["big", "little"])
def test_reads_every_pool_of_a_dcl_container(tmp_path: Path, order: ByteOrder) -> None:
    """All four pools, in file order, each labelled with the kind the file gives it.

    Reading only the first is what the previous revision did, and it left the
    entry pool -- the music -- undecoded on every 2001-2005 file.
    """
    records = b"".join(
        _pool_record(kind, REFERENCE_DCL, order)
        for kind in (POOL_OTHERS, POOL_DETAILS, POOL_ENTRIES, POOL_TEXT)
    )
    path = tmp_path / f"{order}.mus"
    path.write_bytes(_dcl_file(order=order, records=records))

    pools = read_mus_pools(path)
    assert [pool.kind for pool in pools] == [POOL_OTHERS, POOL_DETAILS, POOL_ENTRIES, POOL_TEXT]
    assert {pool.byte_order for pool in pools} == {order}
    assert [pool.data for pool in pools] == [REFERENCE_TEXT] * 4


def test_an_empty_pool_is_read_as_empty_not_skipped(tmp_path: Path) -> None:
    """A length of exactly 6 means the pool is there and has nothing in it.

    Three corpus documents carry an empty entry pool. Dropping the record
    instead of returning it would shift every later pool's kind onto the wrong
    bytes.
    """
    records = (
        _pool_record(POOL_OTHERS, REFERENCE_DCL)
        + _empty_pool_record(POOL_ENTRIES)
        + _pool_record(POOL_TEXT, REFERENCE_DCL)
    )
    path = tmp_path / "empty_pool.mus"
    path.write_bytes(_dcl_file(records=records))

    pools = read_mus_pools(path)
    assert [pool.kind for pool in pools] == [POOL_OTHERS, POOL_ENTRIES, POOL_TEXT]
    assert pools[1].data == b""
    assert pools[2].data == REFERENCE_TEXT


def test_a_pool_record_running_past_the_end_is_refused(tmp_path: Path) -> None:
    """A declared length is file-supplied, so it is checked before it is trusted."""
    record = bytearray(_pool_record(POOL_OTHERS, REFERENCE_DCL))
    record[2:6] = (1 << 20).to_bytes(4, "big")
    path = tmp_path / "overrun.mus"
    path.write_bytes(_dcl_file(records=bytes(record)))
    with pytest.raises(CorruptScoreError, match="does not fit"):
        read_mus_pools(path)


def test_a_pool_record_too_short_to_advance_is_refused(tmp_path: Path) -> None:
    """A length below the six-byte minimum would leave the walk in place forever."""
    record = bytearray(_pool_record(POOL_OTHERS, REFERENCE_DCL))
    record[2:6] = (2).to_bytes(4, "big")
    path = tmp_path / "stuck.mus"
    path.write_bytes(_dcl_file(records=bytes(record)))
    with pytest.raises(CorruptScoreError, match="declares length 2"):
        read_mus_pools(path)


def test_a_pool_whose_stream_is_corrupt_is_refused_not_truncated(tmp_path: Path) -> None:
    """Half a document read as a whole one is worse than an error."""
    records = _pool_record(POOL_OTHERS, REFERENCE_DCL) + _pool_record(
        POOL_ENTRIES, b"\x00\x04\xff\xff\xff\xff"
    )
    path = tmp_path / "corrupt_pool.mus"
    path.write_bytes(_dcl_file(records=records))
    with pytest.raises(CorruptScoreError):
        read_mus_pools(path)


def test_trailing_bytes_after_the_last_pool_are_refused(tmp_path: Path) -> None:
    """The records tile the file exactly; anything else is a file we misread."""
    path = tmp_path / "trailing.mus"
    path.write_bytes(_dcl_file() + b"\x00\x00\x00")
    with pytest.raises(CorruptScoreError, match="does not fit|truncated"):
        read_mus_pools(path)


def test_each_stream_is_handed_only_its_own_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decompressor never sees past the record's declared length.

    Asserted on the buffer handed over rather than on the result, deliberately:
    a stream that reads on into its neighbour raises about as often as it
    returns something, so an outcome-based test passes either way and guards
    nothing. This one fails the moment the slice is widened.
    """
    seen: list[int] = []

    def spy(stream: bytes, start: int, cap: int) -> bytes:
        seen.append(len(stream) - start)
        return blast_decompress(stream, start, cap)

    monkeypatch.setattr(mus_payload, "blast_decompress", spy)
    records = _pool_record(POOL_OTHERS, REFERENCE_DCL) + _pool_record(POOL_ENTRIES, REFERENCE_DCL)
    path = tmp_path / "bounded.mus"
    path.write_bytes(_dcl_file(records=records))

    read_mus_pools(path)
    assert seen == [len(REFERENCE_DCL), len(REFERENCE_DCL)]


def test_a_pool_whose_stream_lacks_its_end_marker_is_refused(tmp_path: Path) -> None:
    """Truncation must surface as an error, not as a short pool."""
    records = _pool_record(POOL_OTHERS, REFERENCE_DCL[:-1]) + _pool_record(
        POOL_ENTRIES, REFERENCE_DCL
    )
    path = tmp_path / "bleed.mus"
    path.write_bytes(_dcl_file(records=records))
    with pytest.raises(CorruptScoreError, match="did not decode"):
        read_mus_pools(path)


def test_zlib_era_pools_are_unlabelled(tmp_path: Path) -> None:
    """That container names nothing, so a reader has to walk a pool to know it."""
    payload = b"Times New Roman\x00" * 500
    path = tmp_path / "new.mus"
    path.write_bytes(_zlib_file(payload))
    pools = read_mus_pools(path)
    assert [pool.kind for pool in pools] == [None]
    assert pools[0].byte_order == "little"


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
    assert read_mus_payload(path) == REFERENCE_TEXT


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
