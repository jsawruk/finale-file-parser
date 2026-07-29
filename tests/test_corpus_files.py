"""The corpus walk finds both spellings of a legacy suffix.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import pytest
from corpus_files import CORPUS, corpus_paths

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


def test_the_walk_finds_both_spellings_of_mus() -> None:
    """`rglob("*.mus")` is case sensitive on a POSIX path and misses the whole
    Windows cohort. Asserting both spellings are present -- rather than a total
    -- says what the walk is for, and fails on the glob that used to be here.
    """
    suffixes = {path.suffix for path in corpus_paths(".mus")}
    assert ".mus" in suffixes
    assert ".MUS" in suffixes


def test_the_walk_returns_only_the_suffix_asked_for() -> None:
    """`.mus` and `.musx` share a prefix; a sloppier match would conflate them."""
    assert {p.suffix.lower() for p in corpus_paths(".mus")} == {".mus"}
    assert {p.suffix.lower() for p in corpus_paths(".musx")} == {".musx"}
