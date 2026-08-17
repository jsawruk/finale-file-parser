"""Pin percussion usage without mistaking Finale's palette for score content."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from corpus_files import corpus_paths

from finale_file_parser.enigma.document import field_int, parse_enigma
from finale_file_parser.enigma.mus_percussion import dcl_percussion_maps
from finale_file_parser.enigma.mus_rows import read_mus_rows
from finale_file_parser.enigma.percussion import percussion_notes
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.version import mus as mus_header

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
    named_map_documents: int = 0
    named_maps: int = 0
    palette_maps: int = 0
    percussion_types: set[int] = field(default_factory=set)
    midi_range_percussion_types: int = 0
    code_type_agreements: int = 0
    dcl_documents: int = 0
    dcl_platform_orders: Counter[tuple[str, str]] = field(default_factory=Counter)
    dcl_maps: int = 0
    dcl_named_maps: int = 0
    dcl_entries: int = 0
    dcl_named_entries: int = 0
    dcl_input_playback_differences: int = 0


@pytest.fixture(scope="module")
def reading() -> Reading:
    out = Reading()
    for path in corpus_paths(".musx"):
        document = parse_enigma(score_xml(path))
        out.archives += 1
        palette = document.others.of_tag("percussionNoteInfo")
        out.palette_rows += len(palette)
        palette_maps = {field_int(record.attrs.get("cmper")) for record in palette}
        named_maps = {
            field_int(record.attrs.get("cmper")) for record in document.others.of_tag("drumLibName")
        }
        out.palette_maps += len(palette_maps)
        out.named_maps += len(named_maps)
        out.named_map_documents += int(palette_maps == named_maps)
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
                    percussion_type = note.appearance.percussion_type
                    out.percussion_types.add(percussion_type)
                    out.midi_range_percussion_types += int(0 <= percussion_type <= 127)
                    out.code_type_agreements += int(note.note_code == percussion_type)

    for path in corpus_paths(".mus"):
        detail = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE])
        if detail.year is None or detail.year > 2005:
            continue
        out.dcl_documents += 1
        rows = read_mus_rows(path)
        platform = detail.created.platform if detail.created is not None else ""
        out.dcl_platform_orders[(platform, rows.byte_order)] += 1
        for percussion_map in dcl_percussion_maps(rows):
            out.dcl_maps += 1
            out.dcl_named_maps += int(percussion_map.name is not None)
            out.dcl_entries += len(percussion_map.entries)
            for entry in percussion_map.entries:
                if entry.name is None:
                    continue
                out.dcl_named_entries += 1
                out.dcl_input_playback_differences += int(entry.input_note != entry.playback_note)
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


def test_every_musx_percussion_palette_map_has_its_name_record(reading: Reading) -> None:
    assert reading.named_map_documents == reading.archives == 401
    assert reading.named_maps == reading.palette_maps == 8_403


def test_dcl_percussion_names_join_to_their_map_entries(reading: Reading) -> None:
    assert reading.dcl_documents == 139
    assert reading.dcl_platform_orders == {("MAC", "big"): 37, ("WIN", "little"): 102}
    assert reading.dcl_named_maps == reading.dcl_maps == 1_282
    assert reading.dcl_entries == 74_730
    assert reading.dcl_named_entries == 18_647
    assert reading.dcl_input_playback_differences == 3_717


def test_used_musx_percussion_types_are_not_midi_notes_or_note_codes(reading: Reading) -> None:
    assert len(reading.percussion_types) == 2
    assert reading.midi_range_percussion_types == 0
    assert reading.code_type_agreements == 0
