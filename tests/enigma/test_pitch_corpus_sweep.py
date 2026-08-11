"""Sweep the full local corpus, spelling every note into written and concert pitch.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted third-party
material and is gitignored; these assertions are the only check against real archives.

The core assertion is a genuine invariant, not the spelling definition: a key
transposition must preserve scale degree, so each concert pitch's printed accidental
(alteration minus the concert key's accidental for its letter) must equal the note's
original harm_alt. For a concert (non-transposing) staff this is trivially true, so
the assertion is a real check only on the transposing-staff subset (~50,024 of the
~234,000 notes swept); every note, transposing or not, is still checked to spell
without raising. This was verified to hold with 0 violations over those
transposing-staff notes during design; any mismatch here is a real defect in
transpose_key/transpose_pitch, not a reason to loosen the assertion.

Report counts only -- never a corpus filename, pitch name, lyric, or text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.key import decode_key
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.pitch import StaffTransposition, read_transposition, spell_note
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401

# Independent reconstruction of the key-accidental rule (NOT imported from pitch, so a
# bug there is caught rather than mirrored).
_SHARP_ORDER = "FCGDAEB"
_FLAT_ORDER = "BEADGCF"


def _printed_accidental(letter: str, alteration: int, fifths: int) -> int:
    if fifths > 0 and letter in _SHARP_ORDER[:fifths]:
        key_acc = 1
    elif fifths < 0 and letter in _FLAT_ORDER[:-fifths]:
        key_acc = -1
    else:
        key_acc = 0
    return alteration - key_acc


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_corpus_note_spells_and_preserves_scale_degree() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    notes_spelled = 0
    transposing_notes_checked = 0
    for path in paths:
        doc = parse_enigma(score_xml(path))
        location = locate_entries(doc)
        for entry_record in doc.entries.of_tag("entry"):
            entnum = int(entry_record.attrs["entnum"])
            placed = location.get(entnum)
            if not placed:
                continue
            # any placement will do: key comes from the measure, and a mirror's
            # placements all sit in the same measure
            concert_key = decode_key(placed[0].key_signature)
            staff_spec = doc.others.get("staffSpec", placed[0].staff)
            transposition = (
                read_transposition(staff_spec)
                if staff_spec is not None
                else StaffTransposition(0, 0)
            )
            for note in read_entry(entry_record).notes:
                spelled = spell_note(note, concert_key, transposition)
                printed = _printed_accidental(
                    spelled.concert.letter, spelled.concert.alteration, concert_key.fifths
                )
                assert printed == note.harm_alt
                notes_spelled += 1
                if not transposition.is_concert:
                    transposing_notes_checked += 1

    assert notes_spelled > 0
    assert transposing_notes_checked > 0
