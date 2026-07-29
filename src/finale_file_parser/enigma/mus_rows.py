"""Read the `others` and `details` pools of a 2001-2005 `.mus` file.

That era stores them as **fixed 16-byte rows carrying ETF's two-character
tags**, not as the 2011 era's self-identifying variable-length records
(`enigma.mus_others`). Layout, in the document's byte order:

    others    0-1   cmper       the `(n)` in an ETF `^XX(n)`
              2-3   tag         two characters, stored as a u16
              4-15  12 bytes    ETF's "6 twobyte values (or 3 fourbytes)"

    details   0-1   cmper1
              2-3   cmper2
              4-5   tag
              6-15  10 bytes    ETF's "5 twobytes"

A record too big for one row **runs on into further rows under the same tag and
key**. `docs/etfspec.pdf` calls each row an *incidence* and says so outright:
"If a structure cannot fit into one other or detail there are multiple
incidences of the tag and comparator(s) to satisfy the structure size." So a
record's payload is its rows' data concatenated, in file order, and a reader
addresses fields by offset into that -- exactly as it does for a 2011 record.

**The tag is a u16, not two bytes.** On a little-endian file its characters come
out reversed: `^MS` is written `SM`, `^&a` is written `a&`. Reading the pair
verbatim finds no known tag in 102 of the 139 corpus documents, which is how
this was noticed.

Rows are grouped by tag and each tag's rows are contiguous and sorted, matching
ETF's own ordering. Nothing here depends on that, and nothing here decodes a
payload: what a record's bytes mean depends on its tag, and that lives in
`enigma.mus_document`.

Verified across all 139 DCL-era corpus documents; see
`docs/formats/mus-dcl-container.md`.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_OTHERS,
    ByteOrder,
    read_mus_pools,
)

__all__ = ["MusRowRecord", "MusRows", "read_mus_rows"]

_ROW = 16
_OTHERS_DATA = 4
"""cmper (2) + tag (2) precede an `others` row's data."""
_DETAILS_DATA = 6
"""cmper1 (2) + cmper2 (2) + tag (2) precede a `details` row's data."""

_MAX_ROWS = 1_000_000
"""Bound the walk. The corpus maximum is 9,148 rows in one pool."""

_MAX_INCIDENCES = 4096
"""Refuse a record claiming more rows than any real one has.

The corpus maximum is 30. The cap only has to keep one runaway key from
accumulating an unbounded payload; it is set far above real records.
"""


@dataclass(frozen=True)
class MusRowRecord:
    """One logical record: its key, and its incidences' data concatenated."""

    tag: str
    """The two-character ETF tag, in reading order (`MS`, `IS`, `FR`, ...)."""

    cmper: int
    cmper2: int = 0
    """Always 0 for an `others` record, which has one comparator."""

    payload: bytes = b""
    """Every incidence's data, in file order. 12 bytes per `others` incidence,
    10 per `details` incidence."""

    incidences: int = 0
    """How many rows made this record. The layout of some records depends on it
    -- an `IS` is three incidences in a 2001 file and six in a 2005 one."""


@dataclass(frozen=True)
class MusRows:
    """A DCL-era document's two record pools, keyed as ETF keys them."""

    others: dict[tuple[str, int], MusRowRecord] = field(default_factory=dict)
    details: dict[tuple[str, int, int], MusRowRecord] = field(default_factory=dict)
    byte_order: ByteOrder = "little"


def read_mus_rows(path: str | os.PathLike[str]) -> MusRows:
    """Return the `others` and `details` records of the `.mus` file at `path`.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode, the container does not
            label its pools, or a pool is not a whole number of rows.
    """
    pools = {pool.kind: pool for pool in read_mus_pools(path)}
    if POOL_OTHERS not in pools or POOL_DETAILS not in pools:
        raise CorruptScoreError(
            f"{path} has no labelled record pools; only a 2001-2005 container names them"
        )
    order = pools[POOL_OTHERS].byte_order
    return MusRows(
        others={
            (record.tag, record.cmper): record
            for record in _walk(pools[POOL_OTHERS].data, order, _OTHERS_DATA, "others")
        },
        details={
            (record.tag, record.cmper, record.cmper2): record
            for record in _walk(pools[POOL_DETAILS].data, order, _DETAILS_DATA, "details")
        },
        byte_order=order,
    )


def _tag(pair: bytes, order: ByteOrder) -> str:
    """The two characters of an ETF tag, which is stored as a u16."""
    return (pair if order == "big" else pair[::-1]).decode("latin-1")


def _walk(pool: bytes, order: ByteOrder, data_at: int, what: str) -> list[MusRowRecord]:
    """Every record in `pool`, rows under one key merged in file order."""
    if len(pool) % _ROW:
        raise CorruptScoreError(
            f"the {what} pool is {len(pool)} bytes, not a whole number of {_ROW}-byte rows"
        )
    if len(pool) // _ROW > _MAX_ROWS:
        raise CorruptScoreError(f"the {what} pool claims more than {_MAX_ROWS} rows; refusing")

    keys: list[tuple[str, int, int]] = []
    chunks: defaultdict[tuple[str, int, int], list[bytes]] = defaultdict(list)
    for start in range(0, len(pool), _ROW):
        row = pool[start : start + _ROW]
        cmper = int.from_bytes(row[0:2], order)
        cmper2 = int.from_bytes(row[2:4], order) if data_at == _DETAILS_DATA else 0
        key = (_tag(row[data_at - 2 : data_at], order), cmper, cmper2)
        if key not in chunks:
            keys.append(key)
        if len(chunks[key]) >= _MAX_INCIDENCES:
            raise CorruptScoreError(
                f"a {what} record claims more than {_MAX_INCIDENCES} incidences; refusing"
            )
        chunks[key].append(row[data_at:])
    return [
        MusRowRecord(
            tag=tag,
            cmper=cmper,
            cmper2=cmper2,
            payload=b"".join(chunks[(tag, cmper, cmper2)]),
            incidences=len(chunks[(tag, cmper, cmper2)]),
        )
        for tag, cmper, cmper2 in keys
    ]
