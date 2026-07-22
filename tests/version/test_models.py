import pytest

from finale_file_parser.version.models import (
    AppVersion,
    Confidence,
    Family,
    FileVersion,
    FinaleFileError,
    MusDetail,
    MusxDetail,
    NotFinaleFileError,
    ProvenanceStamp,
)


def test_details_are_frozen() -> None:
    detail = MusDetail(banner="Finale(R) 2011", year=2011)
    with pytest.raises(AttributeError):
        detail.year = 2012  # type: ignore[misc]


def test_file_version_holds_family_specific_detail() -> None:
    musx = MusxDetail(
        created=None,
        modified=ProvenanceStamp(
            year=2015,
            month=11,
            day=23,
            application="FIN",
            platform="MAC",
            app_version=AppVersion(major=18, maint=5, dev_status="dev", build=7098),
        ),
        metadata_schema="18.0",
    )
    version = FileVersion(
        family=Family.MUSX,
        label="18.5 dev (build 7098)",
        confidence=Confidence.EXACT,
        detail=musx,
    )
    assert version.detail is musx
    assert version.confidence is Confidence.EXACT


def test_not_finale_file_error_is_a_finale_file_error() -> None:
    assert issubclass(NotFinaleFileError, FinaleFileError)
