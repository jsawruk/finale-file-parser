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
    ERA_DCL,
    ERA_ZLIB,
    era_of,
    identify_pools,
    read_pool_file,
    write_pool_file,
)

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


def test_every_document_frames_and_reads_back() -> None:
    """The round trip is the guard. A framing bug that shifted a payload by one
    byte would still produce a valid file of the right size.

    The era in the header is asserted against the *container's own* labelling,
    not against whatever the writer was handed: a DCL container labels its pools
    and a 2011-era one labels none, and `identify_pools` fills every label in --
    so `era_of` asked after identification can only ever answer DCL. Both eras
    are counted, because an assertion only one era reaches would have called
    that DCL-for-everything.
    """
    framed = 0
    by_era = {ERA_ZLIB: 0, ERA_DCL: 0}
    for path in corpus_paths(".mus")[:120]:
        try:
            raw = read_mus_pools(path)
            pools = identify_pools(raw)
        except Exception:  # noqa: BLE001 -- container failures are other sweeps' business
            continue
        stated = ERA_DCL if raw[0].kind is not None else ERA_ZLIB
        data = write_pool_file(pools, era=era_of(raw))
        back = read_pool_file(data)
        assert back.era == stated, "the header's era is not the one the container states"
        assert len(back.pools) == len(pools), "pool count changed across the round trip"
        for before, after in zip(pools, back.pools, strict=True):
            assert after.kind == before.kind
            assert after.data == before.data
            assert after.byte_order == before.byte_order
        framed += 1
        by_era[stated] += 1
    assert framed >= 100, f"only {framed} documents framed; the sweep is not exercising much"
    assert by_era[ERA_ZLIB] >= 60, f"only {by_era[ERA_ZLIB]} 2011-era documents framed"
    assert by_era[ERA_DCL] >= 25, f"only {by_era[ERA_DCL]} DCL-era documents framed"


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
