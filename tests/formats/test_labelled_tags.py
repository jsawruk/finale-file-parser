"""Tags named by the text in their own payloads.

The claim each of these makes is narrow and checkable: a record of this tag
contains these words. So the test reads the corpus and checks exactly that,
rather than trusting the catalogue to describe itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.mus_rows import read_mus_rows
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.formats.tags import LABELLED, TAG_NAMES, name_for

CORPUS = Path(__file__).parent.parent.parent / "corpus"

# One string that must appear in a record of each tag, quoted from the payloads.
# Deliberately not taken from `description`: a test that reads its expectation
# out of the thing under test proves only that the string was copied twice.
EVIDENCE = {
    "DL": "General MIDI",
    "FN": "Maestro",
    "RT": "D.C. al Fine",
    "fI": "Standard Guitar",
    "fg": "Triad",
    "ft": "Seville",
    "DN": "Acoustic Bass Drum",
}


def test_every_labelled_tag_states_its_evidence() -> None:
    labelled = [e for e in TAG_NAMES if e.tier == LABELLED]
    assert {e.tag for e in labelled} == set(EVIDENCE)
    for entry in labelled:
        assert entry.documents > 0, f"^{entry.tag} names no documents"
        assert entry.description, f"^{entry.tag} quotes no text"


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


def test_a_labelled_name_is_not_mistaken_for_a_decoding() -> None:
    """It says what a record holds and nothing about where its fields sit, so
    nothing may quietly promote it to the tier that does."""
    entry = name_for("others", "RT")
    assert entry is not None
    assert entry.tier == LABELLED

    from finale_file_parser.formats.layouts import layout_for

    assert layout_for("others", "RT") is None, "no payload layout is claimed for it"
