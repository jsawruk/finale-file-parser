"""The framed file `finale-parser extract` writes, and reads back.

A `.mus` keeps its payload as four compressed pools, and a hex editor sees only
the compressed bytes. This file is those pools decompressed, in one piece, laid
out so a reader can walk them without decompressing anything.

**The chain is the container's own.** A 2001-2005 `.mus` already stores its
payload as a run of records -- kind, length, checksum -- laid end to end from
`0x200` with no gaps, where `length` counts its own ten-byte header. This file
keeps exactly that shape, so what a reader learns from walking it is true of
the format rather than true of us. Two things differ, and only two: each
payload is decompressed, so `length` is the decompressed size; and an 8-byte
header is prepended so the file announces what it is instead of impersonating a
score.

**The checksum is always zero.** The container's checksum covers the
*compressed* stream, which this file does not contain, so carrying it across
would invite a reader to verify it against bytes it never described. The field
is kept because the chain's shape is the point; its value is not.

A 2011-era `.mus` has no pool chain at all -- its pools are bare zlib streams --
so for those documents the framing is borrowed rather than preserved. The
header's `era` byte says which case a reader is looking at.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import MAX_MUS_PAYLOAD, ByteOrder, MusPool

__all__ = [
    "EMPTY_ENTRY_LENGTH",
    "ENTRY_HEADER_SIZE",
    "ERA_DCL",
    "ERA_ZLIB",
    "HEADER_SIZE",
    "MAGIC",
    "VERSION",
    "PoolFile",
    "era_of",
    "read_pool_file",
    "write_pool_file",
]

MAGIC = b"FMUS"
"""Four bytes that say this is not a `.mus`.

A derived file that looked like the real thing would eventually be opened as
one, and every offset in it would be wrong by eight bytes and a decompression.
"""

VERSION = 1
HEADER_SIZE = 8
"""magic (4) + version (1) + order (1) + era (1) + pool count (1).

Every field is a single byte, so the header itself has no byte order to get
wrong -- which matters, because the byte order of everything after it is what
byte 5 announces.
"""

ENTRY_HEADER_SIZE = 10
"""kind (2) + length (4) + checksum (4), as the container writes it."""

EMPTY_ENTRY_LENGTH = 6
"""A `length` of exactly 6 means kind and length and nothing else -- no
checksum, no payload. The container's own way of saying a pool exists and is
empty, which three corpus documents use for their entry pool."""

ERA_ZLIB = 0
ERA_DCL = 1

_MAX_POOLS = 64
"""Refuse a file claiming more pools than any real document has.

Every corpus document has exactly four. The cap is defence in depth: the count
is a file-supplied number that sizes a loop.
"""


@dataclass(frozen=True)
class PoolFile:
    """A framed file, read back."""

    version: int
    byte_order: ByteOrder
    era: int
    pools: tuple[MusPool, ...]


def era_of(pools: tuple[MusPool, ...]) -> int:
    """Which container these pools came out of.

    A DCL container labels its pools and a zlib-era one does not, so a labelled
    first pool is the era, stated by the container rather than guessed.
    """
    return ERA_DCL if pools and pools[0].kind is not None else ERA_ZLIB


def _int(value: int, size: int, order: ByteOrder) -> bytes:
    return value.to_bytes(size, order)


def write_pool_file(pools: tuple[MusPool, ...], *, era: int) -> bytes:
    """Frame `pools` as one file.

    Raises:
        ValueError: a pool has no `kind`, or there are too many pools. An
            unidentified pool is refused rather than written with a guessed
            label -- a wrong kind in this header sends a reader to the wrong
            record shape and everything after it is confident nonsense.
    """
    if not pools:
        raise ValueError("no pools to write")
    if len(pools) > _MAX_POOLS:
        raise ValueError(f"{len(pools)} pools exceeds the {_MAX_POOLS} this format allows")
    if era not in (ERA_ZLIB, ERA_DCL):
        raise ValueError(f"unknown era {era!r}")

    order: ByteOrder = pools[0].byte_order
    out = bytearray(MAGIC)
    out.append(VERSION)
    out.append(1 if order == "big" else 0)
    out.append(era)
    out.append(len(pools))

    for pool in pools:
        if pool.kind is None:
            raise ValueError("a pool with no identified kind cannot be written")
        out += _int(pool.kind, 2, order)
        if not pool.data:
            out += _int(EMPTY_ENTRY_LENGTH, 4, order)
            continue
        out += _int(ENTRY_HEADER_SIZE + len(pool.data), 4, order)
        out += _int(0, 4, order)
        out += pool.data
    return bytes(out)


def read_pool_file(data: bytes) -> PoolFile:
    """Walk a framed file back into pools.

    This reads a file this project wrote, and still does not trust it: every
    length is bounds-checked before it is used, because the alternative is a
    reader that can be made to walk past its own buffer by a number in a file.

    Raises:
        CorruptScoreError: the header is wrong, the version is not one this
            reader knows, or the chain does not tile the data exactly.
    """
    if len(data) < HEADER_SIZE:
        raise CorruptScoreError("not a pool file: shorter than its header")
    if data[:4] != MAGIC:
        raise CorruptScoreError("not a pool file: wrong magic")
    version = data[4]
    if version != VERSION:
        raise CorruptScoreError(f"pool file version {version} is not version {VERSION}")
    order: ByteOrder = "big" if data[5] else "little"
    era = data[6]
    if era not in (ERA_ZLIB, ERA_DCL):
        raise CorruptScoreError(f"pool file names an unknown era {era}")
    count = data[7]
    if not 0 < count <= _MAX_POOLS:
        raise CorruptScoreError(f"pool file claims {count} pools")

    pools: list[MusPool] = []
    at = HEADER_SIZE
    for _ in range(count):
        if at + 6 > len(data):
            raise CorruptScoreError("pool file ends inside a chain entry header")
        kind = int.from_bytes(data[at : at + 2], order)
        length = int.from_bytes(data[at + 2 : at + 6], order)
        if length == EMPTY_ENTRY_LENGTH:
            pools.append(MusPool(data=b"", byte_order=order, kind=kind))
            at += 6
            continue
        if length < ENTRY_HEADER_SIZE or length > MAX_MUS_PAYLOAD:
            raise CorruptScoreError(f"pool file entry claims {length} bytes")
        if at + length > len(data):
            raise CorruptScoreError("pool file entry runs past the end of the file")
        start = at + ENTRY_HEADER_SIZE
        pools.append(MusPool(data=data[start : at + length], byte_order=order, kind=kind))
        at += length

    if at != len(data):
        raise CorruptScoreError(f"pool file has {len(data) - at} bytes after its last pool")
    return PoolFile(version=version, byte_order=order, era=era, pools=tuple(pools))
