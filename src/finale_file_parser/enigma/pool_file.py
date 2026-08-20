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
from finale_file_parser.enigma.mus_payload import (
    MAX_MUS_PAYLOAD,
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    ByteOrder,
    MusPool,
)

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
    "identify_pools",
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

    Ask this of the pools **as read**. `identify_pools` fills in every missing
    `kind`, so calling this on its output can only ever answer `ERA_DCL` -- the
    question it asks has already been erased by then.
    """
    return ERA_DCL if pools and pools[0].kind is not None else ERA_ZLIB


def _int(value: int, size: int, order: ByteOrder) -> bytes:
    return value.to_bytes(size, order)


def write_pool_file(pools: tuple[MusPool, ...], *, era: int) -> bytes:
    """Frame `pools` as one file.

    Raises:
        ValueError: a pool has no `kind`, there are too many pools, or the
            pools disagree about their byte order. An unidentified pool is
            refused rather than written with a guessed label -- a wrong kind in
            this header sends a reader to the wrong record shape and everything
            after it is confident nonsense.
    """
    if not pools:
        raise ValueError("no pools to write")
    if len(pools) > _MAX_POOLS:
        raise ValueError(f"{len(pools)} pools exceeds the {_MAX_POOLS} this format allows")
    if era not in (ERA_ZLIB, ERA_DCL):
        raise ValueError(f"unknown era {era!r}")

    order: ByteOrder = pools[0].byte_order
    if any(pool.byte_order != order for pool in pools):
        # The header states one order for the whole file, so a disagreement
        # cannot be written down -- only silently resolved in favour of the
        # first pool, which is how the rest of the chain would then be misread.
        raise ValueError("pools disagree about their byte order; the header states only one")
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
    if data[5] not in (0, 1):
        raise CorruptScoreError(f"pool file names an unknown byte order {data[5]}")
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


def identify_pools(pools: tuple[MusPool, ...]) -> tuple[MusPool, ...]:
    """Fill in the `kind` of pools whose container did not label them.

    A DCL container names all four pools; a 2011-era one names none. The kinds
    are recoverable anyway, because each reader already carries a test for
    "is this my pool?" and uses it to pick a stream:

    - `mus_others._walk` returns None unless the stream is an others pool.
    - `mus_details._walk` returns None unless it is a details pool.
    - `mus_entries._looks_like_entry_pool` is the same test for entries.

    Measured over all 99 zlib-era corpus documents: others, details and entries
    identify positively in 99 of 99, with no stream matching two tests. The
    fourth pool is the text pool **by elimination** -- there is no positive test
    for it -- which agrees with the order the DCL container states outright
    (15, 16, 17, 18).

    That is why the elimination is only allowed once. If two pools were left
    unidentified the fourth would be a coin toss, and a wrong kind here is not a
    missing label: it points a reader at the wrong record shape and every field
    after it reads as confident nonsense.

    Raises:
        CorruptScoreError: more than one pool could not be identified, or two
            tests claimed the same pool.
    """
    from finale_file_parser.enigma import mus_details, mus_others
    from finale_file_parser.enigma.mus_entries import _looks_like_entry_pool

    if all(pool.kind is not None for pool in pools):
        return pools

    out: list[MusPool] = []
    unknown: list[int] = []
    for index, pool in enumerate(pools):
        if pool.kind is not None:
            out.append(pool)
            continue
        others = mus_others._walk(pool.data)
        details = mus_details._walk(pool.data)
        claims = []
        if others is not None and len(others) >= mus_others._MIN_RECORDS:
            claims.append(POOL_OTHERS)
        if details is not None and len(details) >= mus_details._MIN_RECORDS:
            claims.append(POOL_DETAILS)
        if _looks_like_entry_pool(pool.data, pool.byte_order):
            claims.append(POOL_ENTRIES)
        if len(claims) > 1:
            raise CorruptScoreError(
                f"pool {index} matches {len(claims)} pool tests, so neither can be trusted"
            )
        if claims:
            out.append(MusPool(data=pool.data, byte_order=pool.byte_order, kind=claims[0]))
            continue
        unknown.append(len(out))
        out.append(pool)

    if len(unknown) > 1:
        raise CorruptScoreError(
            f"{len(unknown)} pools could not be identified; only one may be inferred"
        )
    for index in unknown:
        pool = out[index]
        out[index] = MusPool(data=pool.data, byte_order=pool.byte_order, kind=POOL_TEXT)
    return tuple(out)
