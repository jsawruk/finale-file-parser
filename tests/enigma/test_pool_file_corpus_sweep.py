"""Framing every corpus document and reading it back.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    read_mus_pools,
)
from finale_file_parser.enigma.pool_file import (
    era_of,
    identify_pools,
    read_pool_file,
    write_pool_file,
)

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


def test_every_document_frames_and_reads_back() -> None:
    """The round trip is the guard. A framing bug that shifted a payload by one
    byte would still produce a valid file of the right size."""
    framed = 0
    for path in corpus_paths(".mus")[:120]:
        try:
            pools = identify_pools(read_mus_pools(path))
        except Exception:  # noqa: BLE001 -- container failures are other sweeps' business
            continue
        data = write_pool_file(pools, era=era_of(pools))
        back = read_pool_file(data)
        assert len(back.pools) == len(pools), "pool count changed across the round trip"
        for before, after in zip(pools, back.pools, strict=True):
            assert after.kind == before.kind
            assert after.data == before.data
            assert after.byte_order == before.byte_order
        framed += 1
    assert framed >= 100, f"only {framed} documents framed; the sweep is not exercising much"


def test_the_unlabelled_era_is_identified_not_guessed() -> None:
    """A 2011-era container labels no pool. Three of the four are identifiable
    by the readers' own walks, and the fourth is the text pool by elimination --
    so if a document ever fails to identify those three, the file is refused
    rather than written with a guess."""
    checked = 0
    for path in corpus_paths(".mus")[:120]:
        try:
            raw = read_mus_pools(path)
        except Exception:  # noqa: BLE001
            continue
        if raw[0].kind is not None:
            continue  # a DCL container states its kinds
        kinds = {pool.kind for pool in identify_pools(raw)}
        assert {POOL_OTHERS, POOL_DETAILS, POOL_ENTRIES} <= kinds
        checked += 1
    assert checked >= 30, f"only {checked} unlabelled-era documents checked"
