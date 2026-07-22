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
    "<year>2015</year><month>11</month><day>23</day>"
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
    created_app = detail.created.app_version
    assert created_app is not None
    assert created_app.major == 16
    assert created_app.maint is None
    assert created_app.dev_status == "release"
    assert detail.modified is not None
    modified_app = detail.modified.app_version
    assert modified_app is not None
    assert modified_app.major == 18
    assert modified_app.maint == 5
    assert modified_app.build == 7098


def test_platform_comes_from_the_modifying_write(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx())
    assert detail.modified is not None
    assert detail.modified.platform == "WIN"


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


def test_missing_app_version_yields_a_stamp_without_one(make_musx: Callable[..., Path]) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><year>2015</year><month>1</month><day>2</day>"
        "<platform>MAC</platform></modified></fileInfo></metadata>"
    )
    detail = read(make_musx(metadata=metadata))
    assert detail.modified is not None
    assert detail.modified.app_version is None
    assert detail.modified.platform == "MAC"


def test_reads_valid_metadata_under_the_cap(make_musx: Callable[..., Path]) -> None:
    # Companion to test_refuses_oversized_metadata_member: proves the exact
    # same document parses to a populated result when it is small enough to
    # read, so the oversized case below is attributable to the cap alone.
    padded = _VALID_METADATA + " " * (MAX_METADATA_BYTES - len(_VALID_METADATA) - 1)
    assert len(padded.encode()) <= MAX_METADATA_BYTES
    detail = read(make_musx(metadata=padded))
    assert detail.metadata_schema == "18.0"
    assert detail.modified is not None
    modified_app = detail.modified.app_version
    assert modified_app is not None
    assert modified_app.major == 18


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


def test_extracts_dates_from_both_blocks(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx())
    assert detail.created is not None and detail.modified is not None
    assert (detail.created.year, detail.created.month, detail.created.day) == (2010, 9, 14)
    assert (detail.modified.year, detail.modified.month, detail.modified.day) == (2015, 11, 23)


def test_each_stamp_carries_its_own_platform(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx())
    assert detail.created is not None and detail.modified is not None
    assert detail.created.platform == "MAC"
    assert detail.modified.platform == "WIN"


def test_extracts_modified_by(make_musx: Callable[..., Path]) -> None:
    # SAMPLE_METADATA (tests/version/conftest.py) carries no <modifiedBy> element
    # at all -- it is optional and absent from most corpus files -- so this test
    # supplies its own metadata rather than patching a placeholder that isn't there.
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><year>2015</year><month>11</month><day>23</day>"
        "<platform>WIN</platform><modifiedBy>ABC</modifiedBy>"
        "<appVersion><major>18</major><maint>5</maint><devStatus>dev</devStatus>"
        "<build>7098</build></appVersion></modified></fileInfo></metadata>"
    )
    detail = read(make_musx(metadata=metadata))
    assert detail.modified is not None
    assert detail.modified.modified_by == "ABC"


def test_block_without_a_date_yields_no_stamp(make_musx: Callable[..., Path]) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><platform>MAC</platform>"
        "<appVersion><major>18</major></appVersion></modified></fileInfo></metadata>"
    )
    assert read(make_musx(metadata=metadata)).modified is None


def test_block_with_dates_but_no_app_version_still_yields_a_stamp(
    make_musx: Callable[..., Path],
) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><year>2015</year><month>1</month><day>2</day>"
        "<platform>MAC</platform></modified></fileInfo></metadata>"
    )
    stamp = read(make_musx(metadata=metadata)).modified
    assert stamp is not None
    assert stamp.app_version is None
    assert stamp.year == 2015
