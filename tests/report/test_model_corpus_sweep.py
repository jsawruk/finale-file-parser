"""Corpus-wide checks on the inspection model.

A sweep: it reads every `.mus` in the corpus. The model's own behaviour is
covered in `test_model.py`, which needs no corpus for most of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.mus_details import ENTRY_DETAIL_TAGS, read_mus_details
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


_REFERENCE_DOCUMENTS = 10
"""How many `.mus` documents carrying entry-keyed details this sweep inspects.

A constant, and small. The join is the same code on every document, so the
eleventh says little the first ten did not, and an inspection each is by far
the most expensive thing in this file.
"""


def _with_entry_details(limit: int) -> list[Path]:
    """Up to `limit` corpus paths whose raw details pool names an entry.

    Chosen by reading the raw pool, which costs a fraction of an inspection: 99
    of the 137 `.mus` documents qualify but they are not the first 99, so
    inspecting in path order would spend most of its budget on documents with
    no reference to check.
    """
    wanted = set(ENTRY_DETAIL_TAGS.values())
    chosen: list[Path] = []
    for path in sorted(CORPUS.rglob("*.mus")):
        try:
            details = read_mus_details(path)
        except FinaleFileError:
            continue
        if any(record.tag in wanted for record in details):
            chosen.append(path)
        if len(chosen) >= limit:
            break
    return chosen


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_every_mus_entry_reference_either_selects_a_row_or_says_it_cannot() -> None:
    """The `.mus` "named by" click-through, against real documents.

    A synthetic record cannot catch this on its own: the manual check that
    passed before the join was fixed passed because the entry it clicked had no
    references at all. So this asks every reference in ten real documents the
    one question that matters -- does the row you point at exist in the tree
    this same report rendered -- and requires that a good many of them do,
    which is what fails if the join stops resolving.

    Counts only. No filename, title or record value leaves this function.
    """
    documents = _with_entry_details(_REFERENCE_DOCUMENTS)
    assert len(documents) == _REFERENCE_DOCUMENTS, "corpus holds too few documents to sweep"

    resolved = 0
    unselectable = 0
    missing = 0
    for path in documents:
        inspection = model.inspect_document(path, engrave_notation=False)
        rendered = set()
        details = inspection.records.get("details")
        if isinstance(details, dict):
            for tag, entries in details.items():
                for entry in entries:
                    rendered.add((str(tag), str(entry["key"])))

        for facts in inspection.entry_index.values():
            assert isinstance(facts, dict)
            for reference in facts["named_by"]:
                tree_tag = reference["tree_tag"]
                tree_key = reference["tree_key"]
                if tree_tag is None or tree_key is None:
                    unselectable += 1
                elif (tree_tag, tree_key) in rendered:
                    resolved += 1
                else:
                    missing += 1

    assert missing == 0, f"{missing} references name a row the records tree never rendered"
    assert resolved > 0, f"no reference resolved ({unselectable} unselectable); the join is dead"
