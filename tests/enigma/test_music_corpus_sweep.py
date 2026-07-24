"""Sweep the full local corpus, reading every entry through the typed music model.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted third-party
material and is gitignored; these assertions are the only check against real archives.

Composes read_entry over every <entry> record in all 401 archives. The core assertion
is that every entry reads without raising -- a survey found the corpus 100% clean, so
any MalformedEntryError here is a real finding, not a reason to loosen an assertion.

Report counts only -- never a corpus filename, record value, pitch, or lyric.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401
WHOLE_NOTE_EDU = 4096


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_corpus_entry_reads_as_a_typed_entry() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    archives_read = 0
    entries_read = 0
    seen_rest = False
    seen_single_note = False
    seen_chord = False

    for path in paths:
        doc = parse_enigma(score_xml(path))
        archives_read += 1

        for record in doc.entries.of_tag("entry"):
            entry = read_entry(record)
            entries_read += 1

            assert entry.is_rest == (len(entry.notes) == 0), path
            # Validate the base+dots decode against real durations, not the
            # tautology whole_notes == edu/4096 (whole_notes IS that fraction).
            # base + each successive halved dot must reconstruct edu exactly.
            reconstructed = entry.duration.base.value
            addend = entry.duration.base.value
            for _ in range(entry.duration.dots):
                addend //= 2
                reconstructed += addend
            assert reconstructed == entry.duration.edu, path

            note_count = len(entry.notes)
            if note_count == 0:
                seen_rest = True
            elif note_count == 1:
                seen_single_note = True
            else:
                seen_chord = True

    assert archives_read == EXPECTED_ARCHIVES
    assert entries_read > 0, "no entries were read across the sweep"
    assert seen_rest, "no rest was seen across the sweep"
    assert seen_single_note, "no single-note entry was seen across the sweep"
    assert seen_chord, "no chord (>=2 notes) was seen across the sweep"
