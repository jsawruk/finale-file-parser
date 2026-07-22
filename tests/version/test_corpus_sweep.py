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
from finale_file_parser.version.models import MusDetail, MusxDetail

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
EXPECTED_MUS_COUNT = 238
EXPECTED_MUS_MAC_COUNT = 136
EXPECTED_MUS_WIN_COUNT = 102
EXPECTED_MUSX_CREATED16_MODIFIED18_COUNT = 267
"""docs/ARCHITECTURE.md -- the current source of truth -- documents this as 267, matching
this direct corpus measurement. The 2026-07-21 design spec still reads 264: that was read off
a single row of a tally rather than measured, and the spec deliberately retains that original
figure with a dated (2026-07-22) correction note appended, per this project's practice of not
rewriting a spec's history. Pinned here to what the corpus actually shows, not the older figure."""
MIN_STAMP_YEAR, MAX_STAMP_YEAR = 1998, 2012


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
    paths = _files(".musx")
    assert len(paths) == EXPECTED_MUSX_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert getattr(detail, "metadata_schema", None) == "18.0", path


def test_directory_names_are_not_trusted_as_version_labels() -> None:
    # holiday_tunes_2013/ holds Finale 2012 files — the banner is the truth.
    mislabelled = [p for p in _files(".mus") if "holiday_tunes_2013" in str(p)]
    assert mislabelled, "No files found in holiday_tunes_2013 directory"
    assert all(detect_version(p).label == "Finale 2012" for p in mislabelled)


def test_every_mus_file_yields_both_provenance_stamps() -> None:
    """Pinned by the 2026-07-22 corpus survey: every one of the 238 .mus files
    carries both a created and a modified stamp. A corpus change that regresses
    this must update this test and docs/superpowers/specs/2026-07-22-mus-header-metadata-design.md
    together, deliberately -- not by silently loosening the assertion.
    """
    paths = _files(".mus")
    assert len(paths) == EXPECTED_MUS_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusDetail), path
        assert detail.created is not None, path
        assert detail.modified is not None, path


def test_every_mus_file_has_created_on_or_before_modified() -> None:
    paths = _files(".mus")
    assert len(paths) == EXPECTED_MUS_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusDetail), path
        created, modified = detail.created, detail.modified
        assert created is not None and modified is not None, path
        assert (created.year, created.month, created.day) <= (
            modified.year,
            modified.month,
            modified.day,
        ), path


def test_every_mus_stamp_reports_application_fin() -> None:
    paths = _files(".mus")
    assert len(paths) == EXPECTED_MUS_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusDetail), path
        created, modified = detail.created, detail.modified
        assert created is not None and modified is not None, path
        assert created.application == "FIN", path
        assert modified.application == "FIN", path


def test_mus_stamp_platform_tallies_exactly() -> None:
    """Platform is read from the created stamp of each file; per the design spec
    every corpus file's created and modified stamps agree on platform, but this
    tally is over the created stamp specifically so a future disagreement would
    change this count rather than being silently averaged away.
    """
    paths = _files(".mus")
    assert len(paths) == EXPECTED_MUS_COUNT
    tally: collections.Counter[str] = collections.Counter()
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusDetail), path
        assert detail.created is not None, path
        tally[detail.created.platform] += 1
    assert dict(tally) == {"MAC": EXPECTED_MUS_MAC_COUNT, "WIN": EXPECTED_MUS_WIN_COUNT}


def test_every_mus_stamp_year_is_in_the_observed_range() -> None:
    paths = _files(".mus")
    assert len(paths) == EXPECTED_MUS_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusDetail), path
        created, modified = detail.created, detail.modified
        assert created is not None and modified is not None, path
        assert MIN_STAMP_YEAR <= created.year <= MAX_STAMP_YEAR, path
        assert MIN_STAMP_YEAR <= modified.year <= MAX_STAMP_YEAR, path


def test_every_musx_file_yields_both_provenance_stamps() -> None:
    """Unified provenance parity with `.mus`: every one of the 401 `.musx` files carries
    both a created and a modified stamp, not only the platform/appVersion fields read
    before this change.
    """
    paths = _files(".musx")
    assert len(paths) == EXPECTED_MUSX_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusxDetail), path
        assert detail.created is not None, path
        assert detail.modified is not None, path


def test_every_musx_stamp_reports_a_non_empty_application() -> None:
    paths = _files(".musx")
    assert len(paths) == EXPECTED_MUSX_COUNT
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusxDetail), path
        created, modified = detail.created, detail.modified
        assert created is not None and modified is not None, path
        assert created.application, path
        assert modified.application, path


def test_musx_modified_over_created_divergence_still_holds() -> None:
    """`modified` remains the layout authority over `created` (see docs/ARCHITECTURE.md):
    a stable subset of corpus files were created by one `appVersion.major` and last
    modified by a later one. Tallied over the `app_version.major` carried by each stamp,
    not a bare `.major` on the detail, since that field now lives on the stamp.

    Alongside the 16-to-18 tally, this also asserts the broader 370-of-401 figure --
    archives where `created` and `modified` disagree on major at all, not only the
    16-to-18 case -- per docs/ARCHITECTURE.md and the 2026-07-22 unify-provenance design
    spec. Both figures are pinned as literals: a corpus change that moves either must
    update this test and those docs together, deliberately.
    """
    paths = _files(".musx")
    assert len(paths) == EXPECTED_MUSX_COUNT
    diverging = 0
    diverging_any_major = 0
    for path in paths:
        detail = detect_version(path).detail
        assert isinstance(detail, MusxDetail), path
        created, modified = detail.created, detail.modified
        assert created is not None and modified is not None, path
        created_major = created.app_version.major if created.app_version else None
        modified_major = modified.app_version.major if modified.app_version else None
        if created_major == 16 and modified_major == 18:
            diverging += 1
        if created_major != modified_major:
            diverging_any_major += 1
    assert diverging == EXPECTED_MUSX_CREATED16_MODIFIED18_COUNT
    assert diverging_any_major == 370
