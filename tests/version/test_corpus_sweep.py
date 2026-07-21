"""Sweep the full local corpus. Skipped wherever corpus/ is absent (e.g. CI).

The corpus is copyrighted third-party material and is gitignored; these
assertions are the regression net against 639 real files without committing any
of them. Expected tallies come from
docs/superpowers/specs/2026-07-21-version-detection-design.md.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from finale_file_parser import Confidence, Family, detect_version

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_MUS = {
    "Finale 2001": 102,
    "Finale 2004": 1,
    "Finale 2005": 36,
    "Finale 2011": 89,
    "Finale 2012": 10,
}
EXPECTED_MUSX_COUNT = 401


def _files(suffix: str) -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == suffix]


def test_every_mus_file_detects_exactly() -> None:
    tally: collections.Counter[str] = collections.Counter()
    for path in _files(".mus"):
        result = detect_version(path)
        assert result.family is Family.MUS, path
        assert result.confidence is Confidence.EXACT, path
        tally[result.label] += 1
    assert dict(tally) == EXPECTED_MUS


def test_every_musx_file_detects_exactly() -> None:
    paths = _files(".musx")
    assert len(paths) == EXPECTED_MUSX_COUNT
    for path in paths:
        result = detect_version(path)
        assert result.family is Family.MUSX, path
        assert result.confidence is Confidence.EXACT, path


def test_every_musx_reports_schema_18() -> None:
    for path in _files(".musx"):
        detail = detect_version(path).detail
        assert getattr(detail, "metadata_schema", None) == "18.0", path


def test_directory_names_are_not_trusted_as_version_labels() -> None:
    # holiday_tunes_2013/ holds Finale 2012 files — the banner is the truth.
    mislabelled = [p for p in _files(".mus") if "holiday_tunes_2013" in str(p)]
    if mislabelled:
        assert all(detect_version(p).label == "Finale 2012" for p in mislabelled)
