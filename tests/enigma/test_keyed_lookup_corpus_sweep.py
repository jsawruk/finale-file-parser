"""Sweep the full local corpus asserting keyed-identity uniqueness and round-trip lookup.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted third-party
material and is gitignored; these assertions are the only check against real archives.

The index build IS the uniqueness check: OptionsPool/OthersPool/DetailsPool/EntriesPool/
TextsPool each raise MalformedEnigmaError on any duplicate full identity at construction
time. So the core assertion here is that all 401 archives parse without raising -- that
alone proves zero duplicate identities across every real record in the local corpus.

Alongside that, this drives a positive round-trip sampled from each parsed document
(never a hardcoded value): entries.get(entnum) and details.for_entry(...) return the
exact record that produced that identity, and a real measSpec with a part is exercised
through both get(..., part=...) and all_with() (the linked-part case against real data).

Report counts only -- never a corpus filename, title, composer, or record text value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401
# Round-trip checks are O(1) dict lookups -- cheap next to decode+parse -- but cap the
# per-archive sample so the sweep's cost stays dominated by parsing, not by lookups.
SAMPLED_PER_POOL_PER_ARCHIVE = 25


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_all_archives_parse_with_unique_identities_and_round_trip_lookup() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    parsed = 0
    entries_round_tripped = 0
    details_by_entry_round_tripped = 0
    options_round_tripped = 0
    texts_round_tripped = 0
    meas_spec_part_round_tripped = False

    for path in paths:
        # Parsing itself is the uniqueness check: a duplicate full identity in any pool
        # raises MalformedEnigmaError here, at index-build time.
        doc = parse_enigma(score_xml(path))
        parsed += 1

        for entry in doc.entries.of_tag("entry")[:SAMPLED_PER_POOL_PER_ARCHIVE]:
            entnum = entry.attrs.get("entnum")
            assert entnum is not None, path
            assert doc.entries.get(entnum) is entry, path
            entries_round_tripped += 1

        for detail in doc.details.records[:SAMPLED_PER_POOL_PER_ARCHIVE]:
            entnum = detail.attrs.get("entnum")
            if entnum is None:
                continue
            inci = detail.attrs.get("inci", "0")
            part = detail.attrs.get("part")
            assert doc.details.for_entry(detail.tag, entnum, inci=inci, part=part) is detail, path
            details_by_entry_round_tripped += 1

        for option in doc.options.records[:SAMPLED_PER_POOL_PER_ARCHIVE]:
            assert doc.options.get(option.tag) is option, path
            options_round_tripped += 1

        for text in doc.texts.records[:SAMPLED_PER_POOL_PER_ARCHIVE]:
            number = text.attrs.get("number")
            type_ = text.attrs.get("type")
            assert doc.texts.get(text.tag, number=number, type=type_) is text, path
            texts_round_tripped += 1

        if not meas_spec_part_round_tripped:
            for meas_spec in doc.others.of_tag("measSpec"):
                part = meas_spec.attrs.get("part")
                if part is None:
                    continue
                cmper = meas_spec.attrs["cmper"]
                assert doc.others.get("measSpec", cmper, part=part) is meas_spec, path
                variants = doc.others.all_with("measSpec", cmper)
                assert any(r is meas_spec for r in variants), path
                meas_spec_part_round_tripped = True
                break

    assert parsed == EXPECTED_ARCHIVES
    assert entries_round_tripped > 0, "no entries were round-tripped across the sweep"
    assert options_round_tripped > 0, "no options were round-tripped across the sweep"
    assert texts_round_tripped > 0, "no texts were round-tripped across the sweep"
    assert details_by_entry_round_tripped > 0, (
        "no entnum-keyed details were round-tripped across the sweep"
    )
    assert meas_spec_part_round_tripped, "no measSpec with a part was exercised across the sweep"
