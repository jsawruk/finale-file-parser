import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser.container.musx import MAX_MEMBERS
from finale_file_parser.version.models import NotFinaleFileError
from finale_file_parser.version.musx import MAX_METADATA_BYTES, METADATA_NAME, read

_VALID_METADATA = (
    '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
    "<fileInfo><modified>"
    "<platform>WIN</platform>"
    "<appVersion><major>18</major><maint>5</maint>"
    "<devStatus>dev</devStatus><build>7098</build></appVersion>"
    "</modified></fileInfo></metadata>"
)
"""A complete, real metadata document: unlike `<a/>` padding, this would parse
to a populated MusxDetail if the size cap did not stop it from being read."""


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


def test_reads_valid_metadata_under_the_cap(make_musx: Callable[..., Path]) -> None:
    # Companion to test_refuses_oversized_metadata_member: proves the exact
    # same document parses to a populated result when it is small enough to
    # read, so the oversized case below is attributable to the cap alone.
    padded = _VALID_METADATA + " " * (MAX_METADATA_BYTES - len(_VALID_METADATA) - 1)
    assert len(padded.encode()) <= MAX_METADATA_BYTES
    detail = read(make_musx(metadata=padded))
    assert detail.metadata_schema == "18.0"
    assert detail.modified is not None
    assert detail.modified.major == 18


def test_refuses_oversized_metadata_member(make_musx: Callable[..., Path]) -> None:
    # Same valid, fully-populated document as above, padded past the cap. A
    # zip bomb: small compressed, enormous uncompressed. Without the size cap
    # this parses cleanly and yields a populated `modified`/`metadata_schema`
    # (see test_reads_valid_metadata_under_the_cap) — so failing to see that
    # here demonstrates the cap, not a parse failure, is what emptied it.
    oversized = _VALID_METADATA + " " * (MAX_METADATA_BYTES + 1)
    detail = read(make_musx(metadata=oversized))
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_resists_entity_expansion(make_musx: Callable[..., Path]) -> None:
    # "Billion laughs". defusedxml must refuse it rather than expanding; a
    # stdlib ElementTree parse would happily yield metadata_schema == "18.0",
    # so asserting emptiness here is specific to defusedxml refusing the doc.
    bomb = """<?xml version="1.0"?>
<!DOCTYPE metadata [
  <!ENTITY a "AAAAAAAAAA">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<metadata version="18.0">&c;</metadata>
"""
    detail = read(make_musx(metadata=bomb))
    assert detail.metadata_schema == ""


def test_corrupt_metadata_member_yields_empty_detail(make_musx: Callable[..., Path]) -> None:
    # A CRC-failed / truncated metadata member inside an otherwise valid
    # Finale archive must degrade to an empty detail, not escalate to
    # NotFinaleFileError — only the archive/mimetype are load-bearing for
    # that error.
    path = make_musx()
    with zipfile.ZipFile(path, "a") as archive:
        info = archive.getinfo(METADATA_NAME)
        offset = info.header_offset + len(info.FileHeader()) + 5
    with open(path, "r+b") as raw:
        raw.seek(offset)
        raw.write(b"\xff\xff\xff\xff")

    detail = read(path)
    assert detail.created is None
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_structurally_hostile_archive_yields_empty_detail(tmp_path: Path) -> None:
    # Duplicate member names trip a container safety limit. Version detection
    # degrades to "unknown" rather than raising — unknown variants stay
    # inspectable.
    path = tmp_path / "hostile.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/vnd.makemusic.notation")
        for _ in range(2):
            info = zipfile.ZipInfo("NotationMetadata.xml")
            archive.writestr(info, "<metadata/>")
    detail = read(path)
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_no_mimetype_over_cap_archive_raises_not_finale_file(tmp_path: Path) -> None:
    # An archive with no mimetype member at all, and more than MAX_MEMBERS
    # entries, must raise NotFinaleFileError -- not silently degrade to an
    # empty MusxDetail the way a structurally hostile *Finale* archive does
    # (see test_structurally_hostile_archive_yields_empty_detail above).
    # Presence of the mimetype member is checked before structural
    # validation runs, so "not a Finale file" wins here.
    path = tmp_path / "no-mimetype-over-cap.musx"
    with zipfile.ZipFile(path, "w") as archive:
        for i in range(MAX_MEMBERS + 1):
            archive.writestr(f"presets/{i}.preset", b"x")
    with pytest.raises(NotFinaleFileError):
        read(path)
