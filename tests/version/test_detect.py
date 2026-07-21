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
    return (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        f"<fileInfo><modified><platform>MAC</platform>{app_version}</modified></fileInfo>"
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
    metadata = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><created><platform>MAC</platform>"
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
