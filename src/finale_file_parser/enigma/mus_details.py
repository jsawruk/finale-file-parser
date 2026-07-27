"""Read the `details` pool out of a legacy `.mus` file.

The same shape as the `others` pool (`mus_others.py`): a flat run of
self-identifying, variable-length records. It differs in exactly one way, and
for the obvious reason -- a `details` record is keyed by a *pair* of cmpers, so
its header carries one more field and is twelve bytes rather than ten:

    0-1    tag       record type (numeric; `.musx` names the same types)
    2-3    cmper1    first key component (staff, for `gfhold`)
    4-5    cmper2    second key component (measure, for `gfhold`)
    6-7    inci      incidence -- see the caveat on `MusDetailRecord.inci`
    8-11   length    payload size in bytes
    12-    payload   `length` bytes, then four bytes of trailer

so one record occupies `16 + length` bytes, against the `others` pool's
`14 + length`. Sections and two-byte zero padding work the same way.

`gfhold` (tag 1044) is the reason this pool matters: it is what ties a measure
on a staff to the entry frames that fill it. Its 20-byte payload:

    +0   clefID       0 means "the staff's `defaultClef`", which a `.musx`
                      export materialises into the record
    +4   clefPercent
    +6   frame1

Verified against paired `.musx` files across 80 documents: the `gfhold` key
sequence is the `.musx` sequence restricted to the keys `.mus` holds in 80 of
80, `clefPercent` matches in 8,382 of 8,382 records, `frame1` in 8,372 of
8,372, and `clefID` in 8,255 of 8,527 -- with every one of the other 272 being
the `defaultClef` case above, so none are unexplained.

Scope: the 2011/2012 era, as with the other `.mus` readers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import read_mus_streams

__all__ = ["MusDetailRecord", "TAG_GFHOLD", "TAG_TUPLET_DEF", "read_mus_details", "entry_key"]

_HEADER = 12
"""tag (2) + cmper1 (2) + cmper2 (2) + inci (2) + length (4)."""
_TRAILER = 4
"""Four bytes follow every payload before the next record's header."""

TAG_GFHOLD = 1044
"""`gfhold` -- confirmed by payload, not only by key sequence."""

TAG_TUPLET_DEF = 1072
"""`tupletDef` -- keyed by entry, not by a (staff, measure) pair. See `entry_key`."""

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

Matches the `others` reader's cap for the same reason: it bounds a hostile
length field while leaving ample room over any real record.
"""

_MAX_RECORDS = 1_000_000
"""Refuse a stream claiming more records than any real document has.

The corpus maximum is under 4,000. Set far above real documents so no valid
file trips it.
"""

_MIN_RECORDS = 50
"""Below this a clean walk is more likely coincidence than a real pool."""


@dataclass(frozen=True)
class MusDetailRecord:
    """One `details` record, with its key pair and its payload verbatim.

    `inci` is named by position: it sits exactly where Enigma's third key
    component belongs, and `DetailsPool` keys `.musx` records by
    (cmper1, cmper2, inci). **The identification is unconfirmed** -- the field
    is zero in all 77,384 corpus records examined, and no corpus document
    repeats a (tag, cmper1, cmper2) key, so nothing yet distinguishes an
    incidence counter from a reserved field.
    """

    tag: int
    cmper1: int
    cmper2: int
    inci: int
    payload: bytes


def entry_key(record: MusDetailRecord) -> int:
    """The 32-bit entry number a detail is attached to.

    Details that hang off an *entry* rather than a (staff, measure) reuse the two
    key fields as one number, **high word first**: `cmper1` is the top sixteen
    bits. Confirmed against the paired `.musx` on every `tupletDef` in the
    corpus; the little-endian reading matches none of them, so the order is not
    a guess.
    """
    return (record.cmper1 << 16) | record.cmper2


def read_mus_details(path: str | os.PathLike[str]) -> tuple[MusDetailRecord, ...]:
    """Return every `details` record in the `.mus` file at `path`, in pool order.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode, or no stream holds a
            recognisable `details` pool.
    """
    for stream in read_mus_streams(path):
        records = _walk(stream)
        if records is not None and len(records) >= _MIN_RECORDS:
            return records
    raise CorruptScoreError(
        f"{path} has no recognisable details pool "
        "(DCL-era files pack all pools into one stream; that is not yet supported)"
    )


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _walk(stream: bytes) -> tuple[MusDetailRecord, ...] | None:
    """Walk `stream` as a details pool, or None if it is not one.

    Returns None rather than raising, so this doubles as the test for *which*
    stream is the pool. The twelve-byte header is what separates the two pools:
    across the corpus the `others` stream never tiles under this rule, and this
    stream never tiles under the `others` rule. That is an empirical property
    of real pools, not a structural guarantee -- a stream of uniform
    zero-payload records satisfies both rules, since each reads its length out
    of the other's zeroed payload.
    """
    records: list[MusDetailRecord] = []
    position = 0
    while position + _HEADER <= len(stream):
        if _u16(stream, position) in _PADDING:
            position += 2
            continue
        length = _u32(stream, position + 8)
        end = position + _HEADER + length + _TRAILER
        if length > _MAX_PAYLOAD or end > len(stream):
            return None
        if len(records) >= _MAX_RECORDS:
            return None
        payload_at = position + _HEADER
        records.append(
            MusDetailRecord(
                tag=_u16(stream, position),
                cmper1=_u16(stream, position + 2),
                cmper2=_u16(stream, position + 4),
                inci=_u16(stream, position + 6),
                payload=stream[payload_at : payload_at + length],
            )
        )
        position = end
    return tuple(records)
