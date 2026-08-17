"""The complete case-insensitive corpus evidence behind `labelled` tag names."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from corpus_files import corpus_paths

from finale_file_parser.enigma.mus_rows import read_mus_rows
from finale_file_parser.formats.tags import LABELLED, TAG_NAMES
from finale_file_parser.version import mus as mus_header

from .test_labelled_tags import EVIDENCE

CORPUS = Path(__file__).parent.parent.parent / "corpus"
pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_DOCUMENTS = 139
EXPECTED_RECORDS = {
    "DL": 1_282,
    "DN": 18_647,
    "FN": 1_239,
    "RT": 1_253,
    "fI": 1_110,
    "fg": 2_884,
    "ft": 281,
}


@dataclass
class Reading:
    documents: int = 0
    carrying: Counter[str] = field(default_factory=Counter)
    records: Counter[str] = field(default_factory=Counter)
    evidence: Counter[str] = field(default_factory=Counter)
    offset_seen: Counter[str] = field(default_factory=Counter)
    ragged: list[str] = field(default_factory=list)


@pytest.fixture(scope="module")
def reading() -> Reading:
    out = Reading()
    labelled = {entry.tag for entry in TAG_NAMES if entry.tier == LABELLED}
    offsets = {entry.tag: entry.text_at for entry in TAG_NAMES if entry.text_at is not None}
    for path in corpus_paths(".mus"):
        detail = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE])
        if detail.year is None or detail.year > 2005:
            continue
        out.documents += 1
        rows = read_mus_rows(path)
        found: set[str] = set()
        for record in (*rows.others.values(), *rows.details.values()):
            if record.tag not in labelled:
                continue
            found.add(record.tag)
            out.records[record.tag] += 1
            needle = EVIDENCE[record.tag].encode("latin-1")
            out.evidence[record.tag] += int(needle in record.payload)

            at = offsets.get(record.tag)
            if at is None or len(record.payload) <= at:
                continue
            body = record.payload[at:]
            end = body.find(b"\x00")
            name = body if end < 0 else body[:end]
            if not name or not all(32 <= byte < 127 for byte in name):
                out.ragged.append(f"{record.tag} at +{at}: {name[:16]!r}")
            else:
                out.offset_seen[record.tag] += 1
        out.carrying.update(found)
    return out


def test_the_label_census_reads_every_dcl_document(reading: Reading) -> None:
    assert reading.documents == EXPECTED_DOCUMENTS


def test_the_payloads_really_carry_the_text_the_catalogue_quotes(reading: Reading) -> None:
    missing = [tag for tag, count in reading.evidence.items() if count == 0]
    assert missing == [], f"no corpus record of {missing} carries the text claimed for it"


def test_every_labelled_tag_states_its_measured_document_count(reading: Reading) -> None:
    stated = {entry.tag: entry.documents for entry in TAG_NAMES if entry.tier == LABELLED}
    assert stated == dict(reading.carrying)


def test_the_labelled_record_counts_are_stable(reading: Reading) -> None:
    assert dict(reading.records) == EXPECTED_RECORDS


def test_the_name_offset_lands_on_readable_text(reading: Reading) -> None:
    """A wrong offset would show a cut-off name or bytes preceding the text."""
    offsets = {entry.tag for entry in TAG_NAMES if entry.text_at is not None}
    assert not reading.ragged, f"the stated offset does not land on text: {reading.ragged[:5]}"
    assert set(reading.offset_seen) == offsets
