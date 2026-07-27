"""Read the `others` pool out of a legacy `.mus` file.

The pool is a flat run of **self-identifying, variable-length records**. Each
carries its own key, so nothing outside the record is needed to address it — no
directory, no key array, no positional convention. Layout, little-endian:

    0-1    tag       record type (numeric; `.musx` names the same types)
    2-3    cmper     the `(n)` in an ETF `^XX(n)` — the record's key
    4-5    part      0 for the score, then 1, 2, ... per linked part
    6-9    length    payload size in bytes
    10-    payload   `length` bytes, then four bytes of trailer

so one record occupies `14 + length` bytes. Records of one tag sit together in a
section; sections may be separated by two-byte zero padding, which the walk skips.

Why this took so long to see: every earlier attempt anchored on a payload field
found by searching for values already known from the paired `.musx`, then read
*forward*. The key sits ten bytes **behind** that anchor, so it was never in
view. Two near-misses came from reading the neighbouring record's header as if
it belonged to the anchored one; see `docs/formats/mus-binary-notes.md`.

Verified against paired `.musx` files (84 documents, 219,463 records): the tag
146 (`frameSpec`) key sequence matches exactly in 78 of 79 truly-paired
documents and its `startEntry`/`endEntry` payload in 7,975 of 7,978 records; the
tag 176 (`measSpec`) payload's width/beats/divbeat match in 4,546 of 4,595.

Scope: the 2011/2012 era, whose payload separates pools into their own zlib
streams. DCL-era files (2001-2005) pack everything into one stream with no known
pool delimiters, so this raises for them rather than guessing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import read_mus_streams

__all__ = [
    "OPTIONS_CMPER",
    "TAG_CLEF_OPTIONS",
    "TAG_FRAME_SPEC",
    "TAG_MEAS_SPEC",
    "TAG_STAFF_SPEC",
    "MusOther",
    "read_mus_others",
]

_HEADER = 10
"""tag (2) + cmper (2) + part (2) + length (4)."""
_TRAILER = 4
"""Four bytes follow every payload before the next record's header."""

TAG_FRAME_SPEC = 146
"""`frameSpec` — confirmed by payload, not only by key sequence."""
TAG_MEAS_SPEC = 176
"""`measSpec` — confirmed by payload, not only by key sequence."""

TAG_STAFF_SPEC = 231
"""`staffSpec` — confirmed by payload (rest offsets, staff lines, repeat-dot
offsets), not by key sequence."""

TAG_CLEF_OPTIONS = 109
"""The clef definition table — confirmed by payload.

An `others` record rather than a pool of its own: Enigma's document-wide options
live in this pool under the `OPTIONS_CMPER` sentinel, and `EnigmaDocument` keeps
them in `options` only because EnigmaXML puts them in a separate element.
"""

OPTIONS_CMPER = 0xFFFE
"""The cmper Enigma gives a document-wide option record rather than a real key.

98 records in a sampled document carry it, against the `.musx` options pool's
34: the `.mus` split is finer, so the two pools' record counts do not correspond.
"""

_PADDING = frozenset({0x0000, 0xFFFF})
"""Two-byte filler words that separate sections, skipped rather than parsed.

`0x0000` was always handled. **`0xFFFF` is filler too**, and missing that was
what stopped the walk on seven corpus documents: a run of `0xFFFF` words parses
as a record whose declared length is 0, so the walk fell four bytes short of the
next one each time and eventually landed mid-record. Treating it as filler lands
exactly on the next real record. No tag in either pool is 65535, and the format
already uses the same family of sentinels elsewhere (`OPTIONS_CMPER` is 0xFFFE).
"""

_MAX_PAYLOAD = 64 * 1024
"""Refuse a record claiming more than 64 KiB.

The largest payload in the corpus is 7,008 bytes, so this leaves ~9x headroom
while stopping a hostile length field from driving a large allocation.
"""

_MAX_RECORDS = 1_000_000
"""Refuse a stream claiming more records than any real document has.

The corpus maximum is 3,039. The cap only has to bound the walk; it is set far
above real documents so that no valid file trips it.
"""

_MIN_RECORDS = 50
"""Below this a clean walk is more likely coincidence than a real pool.

Used only to identify which stream is the `others` pool. Across the corpus no
stream other than the pool itself ever walks to its end at all, so the floor is
belt-and-braces rather than load-bearing.
"""


@dataclass(frozen=True)
class MusOther:
    """One `others` record, with its key and its payload verbatim.

    The payload is left undecoded: what its bytes mean depends on `tag`, and
    only `frameSpec` and `measSpec` are so far confirmed field-by-field.
    """

    tag: int
    cmper: int
    part: int
    payload: bytes


def read_mus_others(path: str | os.PathLike[str]) -> tuple[MusOther, ...]:
    """Return every `others` record in the `.mus` file at `path`, in pool order.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode, or no stream holds a
            recognisable `others` pool.
    """
    for stream in read_mus_streams(path):
        records = _walk(stream)
        if records is not None and len(records) >= _MIN_RECORDS:
            return records
    raise CorruptScoreError(
        f"{path} has no recognisable others pool "
        "(DCL-era files pack all pools into one stream; that is not yet supported)"
    )


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _walk(stream: bytes) -> tuple[MusOther, ...] | None:
    """Walk `stream` as a record pool, or None if it is not one.

    Returns None rather than raising: this doubles as the test for *which*
    stream is the pool, and the other streams are expected to fail it. A pool is
    recognised only when its records tile the stream exactly -- a partial walk
    is reported as "not a pool" rather than silently truncated, because a
    stream that stops parsing halfway is a stream we do not yet understand.
    """
    records: list[MusOther] = []
    position = 0
    while position + _HEADER <= len(stream):
        if _u16(stream, position) in _PADDING:
            position += 2
            continue
        length = _u32(stream, position + 6)
        end = position + _HEADER + length + _TRAILER
        if length > _MAX_PAYLOAD or end > len(stream):
            return None
        if len(records) >= _MAX_RECORDS:
            return None
        payload_at = position + _HEADER
        records.append(
            MusOther(
                tag=_u16(stream, position),
                cmper=_u16(stream, position + 2),
                part=_u16(stream, position + 4),
                payload=stream[payload_at : payload_at + length],
            )
        )
        position = end
    return tuple(records)
