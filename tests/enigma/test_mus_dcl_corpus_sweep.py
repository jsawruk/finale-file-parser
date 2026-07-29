"""Sweep every 2001-2005 `.mus` file through the pool container and entry reader.

Skipped wherever corpus/ is absent (e.g. CI). These files have **no paired
`.musx`** -- not one of the 139 has a stem match -- so every number here is an
internal-consistency check rather than a comparison against ground truth. What
makes them evidence rather than "it parsed":

* the pool records must tile the file from 0x200 to its last byte with no gap
  and no overlap, and the four kinds must come out (15, 16, 17, 18) in order;
* the entry slots must tile their pool exactly, every entry carrying SETBIT;
* every duration must decode as a note value with dots -- and across 70,428
  entries only sixteen distinct EDU values occur, every one of them musical.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_details import read_mus_details
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.mus_others import read_mus_others
from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    read_mus_pools,
)
from finale_file_parser.enigma.music import duration_from_edu
from finale_file_parser.version import mus as mus_header

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

LAST_DCL_YEAR = 2005

EXPECTED_DOCUMENTS = 139
"""Banner year <= 2005. That is 58% of the 238-file `.mus` corpus, and until
this container was decoded none of it opened past its first pool."""

EXPECTED_LITTLE_ENDIAN = 102
EXPECTED_BIG_ENDIAN = 37
"""Windows and Mac. The split is per document and comes from the container's
first record, not from the banner."""

EXPECTED_EMPTY_ENTRY_POOLS = 3
"""Three documents carry a six-byte entry record: the pool is there and empty."""

EXPECTED_ENTRY_POOLS_READ = 137
EXPECTED_ENTRIES = 70_428
"""Entries decoded from the 137 documents whose pool reads end to end."""

EXPECTED_DURATION_FAILURES = 2
"""Two documents hold a breve (8192 EDU) or a dotted whole (6144).

`duration_from_edu` caps at 4096, so it rejects both -- a limit of the note-value
model, not of this container: a dotted whole note is ordinary notation and a
`.musx` holding one would fail the same way. Pinned here so that fixing it shows
up as this number falling to 0.
"""

MIN_DISTINCT_DURATIONS = 12
"""A wrong decode would smear EDU across hundreds of arbitrary values."""


def _mus_files() -> list[Path]:
    """Case-insensitive: `.mus` and `.MUS` both occur, and a case-sensitive glob
    drops the entire Windows cohort -- which is most of this era."""
    return sorted(p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".mus")


def _dcl_files() -> list[Path]:
    out = []
    for path in _mus_files():
        year = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE]).year
        if year is not None and year <= LAST_DCL_YEAR:
            out.append(path)
    return out


def test_the_dcl_cohort_is_the_expected_size() -> None:
    """Guards the sweeps below: a shrunken corpus must not silently pass."""
    assert len(_dcl_files()) == EXPECTED_DOCUMENTS


def test_every_dcl_file_tiles_into_four_labelled_pools() -> None:
    """The container walk is exact by construction -- each record's declared
    length advances the walk, and the last must land on the final byte.

    So a file that reads at all has tiled; what this pins is that all 139 do,
    and that the kinds are the same four in the same order every time.
    """
    kinds: Counter[tuple[int | None, ...]] = Counter()
    orders: Counter[str] = Counter()
    failures: list[str] = []
    for path in _dcl_files():
        try:
            pools = read_mus_pools(path)
        except Exception as exc:  # noqa: BLE001 - collecting, not suppressing
            failures.append(type(exc).__name__)
            continue
        kinds[tuple(pool.kind for pool in pools)] += 1
        orders[pools[0].byte_order] += 1

    assert not failures, f"{len(failures)} of {EXPECTED_DOCUMENTS} failed: {failures[:5]}"
    assert kinds == Counter(
        {(POOL_OTHERS, POOL_DETAILS, POOL_ENTRIES, POOL_TEXT): EXPECTED_DOCUMENTS}
    )
    assert orders["little"] == EXPECTED_LITTLE_ENDIAN
    assert orders["big"] == EXPECTED_BIG_ENDIAN


def test_every_dcl_entry_pool_reads_as_typed_music() -> None:
    """The music itself. Durations are the check that carries the weight.

    Sixteen distinct EDU values over 70,428 entries, each decoding to a note
    value with 0-2 dots, is not something a wrong byte order or a wrong slot
    stride produces -- both scatter EDU across arbitrary values, and both would
    show up here as a flood of duration failures rather than two.
    """
    read = empty = 0
    durations: Counter[int] = Counter()
    other_failures: list[str] = []
    duration_failures = 0
    for path in _dcl_files():
        try:
            entries = read_mus_entries(path)
        except CorruptScoreError as exc:
            if "bad duration" in str(exc):
                duration_failures += 1
            else:
                other_failures.append(str(exc)[-60:])
            continue
        read += 1
        if not entries:
            empty += 1
        for entry in entries:
            durations[entry.duration.edu] += 1

    assert not other_failures, f"unexpected failures: {other_failures[:3]}"
    assert duration_failures == EXPECTED_DURATION_FAILURES
    assert read == EXPECTED_ENTRY_POOLS_READ
    assert empty == EXPECTED_EMPTY_ENTRY_POOLS
    assert sum(durations.values()) == EXPECTED_ENTRIES
    assert len(durations) >= MIN_DISTINCT_DURATIONS
    for edu in durations:
        assert duration_from_edu(edu).dots <= 2


def test_the_dcl_record_pools_are_refused_rather_than_half_read() -> None:
    """A 2001-2005 `others`/`details` pool is a different record encoding.

    It is reachable now, which is exactly why this has to be pinned: the walks
    in `mus_others`/`mus_details` are handed four pools each and must accept
    none of them. One that half-walked would hand `read_mus_document` a
    document made of fabricated records instead of raising.
    """
    others_accepted = details_accepted = 0
    for path in _dcl_files():
        try:
            read_mus_others(path)
        except CorruptScoreError:
            pass
        else:
            others_accepted += 1
        try:
            read_mus_details(path)
        except CorruptScoreError:
            pass
        else:
            details_accepted += 1
    assert others_accepted == 0
    assert details_accepted == 0
