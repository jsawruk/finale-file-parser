"""The report re-walks a join `locate_entries` already walks. This is what
stops the two drifting.

The duplication is deliberate -- `locate_entries` raises on exactly the
documents a diagnostic report exists for, so the report needs a walk that does
not. What it must not do is disagree about a document they can both read.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.report import entry_facts
from finale_file_parser.report.entry_facts import (
    build_entry_index,
    decode_entry,
    placements_by_entry,
)

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

DOCUMENTS = 60
"""Documents read from each container.

The walk is the same code on every document, so this is sized to be wide enough
to reach both containers and the malformed cohort, and cheap enough not to move
the gate: `--dist loadfile` means the suite can never finish faster than its
slowest single test, and that is another sweep by a wide margin (~444s against
~30s for each test here).
"""


def _documents() -> Iterator[EnigmaDocument]:
    """Corpus documents from both containers, skipping the ones that will not
    read at all -- container failures are other sweeps' business.

    **Both containers, because only one of them exercises the reason this file
    exists.** `locate_entries` accepts every one of the 401 corpus `.musx`
    documents, so a `.musx`-only sweep would assert nothing about the tolerant
    walk's own case; the `.mus` cohort holds a document it refuses, and the
    report has to answer for exactly that document.
    """
    for path in corpus_paths(".musx")[:DOCUMENTS]:
        try:
            yield parse_enigma(score_xml(path))
        except Exception:  # noqa: BLE001 -- container failures are other sweeps' business
            continue
    for path in corpus_paths(".mus")[:DOCUMENTS]:
        try:
            yield read_mus_document(path)
        except Exception:  # noqa: BLE001
            continue


def test_the_report_walk_agrees_with_locate_entries() -> None:
    """Same entries, same (staff, measure, layer), same count -- wherever
    `locate_entries` accepts the document at all."""
    compared = 0
    for document in _documents():
        try:
            expected = locate_entries(document)
        except Exception:  # noqa: BLE001 -- no oracle for a document it refuses
            continue
        placements, _ = placements_by_entry(document)
        theirs = {
            entnum: sorted((p.staff, p.measure, p.layer) for p in places)
            for entnum, places in expected.items()
        }
        ours = {
            entnum: sorted((p.staff, p.measure, p.layer) for p in places)
            for entnum, places in placements.items()
        }
        assert ours == theirs, "the report's walk disagrees with locate_entries"
        compared += 1
    assert compared >= 100, f"only {compared} documents compared; the sweep is not exercising much"


def test_the_index_never_raises_anywhere_in_the_corpus() -> None:
    """Including the documents `locate_entries` refuses, which is the whole
    reason the report has its own walk."""
    built = refused_by_locate = 0
    for document in _documents():
        try:
            locate_entries(document)
        except Exception:  # noqa: BLE001
            refused_by_locate += 1
        build_entry_index(document)  # must not raise, for either kind
        built += 1
    assert built >= 100
    # If this ever reads zero the sweep has stopped testing its own premise --
    # every document it saw was one `locate_entries` could read, so nothing here
    # exercised the tolerant walk. Widen the slice; do not delete the check.
    assert refused_by_locate >= 1, "no document in the slice is one locate_entries refuses"


def test_the_report_spells_with_the_key_locate_entries_resolved() -> None:
    """The report must not develop its own opinion of which key an entry is in.

    Spelling itself is not duplicated -- `entry_facts` calls `spell_note`, the
    same function `to_ir` calls -- so the two can only disagree about what they
    feed it, and that is what this pins: every entry is decoded a second time
    with the key `locate_entries` resolved for it, and must come out the same
    way the index has it.

    Two ways that can fail, both real. The index spells with the *first*
    placement's key, so a walk that ordered a mirrored entry's placements
    differently would spell the entry in the other staff's key while still
    agreeing with `locate_entries` about the set of places it sits in -- the
    first sweep sorts, so only this one can see that. And the key lookup itself
    is plumbing the report owns: feeding the wrong measure's key changes 262 of
    the spellings in twenty documents, measured by shifting it one measure.

    This placement comparison is only pinned here where an entry has a single
    placement: exactly 1 of 632 corpus documents places any entry more than
    once (239 such entries, at most 2 placements each), and it falls outside
    the documents this sweep walks. The first-placement rule for a genuinely
    mirrored entry is pinned synthetically instead, by
    `test_a_mirrored_entry_spells_from_the_first_placement` in
    `tests/report/test_entry_facts.py`.

    The transposition is taken from the report's own table on purpose. It is the
    other input to spelling, and holding it fixed is what leaves the key as the
    only thing this can be measuring.
    """
    documents = entries = 0
    for document in _documents():
        try:
            located = locate_entries(document)
        except Exception:  # noqa: BLE001 -- no oracle for a document it refuses
            continue
        index = build_entry_index(document)
        transpositions = entry_facts._transpositions(document)
        records = {
            entry_facts._as_int(record.attrs.get("entnum")): record
            for record in document.entries.of_tag("entry")
        }
        for entnum, places in located.items():
            facts = index.get(str(entnum))
            if facts is None or facts.decode is None or not facts.placements:
                continue
            first, theirs = facts.placements[0], places[0]
            assert (first.staff, first.measure, first.layer) == (
                theirs.staff,
                theirs.measure,
                theirs.layer,
            ), "the report and locate_entries put a different placement first"
            assert facts.decode == decode_entry(
                records[entnum], theirs.key_signature, transpositions.get(theirs.staff)
            ), "the report spelled this entry in a different key than locate_entries resolved"
            entries += 1
        documents += 1
    assert documents >= 100, f"only {documents} documents compared"
    assert entries >= 20_000, f"only {entries} entries compared"
