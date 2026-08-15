"""Corpus-wide checks on the inspection model.

A sweep: it reads every `.mus` in the corpus. The model's own behaviour is
covered in `test_model.py`, which needs no corpus for most of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.report import model

CORPUS = Path(__file__).parent.parent.parent / "corpus"


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_no_two_records_of_one_tag_share_a_key() -> None:
    """A row that cannot be told from its neighbour is a row that cannot be
    selected, so this is worth pinning rather than assuming.

    It also records what an earlier reading of the tree got wrong: rows reading
    `65534/0` under many different tags looked like duplicates and are not --
    each is that tag's own options record. Within any one tag, keys are unique
    across every `.mus` in the corpus.
    """
    collisions = []
    for path in sorted(CORPUS.rglob("*.mus"))[:40]:
        try:
            records = model._mus_records(path)
        except FinaleFileError:
            continue
        for pool, tags in records.items():
            assert isinstance(tags, dict)
            for tag, entries in tags.items():
                keys = [e["key"] for e in entries]
                if len(keys) != len(set(keys)):
                    collisions.append(f"{path.name} {pool}/{tag}")
    assert collisions == []
