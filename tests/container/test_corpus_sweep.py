"""Sweep the full local corpus through the container reader.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted
third-party material and is gitignored; these assertions are the only check
against real archives. Expected values come from
docs/superpowers/specs/2026-07-21-musx-container-design.md.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from finale_file_parser.container.musx import SCORE_NAME, open_musx

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401
EXPECTED_VARIANTS = 22
MIN_MEMBERS, MAX_MEMBERS_OBSERVED = 5, 10


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_archive_opens_and_enumerates() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES
    for path in paths:
        with open_musx(path) as container:
            assert MIN_MEMBERS <= len(container.entries) <= MAX_MEMBERS_OBSERVED, path
            assert container.entries[0].name == "mimetype", path
            assert container.entries[0].compress_type == zipfile.ZIP_STORED, path


def test_every_archive_yields_a_score_stream_of_declared_length() -> None:
    paths = _archives()
    assert paths
    for path in paths:
        with zipfile.ZipFile(path) as raw:
            declared = raw.getinfo(SCORE_NAME).file_size
        with open_musx(path) as container:
            assert len(container.score_stream()) == declared, path


def test_corpus_still_has_the_expected_number_of_ordered_variants() -> None:
    shapes = set()
    for path in _archives():
        with zipfile.ZipFile(path) as raw:
            shapes.add(tuple(i.filename for i in raw.infolist()))
    assert len(shapes) == EXPECTED_VARIANTS


def test_no_corpus_archive_trips_a_safety_limit() -> None:
    # None of the defences fire on real files. If this ever fails, either the
    # corpus gained a hostile file or a cap is too tight — investigate before
    # loosening anything.
    paths = _archives()
    assert paths
    opened = 0
    for path in paths:
        with open_musx(path):
            opened += 1
    assert opened == EXPECTED_ARCHIVES
