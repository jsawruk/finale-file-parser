"""Decode a legacy `.mus` file's compressed payload.

Two eras, two codecs. Which one applies is decided by the banner year in the
plaintext header, then confirmed by actually decoding:

    2001-2005  PKWARE DCL ("implode") stream   at 0x20A, lit=0, dict=4
    2011-2012  chain of zlib streams           first at 0x216, found by 78 9c

Verified across the whole curated corpus: 139/139 old-cohort files and 99/99
new-cohort files decode. See `docs/formats/mus-binary-notes.md` for how this was
established and for the offsets' stability.

This returns the decoded payload bytes. Parsing those bytes into records is a
separate, later step -- the payload is not EnigmaXML and is not yet understood.
"""

from __future__ import annotations

import os
import zlib

from finale_file_parser.enigma.blast import CorruptDclStreamError, blast_decompress
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.version import mus as mus_header

__all__ = ["MAX_MUS_PAYLOAD", "read_mus_payload"]

MAX_MUS_PAYLOAD = 64 * 1024 * 1024
"""Refuse output past 64 MiB.

Measured over all 238 corpus files: DCL inflates 0.82x-2.75x (median 2.35x) and
the zlib chain 5.87x-8.63x (median 6.07x), with decoded payloads running
32,816 to 699,585 bytes. The cap leaves ~90x headroom over the largest real
payload while still bounding a decompression bomb.
"""

_DCL_OFFSET = 0x20A
"""Constant across all 139 old-cohort corpus files."""

_ZLIB_DEFLATE_METHOD = 8
_MIN_STREAM_OUTPUT = 4096
"""A real stream inflates to far more than this; the floor rejects byte pairs
that merely look like a zlib header, which occur a few times per file by chance."""


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


def read_mus_payload(path: str | os.PathLike[str]) -> bytes:
    """Return the decoded payload of the `.mus` file at `path`.

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
        order = (_read_dcl, _read_zlib_chain)
    else:
        order = (_read_zlib_chain, _read_dcl)

    failures = []
    for reader in order:
        try:
            return reader(data)
        except CorruptScoreError as exc:
            failures.append(str(exc))
    raise CorruptScoreError(f"{path} payload decoded by neither scheme: " + "; ".join(failures))


def _read_dcl(data: bytes) -> bytes:
    """Decode the single PKWARE DCL stream of a 2001-2005 file."""
    try:
        return blast_decompress(data, _DCL_OFFSET, MAX_MUS_PAYLOAD)
    except CorruptDclStreamError as exc:
        raise CorruptScoreError(f"DCL stream at {_DCL_OFFSET:#x} did not decode: {exc}") from exc


def _read_zlib_chain(data: bytes) -> bytes:
    """Decode the chain of consecutive zlib streams of a 2011-2012 file.

    Streams are located by their zlib header rather than a fixed offset: the
    preamble ahead of the first one is variable-length, and two corpus files
    start at 0x20A rather than the usual 0x216.
    """
    out = bytearray()
    position = 0
    while position < len(data) - 1:
        if not _is_zlib_header(data, position):
            position += 1
            continue
        index = position
        try:
            chunk, consumed = _inflate_bounded(data[index:], MAX_MUS_PAYLOAD - len(out))
        except (zlib.error, CorruptScoreError):
            # A byte pair that merely looks like a header; step past and go on.
            position = index + 1
            continue
        if len(chunk) < _MIN_STREAM_OUTPUT:
            position = index + 1
            continue
        out += chunk
        # Guard against a zero-width advance, which would loop forever.
        position = index + max(consumed, 1)
    if not out:
        raise CorruptScoreError("no zlib stream found in payload")
    return bytes(out)


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
