"""Sweep the full local corpus through the EnigmaXML decoder.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted
third-party material and is gitignored; these assertions are the only check
against real archives. Expected values come from docs/formats/score-dat.md.

Report counts and sizes only -- never a corpus filename, title, or payload.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from finale_file_parser.container.musx import SCORE_NAME, open_musx
from finale_file_parser.enigma.crypt import RESET_EVERY
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401
MIN_INFLATED, MAX_INFLATED_OBSERVED = 2_481_759, 10_781_112
MIN_OVER_RESET_EVERY = 60
"""At least this many score.dat streams must exceed RESET_EVERY, so the sweep
genuinely exercises the keystream reset against real data. Observed: 68."""

SCHEMA_VERSION_RE = re.compile(rb'<finale\b[^>]*\bversion="([^"]*)"')


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def _score_dat_size(path: Path) -> int:
    with open_musx(path) as container:
        entry = next(e for e in container.entries if e.name == SCORE_NAME)
        return entry.size


def test_every_archive_decodes_to_versioned_finale_xml_in_range() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    over_reset_every = 0
    for path in paths:
        xml = score_xml(path)

        assert xml.startswith(b"<?xml"), path
        assert b"<finale" in xml, path

        match = SCHEMA_VERSION_RE.search(xml)
        assert match is not None, path
        assert match.group(1) == b"18.0", path

        assert MIN_INFLATED <= len(xml) <= MAX_INFLATED_OBSERVED, path

        if _score_dat_size(path) > RESET_EVERY:
            over_reset_every += 1

    assert over_reset_every >= MIN_OVER_RESET_EVERY
