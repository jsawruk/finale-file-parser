import struct
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser.container.models import CorruptContainerError
from finale_file_parser.container.musx import (
    MAX_MEMBERS,
    MAX_SCORE_BYTES,
    MAX_TOTAL_UNCOMPRESSED,
    open_musx,
)
from finale_file_parser.version.models import NotFinaleFileError

from .conftest import MIMETYPE


def test_enumerates_members_in_archive_order(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        names = [entry.name for entry in container.entries]
    assert names[0] == "mimetype"
    assert names == [
        "mimetype",
        "META-INF/container.xml",
        "NotationMetadata.xml",
        "presets/1.preset",
        "score.dat",
    ]


def test_entry_reports_declared_sizes_and_method(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        by_name = {entry.name: entry for entry in container.entries}
    assert by_name["mimetype"].compress_type == zipfile.ZIP_STORED
    assert by_name["score.dat"].compress_type == zipfile.ZIP_DEFLATED
    assert by_name["score.dat"].size == len(b"synthetic-score-payload")


def test_reads_score_stream(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        assert container.score_stream() == b"synthetic-score-payload"


def test_read_returns_member_bytes(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        assert container.read("NotationMetadata.xml", max_bytes=1024) == b"<metadata/>"


def test_accepts_str_path(make_archive: Callable[..., Path]) -> None:
    with open_musx(str(make_archive())) as container:
        assert container.entries


def test_unknown_but_safe_member_name_is_allowed(make_archive: Callable[..., Path]) -> None:
    members = (
        ("mimetype", MIMETYPE),
        ("some/future/member.bin", b"who knows"),
        ("score.dat", b"payload"),
    )
    with open_musx(make_archive(members)) as container:
        assert "some/future/member.bin" in [entry.name for entry in container.entries]


def test_rejects_unsafe_member_name(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", MIMETYPE), ("../escape.dat", b"x"), ("score.dat", b"y"))
    with pytest.raises(CorruptContainerError, match="unsafe member name"):
        open_musx(make_archive(members))


def test_rejects_duplicate_member_names(make_archive: Callable[..., Path]) -> None:
    members = (
        ("mimetype", MIMETYPE),
        ("score.dat", b"first"),
        ("score.dat", b"second"),
    )
    with pytest.raises(CorruptContainerError, match="duplicate member name"):
        open_musx(make_archive(members, allow_duplicates=True))


def test_rejects_too_many_members(make_archive: Callable[..., Path]) -> None:
    members = [("mimetype", MIMETYPE)]
    members += [(f"presets/{i}.preset", b"x") for i in range(MAX_MEMBERS + 1)]
    with pytest.raises(CorruptContainerError, match="too many members"):
        open_musx(make_archive(tuple(members)))


def test_rejects_total_size_over_cap(tmp_path: Path) -> None:
    # Highly compressible payloads: small on disk, enormous declared size.
    path = tmp_path / "bomb.musx"
    chunk = b"\x00" * (4 * 1024 * 1024)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for i in range(8):  # 32 MiB declared, over the 16 MiB cap
            archive.writestr(f"presets/{i}.preset", chunk)
    assert 8 * len(chunk) > MAX_TOTAL_UNCOMPRESSED
    with pytest.raises(CorruptContainerError, match="total declared size"):
        open_musx(path)


def test_read_refuses_member_over_max_bytes(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(CorruptContainerError, match="exceeds max_bytes"):
            container.read("score.dat", max_bytes=4)


def test_read_of_absent_member_raises_key_error(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(KeyError):
            container.read("nope.dat", max_bytes=1024)


def test_score_stream_without_score_dat_raises(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", MIMETYPE), ("NotationMetadata.xml", b"<m/>"))
    with open_musx(make_archive(members)) as container:
        with pytest.raises(CorruptContainerError, match="no score.dat"):
            container.score_stream()


def test_rejects_zip_without_finale_mimetype(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", b"application/zip"), ("score.dat", b"x"))
    with pytest.raises(NotFinaleFileError):
        open_musx(make_archive(members))


def test_rejects_zip_with_no_mimetype_member(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "not a score")
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_rejects_non_zip(tmp_path: Path) -> None:
    path = tmp_path / "legacy.mus"
    path.write_bytes(b"ENIGMA BINARY FILE" + b"\x00" * 78)
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        open_musx(tmp_path / "nope.musx")


def test_closing_releases_the_handle(make_archive: Callable[..., Path]) -> None:
    container = open_musx(make_archive())
    container.close()
    with pytest.raises(ValueError):
        container.read("score.dat", max_bytes=1024)


# --- Finding 1: structural validation must run before any member is read -----


def test_structural_violations_are_reported_even_without_a_finale_mimetype(
    make_archive: Callable[..., Path],
) -> None:
    """An archive with an unsafe name and too many members must fail as
    CorruptContainerError, not NotFinaleFileError, even when it has no
    mimetype member at all. If the mimetype gate ran before structural
    validation, this archive would fail there first, and the structural
    checks would never run."""
    members = [("../../../../etc/passwd", b"x")]
    members += [(f"presets/{i}.preset", b"y") for i in range(MAX_MEMBERS + 1)]
    with pytest.raises(CorruptContainerError):
        open_musx(make_archive(tuple(members)))


# --- Finding 2: the mimetype read must be inside the exception guard --------


def _set_central_directory_flag_bits(path: Path, member_name: str, flag_bits: int) -> None:
    """Patch the general-purpose bit flag of `member_name`'s central directory
    record in place.

    `zipfile.ZipFile.writestr` always resets `ZipInfo.flag_bits` to 0 when
    writing (see `_open_to_write`), so a hostile flag combination such as the
    encryption bit can only be produced by editing the written bytes
    afterwards — exactly how the reviewer's hostile zips were built.
    """
    data = bytearray(path.read_bytes())
    name_bytes = member_name.encode()
    signature = b"PK\x01\x02"
    pos = 0
    while True:
        pos = data.find(signature, pos)
        if pos == -1:
            raise AssertionError(f"central directory record for {member_name!r} not found")
        name_len = struct.unpack_from("<H", data, pos + 28)[0]
        if bytes(data[pos + 46 : pos + 46 + name_len]) == name_bytes:
            struct.pack_into("<H", data, pos + 8, flag_bits)
            path.write_bytes(bytes(data))
            return
        pos += len(signature)


def test_rejects_encrypted_mimetype_member(tmp_path: Path) -> None:
    path = tmp_path / "encrypted.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"x")
    _set_central_directory_flag_bits(path, "mimetype", 0x1)  # bit 0: encrypted
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_rejects_mimetype_member_with_corrupt_local_header(tmp_path: Path) -> None:
    path = tmp_path / "corrupt-local-header.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"x")
    with zipfile.ZipFile(path) as archive:
        offset = archive.getinfo("mimetype").header_offset
    data = bytearray(path.read_bytes())
    data[offset : offset + 4] = b"\x00\x00\x00\x00"  # corrupt local header signature
    path.write_bytes(bytes(data))
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


# --- Finding 3: score_stream()'s cap must be a real bound, not tautological -


def test_score_stream_rejects_declared_size_over_max_score_bytes(tmp_path: Path) -> None:
    path = tmp_path / "huge-score.musx"
    oversized = 9 * 1024 * 1024  # over MAX_SCORE_BYTES, under MAX_TOTAL_UNCOMPRESSED
    assert oversized > MAX_SCORE_BYTES
    assert oversized + len(MIMETYPE) < MAX_TOTAL_UNCOMPRESSED
    chunk = b"\x00" * oversized  # highly compressible: small on disk
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", chunk)
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError, match="exceeds max_bytes"):
            container.score_stream()


# --- Finding 4: a post-open local-header mismatch must translate ------------


def _build_archive_with_corrupt_score_header(tmp_path: Path) -> Path:
    path = tmp_path / "corrupt-score-header.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"payload")
    with zipfile.ZipFile(path) as archive:
        offset = archive.getinfo("score.dat").header_offset
    data = bytearray(path.read_bytes())
    data[offset : offset + 4] = b"\x00\x00\x00\x00"  # corrupt local header signature
    path.write_bytes(bytes(data))
    return path


def test_read_translates_local_header_mismatch_after_open(tmp_path: Path) -> None:
    path = _build_archive_with_corrupt_score_header(tmp_path)
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError):
            container.read("score.dat", max_bytes=1024)


def test_score_stream_translates_local_header_mismatch_after_open(tmp_path: Path) -> None:
    path = _build_archive_with_corrupt_score_header(tmp_path)
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError):
            container.score_stream()


# --- Finding 5: entries is read-only ----------------------------------------


def test_entries_is_read_only(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(AttributeError):
            container.entries = ()  # type: ignore[misc]
