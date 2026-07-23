"""Sweep the full local corpus through parse_enigma(score_xml(path)).

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted
third-party material and is gitignored; these assertions are the only check
against real archives.

Report counts only -- never a corpus filename, title, composer, or record
text value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import Record, parse_enigma
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_archive_parses_into_a_versioned_document_with_the_full_model_reached() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    pools_seen_nonempty: set[str] = set()
    reached_nested_note = False
    reached_meas_spec_part = False

    for path in paths:
        doc = parse_enigma(score_xml(path))

        assert doc.version == "18.0", path

        for name, pool in (
            ("header", doc.header),
            ("mappings", doc.mappings),
            ("options", doc.options),
            ("others", doc.others),
            ("details", doc.details),
            ("entries", doc.entries),
            ("texts", doc.texts),
        ):
            if pool.records:
                pools_seen_nonempty.add(name)

        if not reached_nested_note:
            for entry in doc.entries.of_tag("entry"):
                note = entry.fields.get("note")
                if isinstance(note, Record) or (
                    isinstance(note, tuple) and note and isinstance(note[0], Record)
                ):
                    reached_nested_note = True
                    break

        if not reached_meas_spec_part:
            for meas_spec in doc.others.of_tag("measSpec"):
                if "part" in meas_spec.attrs:
                    reached_meas_spec_part = True
                    break

    assert pools_seen_nonempty == {
        "header",
        "mappings",
        "options",
        "others",
        "details",
        "entries",
        "texts",
    }, f"pools never seen non-empty across the sweep: {pools_seen_nonempty}"
    assert reached_nested_note, "no entry with a nested note field was reached across the sweep"
    assert reached_meas_spec_part, "no measSpec with a part attribute was reached across the sweep"
