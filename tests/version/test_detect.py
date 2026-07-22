from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser import detect_version
from finale_file_parser.version.models import (
    Confidence,
    Family,
    MusDetail,
    MusxDetail,
    NotFinaleFileError,
)


def _metadata(app_version: str) -> str:
    # Every created/modified block in the 401-file corpus carries a date (802/802
    # blocks). A block without one cannot occur in a real .musx, so the date here
    # keeps this helper's input realistic; it is not asserted on by these tests.
    return (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><year>2020</year><month>1</month><day>1</day>"
        f"<platform>MAC</platform>{app_version}</modified></fileInfo>"
        "</metadata>"
    )


def test_detects_mus(write_mus: Callable[..., Path]) -> None:
    path = write_mus(b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.")
    result = detect_version(path)
    assert result.family is Family.MUS
    assert result.label == "Finale 2011"
    assert result.confidence is Confidence.EXACT
    assert isinstance(result.detail, MusDetail)


def test_unrecognised_mus_banner_is_unknown_not_an_error(
    write_mus: Callable[..., Path],
) -> None:
    path = write_mus(b"Finale(R) Future Edition")
    result = detect_version(path)
    assert result.confidence is Confidence.UNKNOWN
    assert result.label == "unknown version"
    assert isinstance(result.detail, MusDetail)
    assert result.detail.banner == "Finale(R) Future Edition"


def test_detects_musx(make_musx: Callable[..., Path]) -> None:
    path = make_musx(
        metadata=_metadata(
            "<appVersion><major>18</major><maint>5</maint>"
            "<devStatus>dev</devStatus><build>7098</build></appVersion>"
        )
    )
    result = detect_version(path)
    assert result.family is Family.MUSX
    assert result.label == "18.5 dev (build 7098)"
    assert result.confidence is Confidence.EXACT
    assert isinstance(result.detail, MusxDetail)


def test_musx_label_omits_absent_maint(make_musx: Callable[..., Path]) -> None:
    path = make_musx(
        metadata=_metadata(
            "<appVersion><major>16</major><devStatus>release</devStatus>"
            "<build>2</build></appVersion>"
        )
    )
    assert detect_version(path).label == "16 release (build 2)"


def test_musx_without_app_version_is_unknown(make_musx: Callable[..., Path]) -> None:
    path = make_musx(metadata=_metadata(""))
    result = detect_version(path)
    assert result.confidence is Confidence.UNKNOWN
    assert result.label == "unknown version"


def test_musx_prefers_modified_over_created(make_musx: Callable[..., Path]) -> None:
    # SAMPLE_METADATA (the default fixture metadata) deliberately encodes
    # conflicting versions: created = major 16, release, build 2; modified =
    # major 18, maint 5, dev, build 7098. Real-world corpora skew the same
    # way (most files are created by one major version and later modified by
    # a newer one), so `modified` must win whenever both are present.
    path = make_musx()
    result = detect_version(path)
    assert isinstance(result.detail, MusxDetail)
    assert result.detail.created is not None
    assert result.detail.modified is not None
    assert result.label == "18.5 dev (build 7098)"
    assert result.label != "16 release (build 2)"
    assert result.confidence is Confidence.EXACT


def test_musx_falls_back_to_created_when_modified_absent(
    make_musx: Callable[..., Path],
) -> None:
    # As in _metadata() above, the date is added here to keep the input realistic
    # (no real .musx block lacks one); it is not asserted on by this test.
    metadata = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><created><year>2011</year><month>3</month><day>4</day>"
        "<platform>MAC</platform>"
        "<appVersion><major>16</major><devStatus>release</devStatus>"
        "<build>2</build></appVersion></created></fileInfo>"
        "</metadata>"
    )
    path = make_musx(metadata=metadata)
    result = detect_version(path)
    assert isinstance(result.detail, MusxDetail)
    assert result.detail.created is not None
    assert result.detail.modified is None
    assert result.label == "16 release (build 2)"
    assert result.confidence is Confidence.EXACT


def test_rejects_non_finale_file(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_bytes(b"just some text, definitely not a score")
    with pytest.raises(NotFinaleFileError):
        detect_version(path)


def test_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.mus"
    path.write_bytes(b"")
    with pytest.raises(NotFinaleFileError):
        detect_version(path)


def test_rejects_file_truncated_inside_the_magic(tmp_path: Path) -> None:
    path = tmp_path / "truncated.mus"
    path.write_bytes(b"ENIGMA BIN")
    with pytest.raises(NotFinaleFileError):
        detect_version(path)


def test_accepts_mus_truncated_after_the_magic(tmp_path: Path) -> None:
    # Short but validly-magicked: report UNKNOWN rather than raising.
    path = tmp_path / "short.mus"
    path.write_bytes(b"ENIGMA BINARY FILE")
    result = detect_version(path)
    assert result.family is Family.MUS
    assert result.confidence is Confidence.UNKNOWN


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_version(tmp_path / "nope.mus")


def test_accepts_a_str_path(write_mus: Callable[..., Path]) -> None:
    path = write_mus(b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.")
    result = detect_version(str(path))
    assert result.family is Family.MUS
    assert result.label == "Finale 2011"
    assert result.confidence is Confidence.EXACT


def test_musx_app_version_without_a_date_is_unknown(make_musx: Callable[..., Path]) -> None:
    """A stamp requires a date, so an appVersion with no date yields no stamp at all.

    This input does not occur in real files: all 802 created/modified blocks across
    the 401-file corpus carry year/month/day. This test does not endorse the input as
    realistic — it pins the deliberate behaviour that a dateless block, even with a
    parseable appVersion, cannot produce a ProvenanceStamp.
    """
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><platform>MAC</platform>"
        "<appVersion><major>18</major><maint>5</maint>"
        "<devStatus>dev</devStatus><build>7098</build></appVersion>"
        "</modified></fileInfo></metadata>"
    )
    path = make_musx(metadata=metadata)
    result = detect_version(path)
    assert result.confidence is Confidence.UNKNOWN
    assert result.label == "unknown version"


def test_musx_modified_stamp_without_version_falls_back_to_created(
    make_musx: Callable[..., Path],
) -> None:
    """Regression test for the "fallback moved up a level" bug (final-review Finding 1,
    table row 1): `modified` has a date but no `appVersion`, so `musx._stamp` still
    builds a stamp for it (a stamp only requires a date, not a version) -- it is just a
    versionless one. The buggy selector (`detail.modified or detail.created`) picked
    that stamp merely because it was *present*, discarding `created`'s perfectly good
    version and reporting UNKNOWN. The correct behaviour -- confirmed by running the
    pre-unify-provenance code (which selected on `AppVersion` presence directly) on this
    same input -- is to fall back to `created`.
    """
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo>"
        "<created><year>2010</year><month>9</month><day>14</day><platform>MAC</platform>"
        "<appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>"
        "</created>"
        "<modified><year>2015</year><month>11</month><day>23</day><platform>WIN</platform></modified>"
        "</fileInfo></metadata>"
    )
    path = make_musx(metadata=metadata)
    result = detect_version(path)
    assert isinstance(result.detail, MusxDetail)
    assert result.detail.modified is not None  # a stamp exists...
    assert result.detail.modified.app_version is None  # ...but carries no version
    assert result.label == "16 release (build 2)"
    assert result.confidence is Confidence.EXACT


def test_musx_modified_missing_a_date_cannot_outrank_created(
    make_musx: Callable[..., Path],
) -> None:
    """Companion case to the test above (final-review Finding 1, table row 2):
    `modified` carries an `appVersion` but no date at all, while `created` has both.

    Unlike row 1, this shape is not reachable through `detect.py`'s stamp-selection
    fix: `musx._stamp` never builds a `ProvenanceStamp` for a block lacking a usable
    date, regardless of whether that block carries an `appVersion` -- the same
    protected rule pinned for the modified-only case by
    `test_musx_app_version_without_a_date_is_unknown` above. So `detail.modified` is
    `None` here before `detect.py`'s selection logic ever runs, and `created` wins
    whether that selection is the buggy `detail.modified or detail.created` or the
    corrected, version-aware form -- verified directly by swapping the two in.

    The pre-unify-provenance code (which read `AppVersion` straight off the block
    with no date requirement) would have reported `modified`'s version here --
    "18.5 dev (build 7098)" / EXACT. That value is not recoverable without loosening
    `musx._stamp`'s date requirement, which this fix must not do (it is a separately
    protected invariant, unrelated to the fallback-selection bug this branch fixes).
    This test pins the current, correct-given-that-invariant behaviour instead of
    asserting a value neither the buggy nor the fixed selector can produce.
    """
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo>"
        "<created><year>2010</year><month>9</month><day>14</day><platform>MAC</platform>"
        "<appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>"
        "</created>"
        "<modified><platform>WIN</platform>"
        "<appVersion><major>18</major><maint>5</maint><devStatus>dev</devStatus>"
        "<build>7098</build></appVersion></modified>"
        "</fileInfo></metadata>"
    )
    path = make_musx(metadata=metadata)
    result = detect_version(path)
    assert isinstance(result.detail, MusxDetail)
    assert result.detail.modified is None
    assert result.label == "16 release (build 2)"
    assert result.confidence is Confidence.EXACT


def test_musx_created_without_app_version_and_no_modified_is_unknown(
    make_musx: Callable[..., Path],
) -> None:
    """Guards `known = stamp is not None and stamp.app_version is not None` against
    regressing to `known = stamp is not None`.

    Before Finding 1's fix, `_musx_stamp`'s selection (`detail.modified or
    detail.created`) meant a lone versionless `modified` stamp (with no `created` at
    all) was itself the selected `stamp` -- `test_musx_without_app_version_is_unknown`
    above already covered that shape and would have caught a stamp-presence-only
    confidence computation. After the fix, that same shape instead falls through to
    `detail.created` (`None` here), so the existing test no longer exercises a
    non-`None`-but-versionless *selected* stamp. This case -- `created` present but
    versionless, `modified` absent entirely -- is the shape that now reaches that
    code path, restoring the mutation coverage.
    """
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><created><year>2010</year><month>9</month><day>14</day>"
        "<platform>MAC</platform></created></fileInfo></metadata>"
    )
    path = make_musx(metadata=metadata)
    result = detect_version(path)
    assert isinstance(result.detail, MusxDetail)
    assert result.detail.created is not None
    assert result.detail.created.app_version is None
    assert result.detail.modified is None
    assert result.confidence is Confidence.UNKNOWN
    assert result.label == "unknown version"
