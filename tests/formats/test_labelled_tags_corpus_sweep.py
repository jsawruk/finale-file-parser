"""The corpus evidence behind the `labelled` tag names.

A sweep: it reads every `.mus` in the corpus. The catalogue's own shape is
checked in `test_labelled_tags.py`, which needs no corpus and runs on every
edit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.mus_rows import read_mus_rows
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.formats.tags import name_for

from .test_labelled_tags import EVIDENCE

CORPUS = Path(__file__).parent.parent.parent / "corpus"


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_the_payloads_really_carry_the_text_the_catalogue_quotes() -> None:
    """The whole basis of this tier. If the words are not in the file, the name
    resting on them is worth nothing."""
    seen: dict[str, int] = dict.fromkeys(EVIDENCE, 0)
    for path in sorted(CORPUS.rglob("*.mus")):
        try:
            rows = read_mus_rows(path)
        except FinaleFileError:
            continue
        for pool in (rows.others, rows.details):
            for key, record in pool.items():
                needle = EVIDENCE.get(key[0])
                if needle and needle.encode("latin-1") in record.payload:
                    seen[key[0]] += 1

    missing = [tag for tag, count in seen.items() if count == 0]
    assert missing == [], f"no corpus record of {missing} carries the text claimed for it"


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_the_document_counts_are_not_overstated() -> None:
    """A count that drifts above the truth turns evidence into decoration."""
    found: dict[str, set[Path]] = {tag: set() for tag in EVIDENCE}
    for path in sorted(CORPUS.rglob("*.mus")):
        try:
            rows = read_mus_rows(path)
        except FinaleFileError:
            continue
        for pool in (rows.others, rows.details):
            for key in pool:
                if key[0] in found:
                    found[key[0]].add(path)

    for tag in EVIDENCE:
        entry = name_for("others", tag) or name_for("details", tag)
        assert entry is not None
        assert entry.documents <= len(found[tag]), (
            f"^{tag} claims {entry.documents} documents; {len(found[tag])} carry it"
        )
