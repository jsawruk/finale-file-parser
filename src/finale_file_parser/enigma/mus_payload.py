"""Decode a legacy `.mus` file's compressed payload into its pools.

Two eras, two codecs, but the same idea: the payload is a handful of compressed
**pools**, not one blob.

    2001-2005  a chain of PKWARE DCL ("implode") records, first at 0x200
    2011-2012  a chain of zlib streams, first found by scanning for 78 9c

The DCL era labels its pools; the zlib era does not. A DCL chain is a run of
records, each

    0-1   kind      pool id: 15 others, 16 details, 17 entries, 18 text
    2-5   length    the whole record, this ten-byte header included
    6-9   checksum  (absent when the pool is empty -- see below)
    10-   a PKWARE DCL stream of `length - 10` bytes

laid end to end from 0x200 to the last byte of the file, with no gaps. A
`length` of exactly 6 means the pool is **empty**: the record is the kind and
the length and nothing else, no checksum and no stream. Three corpus documents
carry an empty entry pool that way.

`length` counts the header, so the chain is walked by adding it to the current
position -- which is also why the old fixed `0x20A` worked as "where the first
stream starts": it is 0x200 plus the ten-byte header.

**Byte order is the writing platform's**, big-endian on Mac and little-endian on
Windows, and it governs the pool records here and every field inside them. It is
read off the first record rather than assumed: that record's kind is always 15,
which is only 15 one way round. Over the corpus: 102 little-endian, 37
big-endian, all 139 walking to the last byte exactly.

Verified across the whole curated corpus: 139/139 DCL-era files tile exactly
with pool kinds (15, 16, 17, 18) and every non-empty pool decodes; 99/99
zlib-era files decode. See `docs/formats/mus-dcl-container.md` for how the
container was established and `docs/formats/mus-binary-notes.md` for the
offsets' stability.

This returns the decoded pool bytes. Parsing those into records is a separate,
later step, and the two eras do not share it: a 2011 pool is a run of
self-identifying variable-length records (`enigma.mus_others`), while a DCL pool
is a table of fixed 16-byte rows carrying ETF's two-character tags.
"""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass
from typing import Literal

from finale_file_parser.enigma.blast import CorruptDclStreamError, blast_decompress
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.version import mus as mus_header

__all__ = [
    "MAX_MUS_PAYLOAD",
    "POOL_DETAILS",
    "POOL_ENTRIES",
    "POOL_OTHERS",
    "POOL_TEXT",
    "ByteOrder",
    "MusPool",
    "read_mus_payload",
    "read_mus_pools",
    "read_mus_streams",
    "u16_le",
    "u32_le",
]


def u16_le(data: bytes, offset: int) -> int:
    """A little-endian `uint16` at `offset`.

    **Named for the byte order it assumes, because it does assume one.** The
    `others` and `details` pool readers both read their record headers this
    way regardless of the container's own byte order, and 37 corpus documents
    are big-endian -- so the assumption is worth seeing at the call site rather
    than buried in a two-line helper each module kept its own copy of.

    Whether fixed little-endian is right for those headers is not settled here:
    this is the behaviour those readers have always had, and the corpus sweeps
    pin what it produces. `mus_document` and `mus_entries` keep their own
    order-aware readers, which is the other half of the same open question.
    """
    return int.from_bytes(data[offset : offset + 2], "little")


def u32_le(data: bytes, offset: int) -> int:
    """A little-endian `uint32` at `offset`. See `u16_le`."""
    return int.from_bytes(data[offset : offset + 4], "little")


MAX_MUS_PAYLOAD = 64 * 1024 * 1024
"""Refuse output past 64 MiB, counted across the whole chain.

Measured over all 238 corpus files: a DCL chain inflates 3.25x-4.51x (median
3.56x) and the zlib chain 5.87x-8.63x (median 6.07x), with decoded payloads
running 32,816 to 699,585 bytes. The cap leaves ~90x headroom over the largest
real payload while still bounding a decompression bomb.
"""

ByteOrder = Literal["little", "big"]

POOL_OTHERS = 15
POOL_DETAILS = 16
POOL_ENTRIES = 17
POOL_TEXT = 18
"""The kinds a DCL-era container gives its four pools, in the order it writes them.

They line up with the roles the zlib era's four streams were found to play by
structure alone, which is what makes them believable as pool ids rather than as
some other counter: 15 walks as the `others` pool, 16 as `details`, 17 tiles as
38-byte entry slots, and 18 opens with `^block(1)`.
"""


@dataclass(frozen=True)
class MusPool:
    """One decompressed pool, with whatever the container says about it."""

    data: bytes

    byte_order: ByteOrder = "little"
    """The document's byte order, which every field inside `data` follows."""

    kind: int | None = None
    """The container's own pool id, or None where the container does not label
    its pools -- which is every zlib-era file. `None` means "ask the bytes",
    not "no pool"."""


_CONTAINER_START = 0x200
"""Where the first pool record sits. Constant across all 139 DCL-era files."""

_RECORD_HEADER = 10
"""kind (2) + length (4) + checksum (4)."""

_EMPTY_RECORD = 6
"""An empty pool's record: kind and length, with no checksum and no stream."""

_MAX_POOLS = 64
"""Bound the walk. Real files carry four; the cap only has to stop a runaway."""

_ZLIB_DEFLATE_METHOD = 8
_MIN_FIRST_STREAM_OUTPUT = 4096
"""How much the **first** stream must inflate to.

Nothing frames the first one -- it is found by scanning -- so a chance byte pair
that both looks like a zlib header and inflates could start the chain in the
wrong place and drag every later offset with it. The floor rejects those.

It applies to the first stream only. Applied to all of them it discarded the
entry pool of two corpus documents, short carols whose pools inflate to 3,268 and
2,394 bytes; each then read as three pools instead of four, with no entry pool
among them. See `_zlib_streams`."""


def _is_zlib_header(data: bytes, index: int) -> bool:
    """Is there a well-formed zlib header at `index`?

    Every corpus file uses `78 9c`, but matching that pair alone would miss any
    file written at a different compression level (`78 01`, `78 da`, ...). This
    applies zlib's actual rule instead: low nibble 8 for deflate, and the
    two-byte header a multiple of 31.
    """
    if index + 2 > len(data):
        return False
    cmf, flg = data[index], data[index + 1]
    return (cmf & 0x0F) == _ZLIB_DEFLATE_METHOD and ((cmf << 8) | flg) % 31 == 0


_LAST_DCL_YEAR = 2005
"""Banner years at or below this use PKWARE DCL; later years use zlib."""

_CHUNK = 1 << 20


def read_mus_pools(path: str | os.PathLike[str]) -> tuple[MusPool, ...]:
    """Return every decompressed pool of the `.mus` file at `path`, in file order.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode by either scheme.
    """
    with open(path, "rb") as handle:
        data = handle.read()
    detail = mus_header.parse(data[: mus_header.MUS_METADATA_SIZE])
    # An unknown banner year is not fatal: try both schemes rather than refusing
    # a variant we simply have not catalogued.
    if detail.year is not None and detail.year <= _LAST_DCL_YEAR:
        readers = (_dcl_pools, _zlib_pools)
    else:
        readers = (_zlib_pools, _dcl_pools)

    failures = []
    for reader in readers:
        try:
            return reader(data)
        except CorruptScoreError as exc:
            failures.append(str(exc))
    raise CorruptScoreError(f"{path} payload decoded by neither scheme: " + "; ".join(failures))


def read_mus_streams(path: str | os.PathLike[str]) -> list[bytes]:
    """Return the payload's pools individually, in file order.

    `read_mus_payload` concatenates these. Callers that need the pool boundaries
    -- the entries reader does -- need them apart, because each holds a
    different pool. Use `read_mus_pools` instead to get the container's own
    labelling and the document's byte order along with the bytes.
    """
    return [pool.data for pool in read_mus_pools(path)]


def read_mus_payload(path: str | os.PathLike[str]) -> bytes:
    """Return the whole decoded payload of the `.mus` file at `path`.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode by either scheme.
    """
    return b"".join(read_mus_streams(path))


def _container_byte_order(data: bytes) -> ByteOrder:
    """Which way round this file writes its integers.

    Decided by the first pool record's kind, which is `POOL_OTHERS` in every
    corpus file and reads as 15 exactly one way round -- 15 the other way is
    3840. So this is a check that a container is there at all as much as it is a
    byte-order test, which is why it raises rather than defaulting.
    """
    if len(data) < _CONTAINER_START + _EMPTY_RECORD:
        raise CorruptScoreError("file is too short to hold a pool container")
    head = data[_CONTAINER_START : _CONTAINER_START + 2]
    if int.from_bytes(head, "big") == POOL_OTHERS:
        return "big"
    if int.from_bytes(head, "little") == POOL_OTHERS:
        return "little"
    raise CorruptScoreError(
        f"no pool container at {_CONTAINER_START:#x}: "
        f"first record's kind is {head.hex()} either way round, not {POOL_OTHERS}"
    )


def _dcl_pools(data: bytes) -> tuple[MusPool, ...]:
    """Walk the chain of DCL pool records of a 2001-2005 file.

    The records tile the file from `_CONTAINER_START` to its last byte. A walk
    that would step past the end, or that declares a record too short to hold
    its own header, is refused rather than truncated: a chain that stops halfway
    is a file we do not understand, and half a document read as a whole one is
    worse than an error.
    """
    byte_order = _container_byte_order(data)
    pools: list[MusPool] = []
    position = _CONTAINER_START
    decoded = 0
    while position < len(data):
        if len(pools) >= _MAX_POOLS:
            raise CorruptScoreError(f"pool chain exceeds {_MAX_POOLS} records; refusing")
        if position + _EMPTY_RECORD > len(data):
            raise CorruptScoreError(f"pool record at {position} is truncated")
        kind = int.from_bytes(data[position : position + 2], byte_order)
        length = int.from_bytes(data[position + 2 : position + 6], byte_order)
        if length < _EMPTY_RECORD or position + length > len(data):
            raise CorruptScoreError(
                f"pool record at {position} declares length {length}, "
                f"which does not fit the remaining {len(data) - position} bytes"
            )
        if length == _EMPTY_RECORD:
            pools.append(MusPool(data=b"", byte_order=byte_order, kind=kind))
        else:
            if length < _RECORD_HEADER:
                raise CorruptScoreError(
                    f"pool record at {position} declares length {length}, "
                    f"too short for its {_RECORD_HEADER}-byte header"
                )
            # Sliced to the record, so a malformed stream cannot read on into
            # the next one and come back with a plausible-looking pool.
            stream = data[position + _RECORD_HEADER : position + length]
            try:
                payload = blast_decompress(stream, 0, MAX_MUS_PAYLOAD - decoded)
            except CorruptDclStreamError as exc:
                raise CorruptScoreError(
                    f"pool record at {position} (kind {kind}) did not decode: {exc}"
                ) from exc
            decoded += len(payload)
            pools.append(MusPool(data=payload, byte_order=byte_order, kind=kind))
        position += length
    if not pools:
        raise CorruptScoreError("pool container holds no records")
    return tuple(pools)


def _zlib_pools(data: bytes) -> tuple[MusPool, ...]:
    """The 2011/2012 chain of zlib streams, as pools.

    That container does not label its streams, so `kind` stays None and
    the readers identify a pool by walking it. Byte order is little-endian
    throughout that era -- no corpus file says otherwise.
    """
    return tuple(MusPool(data=stream, byte_order="little") for stream in _zlib_streams(data))


def _zlib_streams(data: bytes) -> list[bytes]:
    """Every zlib stream in `data`, in order. Raises if there are none.

    **The chain is framed, so only the first stream is searched for.** Each
    stream is followed by the same ten-byte record header the DCL container
    uses -- kind, length, checksum -- and then the next stream: the gap between
    one stream's end and the next one's start is exactly 10 bytes in 297 of the
    307 gaps across the 2011 corpus, and the ten exceptions are chance headers
    that a size floor was previously needed to reject.

    Following the framing instead of scanning finds four pools in **99 of 99**
    corpus documents. Scanning with a 4,096-byte floor found three in two of
    them, having discarded a small entry pool; scanning without one found
    spurious streams.

    The first stream is still located by scanning, because the preamble ahead of
    it is variable-length -- two corpus files start at 0x20A rather than the
    usual 0x216 -- and it alone must clear `_MIN_FIRST_STREAM_OUTPUT`.
    """
    out: list[bytes] = []
    total = 0
    start = _first_stream(data)
    position = 0 if start is None else start
    while start is not None and position < len(data) - 1:
        if not _is_zlib_header(data, position):
            break
        try:
            chunk, consumed = _inflate_bounded(data[position:], MAX_MUS_PAYLOAD - total)
        except (zlib.error, CorruptScoreError):
            break
        out.append(chunk)
        total += len(chunk)
        # Guard against a zero-width advance, which would loop forever.
        end = position + max(consumed, 1)
        # The framed position first, then the abutting one. Both are exact, so
        # neither can drift; and a real record header cannot be mistaken for a
        # zlib one, because its `kind` byte fails the deflate low-nibble test.
        position = next(
            (at for at in (end + _RECORD_HEADER, end) if _is_zlib_header(data, at)),
            len(data),
        )
    if not out:
        raise CorruptScoreError("no zlib stream found in payload")
    return out


def _first_stream(data: bytes) -> int | None:
    """Where the chain starts: the first header that inflates substantially.

    See `_MIN_FIRST_STREAM_OUTPUT` for why this one is held to a size and the
    rest are not.
    """
    position = 0
    while position < len(data) - 1:
        if _is_zlib_header(data, position):
            try:
                chunk, _ = _inflate_bounded(data[position:], MAX_MUS_PAYLOAD)
            except (zlib.error, CorruptScoreError):
                position += 1
                continue
            if len(chunk) >= _MIN_FIRST_STREAM_OUTPUT:
                return position
        position += 1
    return None


def _inflate_bounded(data: bytes, budget: int) -> tuple[bytes, int]:
    """Inflate one zlib stream from the front of `data`.

    Returns the output and how many input bytes the stream consumed, so the
    caller can advance to the next stream in the chain. The decompressor is
    created here rather than passed in: `zlib.decompressobj` is a factory
    function, not a type, so accepting one as a parameter would drag the private
    `zlib._Decompress` name into the signature.

    Incremental rather than one-shot: a single `decompress` call on untrusted
    input allocates the whole output before anything can object.
    """
    engine = zlib.decompressobj()
    out = bytearray()
    chunk = engine.decompress(data, _CHUNK)
    while chunk:
        out += chunk
        if len(out) > budget:
            raise CorruptScoreError(
                f"payload exceeds the {MAX_MUS_PAYLOAD}-byte inflation cap; refusing"
            )
        # Feed back `unconsumed_tail`, not b"": with a max_length set, the
        # remaining input is parked there, and passing b"" silently truncates
        # the output to a single chunk.
        chunk = engine.decompress(engine.unconsumed_tail, _CHUNK)
    return bytes(out), len(data) - len(engine.unused_data)
