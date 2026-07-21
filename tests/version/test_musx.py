import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser.version.models import NotFinaleFileError
from finale_file_parser.version.musx import MAX_METADATA_BYTES, read


def test_reads_created_and_modified(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx())
    assert detail.metadata_schema == "18.0"
    assert detail.created is not None
    assert detail.created.major == 16
    assert detail.created.maint is None
    assert detail.created.dev_status == "release"
    assert detail.modified is not None
    assert detail.modified.major == 18
    assert detail.modified.maint == 5
    assert detail.modified.build == 7098


def test_platform_comes_from_the_modifying_write(make_musx: Callable[..., Path]) -> None:
    assert read(make_musx()).platform == "WIN"


def test_rejects_zip_that_is_not_a_musx(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "not a score")
    with pytest.raises(NotFinaleFileError):
        read(path)


def test_rejects_wrong_mimetype(make_musx: Callable[..., Path]) -> None:
    with pytest.raises(NotFinaleFileError):
        read(make_musx(mimetype=b"application/zip"))


def test_missing_metadata_yields_empty_detail(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx(metadata=None))
    assert detail.created is None
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_malformed_xml_yields_empty_detail(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx(metadata="<metadata><unclosed>"))
    assert detail.modified is None


def test_missing_app_version_yields_none(make_musx: Callable[..., Path]) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><platform>MAC</platform></modified></fileInfo></metadata>"
    )
    detail = read(make_musx(metadata=metadata))
    assert detail.modified is None
    assert detail.platform == "MAC"


def test_refuses_oversized_metadata_member(make_musx: Callable[..., Path]) -> None:
    # A zip bomb: small compressed, enormous uncompressed.
    detail = read(make_musx(metadata="<a/>" + " " * (MAX_METADATA_BYTES + 1)))
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_resists_entity_expansion(make_musx: Callable[..., Path]) -> None:
    # "Billion laughs". defusedxml must refuse it rather than expanding.
    bomb = """<?xml version="1.0"?>
<!DOCTYPE metadata [
  <!ENTITY a "AAAAAAAAAA">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<metadata version="18.0">&c;</metadata>
"""
    detail = read(make_musx(metadata=bomb))
    assert detail.modified is None
