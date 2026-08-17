"""Pin percussion usage without mistaking Finale's palette for score content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from corpus_files import corpus_paths

from finale_file_parser.enigma.document import field_int, parse_enigma
from finale_file_parser.enigma.percussion import percussion_notes
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"
pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


@dataclass
class Reading:
    archives: int = 0
    palette_rows: int = 0
    documents: int = 0
    assignments: int = 0
    unique_assignments: int = 0
    zero_based_identities: int = 0
    used: int = 0
    resolved: int = 0
    unresolved: int = 0


@pytest.fixture(scope="module")
def reading() -> Reading:
    out = Reading()
    for path in corpus_paths(".musx"):
        document = parse_enigma(score_xml(path))
        out.archives += 1
        out.palette_rows += len(document.others.of_tag("percussionNoteInfo"))
        assignments = document.details.of_tag("percussionNoteCode")
        if not assignments:
            continue
        out.documents += 1
        out.assignments += len(assignments)
        identities: set[tuple[int, int]] = set()
        for record in assignments:
            entnum = field_int(record.attrs.get("entnum"))
            inci = field_int(record.attrs.get("inci", "0"))
            note_id = field_int(record.fields.get("noteID"))
            assert entnum is not None and inci is not None and note_id is not None
            identities.add((entnum, note_id))
            out.zero_based_identities += int(inci == note_id - 1)
        out.unique_assignments += len(identities)
        for notes in percussion_notes(document).values():
            for note in notes:
                if note is None:
                    continue
                out.used += 1
                if note.appearance is None:
                    out.unresolved += 1
                else:
                    out.resolved += 1
    return out


def test_the_palette_is_not_mistaken_for_score_usage(reading: Reading) -> None:
    assert reading.archives == 401
    assert reading.palette_rows == 149_533
    assert reading.documents == 10
    assert reading.assignments == 4_692


def test_every_assignment_identity_is_unique_and_zero_based(reading: Reading) -> None:
    assert reading.unique_assignments == 4_692
    assert reading.zero_based_identities == 4_692


def test_only_selected_staff_maps_produce_percussion_notes(reading: Reading) -> None:
    assert reading.used == 605
    assert reading.resolved == 597
    assert reading.unresolved == 8
