"""Tags named by the text in their own payloads.

The claim each of these makes is narrow and checkable: a record of this tag
contains these words. These unit tests pin the catalogue contract; the complete
case-insensitive measurement lives in `test_labelled_tags_corpus_sweep.py`.
"""

from __future__ import annotations

from pathlib import Path

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


def test_a_name_offset_is_stated_only_where_it_is_constant() -> None:
    """`RT` has none deliberately because its text has no constant offset."""
    at = {e.tag: e.text_at for e in TAG_NAMES if e.tier == LABELLED}
    assert at == {"DL": 0, "DN": 0, "FN": 12, "fI": 12, "fg": 12, "ft": 84, "RT": None}


def test_every_labelled_tag_states_its_evidence() -> None:
    labelled = [e for e in TAG_NAMES if e.tier == LABELLED]
    assert {e.tag for e in labelled} == set(EVIDENCE)
    for entry in labelled:
        assert entry.documents > 0, f"^{entry.tag} names no documents"
        assert entry.description, f"^{entry.tag} quotes no text"


def test_a_labelled_name_is_not_mistaken_for_a_decoding() -> None:
    """It says what a record holds and nothing about where its fields sit, so
    nothing may quietly promote it to the tier that does."""
    entry = name_for("others", "RT")
    assert entry is not None
    assert entry.tier == LABELLED

    from finale_file_parser.formats.layouts import layout_for

    assert layout_for("others", "RT") is None, "no payload layout is claimed for it"
