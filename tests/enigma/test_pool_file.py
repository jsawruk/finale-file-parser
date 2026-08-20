"""The framed file `finale-parser extract` writes.

The chain is the DCL container's own -- kind, length, checksum, laid end to
end, with `length` counting its own header -- so a reader of this file walks it
exactly as a reader of a `.mus` walks the real thing. What differs is that the
payloads are decompressed and a magic header says so.

The round-trip test is the one that matters. A framing bug that shifted a
payload by one byte would pass every other assertion here and produce a hex
dump that is wrong in a way a reader would trust.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    ByteOrder,
    MusPool,
)
from finale_file_parser.enigma.pool_file import (
    EMPTY_ENTRY_LENGTH,
    ERA_DCL,
    ERA_ZLIB,
    HEADER_SIZE,
    MAGIC,
    VERSION,
    read_pool_file,
    write_pool_file,
)


def _pools(order: ByteOrder = "little") -> tuple[MusPool, ...]:
    return (
        MusPool(data=b"\x01\x02\x03\x04", byte_order=order, kind=POOL_OTHERS),
        MusPool(data=b"\xaa" * 40, byte_order=order, kind=POOL_DETAILS),
        MusPool(data=b"", byte_order=order, kind=POOL_ENTRIES),
        MusPool(data=b"text", byte_order=order, kind=POOL_TEXT),
    )


def test_pools_survive_a_round_trip() -> None:
    written = write_pool_file(_pools(), era=ERA_DCL)
    back = read_pool_file(written)
    assert back.era == ERA_DCL
    assert back.byte_order == "little"
    assert back.version == VERSION
    assert [(p.kind, p.data) for p in back.pools] == [(p.kind, p.data) for p in _pools()]


def test_a_big_endian_document_round_trips_too() -> None:
    """37 of the 139 DCL-era corpus documents are big-endian, so this is not a
    rare branch. Reading it the wrong way round yields plausible nonsense."""
    written = write_pool_file(_pools("big"), era=ERA_DCL)
    back = read_pool_file(written)
    assert back.byte_order == "big"
    assert [p.data for p in back.pools] == [p.data for p in _pools("big")]


def test_the_header_announces_the_file() -> None:
    written = write_pool_file(_pools(), era=ERA_ZLIB)
    assert written[:4] == MAGIC, "the file must not impersonate a .mus"
    assert written[4] == VERSION
    assert written[5] == 0, "0 is little-endian"
    assert written[6] == ERA_ZLIB
    assert written[7] == 4


def test_an_empty_pool_keeps_its_shape() -> None:
    """`length == 6` is how the container itself says a pool exists and holds
    nothing -- three corpus documents carry an empty entry pool that way. A
    missing pool and an empty one mean different things."""
    written = write_pool_file(_pools(), era=ERA_DCL)
    back = read_pool_file(written)
    empty = [p for p in back.pools if p.kind == POOL_ENTRIES][0]
    assert empty.data == b""

    # and the entry on the wire is the short form
    offset = HEADER_SIZE
    for pool in _pools()[:2]:
        offset += 10 + len(pool.data)
    length = int.from_bytes(written[offset + 2 : offset + 6], "little")
    assert length == EMPTY_ENTRY_LENGTH


def test_an_unlabelled_pool_is_refused() -> None:
    """A pool whose kind was never identified must not be written with a guess."""
    with pytest.raises(ValueError):
        write_pool_file((MusPool(data=b"x", kind=None),), era=ERA_ZLIB)


@pytest.mark.parametrize(
    "mangle",
    [
        pytest.param(lambda b: b[:3], id="truncated-magic"),
        pytest.param(lambda b: b"XXXX" + b[4:], id="wrong-magic"),
        pytest.param(lambda b: b[:4] + bytes([VERSION + 9]) + b[5:], id="future-version"),
        pytest.param(lambda b: b[: HEADER_SIZE + 4], id="truncated-chain"),
        pytest.param(lambda b: b[:6] + b"\x09" + b[7:], id="unknown-era"),
        pytest.param(lambda b: b[:5] + b"\x02" + b[6:], id="unknown-byte-order"),
    ],
)
def test_a_malformed_file_raises_rather_than_guessing(
    mangle: Callable[[bytes], bytes],
) -> None:
    """This file is one we wrote, and it is still untrusted input."""
    with pytest.raises(CorruptScoreError):
        read_pool_file(mangle(write_pool_file(_pools(), era=ERA_DCL)))


def test_an_unknown_byte_order_names_the_bad_value() -> None:
    """`"big" if data[5] else "little"` maps every non-zero byte to big-endian,
    so garbage in that field would silently pick a byte order instead of being
    refused. Misinterpreting the chain as the wrong endianness happens to raise
    `CorruptScoreError` too, but for an unrelated reason (a corrupted length),
    so the message is what tells the two apart."""
    written = write_pool_file(_pools(), era=ERA_DCL)
    mangled = written[:5] + b"\x02" + written[6:]
    with pytest.raises(CorruptScoreError, match="unknown byte order 2"):
        read_pool_file(mangled)


def test_a_declared_length_beyond_the_data_is_refused() -> None:
    """The length field is the one number a hostile file controls. Believing it
    is how a reader is made to allocate or read past its buffer."""
    written = bytearray(write_pool_file(_pools(), era=ERA_DCL))
    written[HEADER_SIZE + 2 : HEADER_SIZE + 6] = (1 << 30).to_bytes(4, "little")
    with pytest.raises(CorruptScoreError):
        read_pool_file(bytes(written))


def test_a_length_within_the_cap_but_past_the_file_is_refused() -> None:
    """`1 << 30` trips the 64 MiB inflation cap before the buffer-bounds check
    ever runs. This length stays under that cap but still runs past the actual
    file, so it is the `at + length > len(data)` check itself that must fire --
    asserted by message, because a truncating slice plus the next entry's own
    header check would otherwise raise `CorruptScoreError` anyway, for the
    wrong reason, and mask the bounds check going missing."""
    written = bytearray(write_pool_file(_pools(), era=ERA_DCL))
    written[HEADER_SIZE + 2 : HEADER_SIZE + 6] = (len(written) + 1_000).to_bytes(4, "little")
    with pytest.raises(CorruptScoreError, match="runs past the end of the file"):
        read_pool_file(bytes(written))


def test_an_unidentifiable_pool_set_is_refused() -> None:
    """Better no file than a file whose labels are guesses: the kind in the
    header is what sends a reader to a record shape."""
    from finale_file_parser.enigma.pool_file import identify_pools

    unlabelled = tuple(MusPool(data=b"\x00" * 64, byte_order="little", kind=None) for _ in range(4))
    with pytest.raises(CorruptScoreError):
        identify_pools(unlabelled)


def test_labelled_pools_are_left_alone() -> None:
    """A DCL container states its pool kinds. Sniffing over the top of that
    could only ever disagree with the file about its own contents."""
    from finale_file_parser.enigma.pool_file import identify_pools

    given = _pools()
    assert [p.kind for p in identify_pools(given)] == [p.kind for p in given]
