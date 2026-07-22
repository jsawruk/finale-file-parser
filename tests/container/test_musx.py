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

# --- Enumeration and entries -------------------------------------------------


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


def test_entries_is_read_only(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(AttributeError):
            container.entries = ()  # type: ignore[misc]


def test_accepts_str_path(make_archive: Callable[..., Path]) -> None:
    with open_musx(str(make_archive())) as container:
        assert container.entries


def test_reads_score_stream(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        assert container.score_stream() == b"synthetic-score-payload"


def test_read_returns_member_bytes(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        assert container.read("NotationMetadata.xml", max_bytes=1024) == b"<metadata/>"


def test_read_of_absent_member_raises_key_error(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(KeyError):
            container.read("nope.dat", max_bytes=1024)


def test_score_stream_without_score_dat_raises(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", MIMETYPE), ("NotationMetadata.xml", b"<m/>"))
    with open_musx(make_archive(members)) as container:
        with pytest.raises(CorruptContainerError, match="no score.dat"):
            container.score_stream()


# --- Name safety --------------------------------------------------------------


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


# --- Structural size limits ---------------------------------------------------


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


# --- Handle lifecycle ---------------------------------------------------------


def test_closing_releases_the_handle(make_archive: Callable[..., Path]) -> None:
    container = open_musx(make_archive())
    container.close()
    with pytest.raises(ValueError):
        container.read("score.dat", max_bytes=1024)


def test_open_musx_closes_the_handle_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Deleting `archive.close()` from `open_musx`'s except-and-reraise branch
    passes every other test in this file, yet leaks a file descriptor for
    every rejected archive -- the corpus sweep alone opens 401 archives. This
    wraps `zipfile.ZipFile` with a subclass that records `close()` calls,
    monkeypatches it in for the duration of the test, and confirms `close()`
    fires when structural validation fails, using stdlib only (no mocking
    library)."""
    path = tmp_path / "too-many-members.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for i in range(MAX_MEMBERS + 1):
            archive.writestr(f"presets/{i}.preset", b"x")

    close_calls: list[None] = []

    class RecordingZipFile(zipfile.ZipFile):
        def close(self) -> None:
            close_calls.append(None)
            super().close()

        def __del__(self) -> None:
            # zipfile.ZipFile defines __del__ to call close() as a backstop
            # "in case the user forgot". Left in place, that backstop fires
            # whenever CPython's refcounting GC happens to collect `archive`
            # -- timing this test must not depend on -- and would record a
            # close() call regardless of whether open_musx's failure path
            # closed the handle itself. Suppressing it here means every
            # recorded call is one open_musx (or MusxContainer.close())
            # actually made.
            pass

    # Patched on the `zipfile` module itself: `container.musx` does `import
    # zipfile` and calls `zipfile.ZipFile(...)`, an attribute lookup at call
    # time, so replacing the attribute here reaches it without needing to
    # patch `finale_file_parser.container.musx` directly.
    monkeypatch.setattr(zipfile, "ZipFile", RecordingZipFile)

    with pytest.raises(CorruptContainerError):
        open_musx(path)

    assert close_calls == [None]


# --- Check ordering: presence, then structure, then mimetype value ----------
#
# `open_musx` documents three ordered checks: whether `mimetype` is present at
# all (central directory only, no read); structural validation (member count,
# names, total size); and only then a read-and-compare of the mimetype
# member's value. Swapping the last two silently passes every other test in
# this file, because none of them combines "mimetype present but wrong value"
# with "also structurally hostile" in one archive -- the one shape that can
# distinguish the two orderings.


def test_rejects_no_mimetype_member_even_when_over_member_cap(tmp_path: Path) -> None:
    """An archive with no mimetype member and more than MAX_MEMBERS entries
    must be reported as NotFinaleFileError, not CorruptContainerError: the
    presence check runs -- and wins -- before the member-count check does."""
    path = tmp_path / "no-mimetype-over-cap.musx"
    with zipfile.ZipFile(path, "w") as archive:
        for i in range(MAX_MEMBERS + 1):
            archive.writestr(f"presets/{i}.preset", b"x")
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_rejects_too_many_members_when_mimetype_is_present(tmp_path: Path) -> None:
    """The same over-cap member count, but with a valid mimetype member
    present, is reported as CorruptContainerError: presence alone does not
    satisfy the gate, structural validation still runs and still enforces
    the member cap."""
    path = tmp_path / "many-members-with-mimetype.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for i in range(MAX_MEMBERS + 1):
            archive.writestr(f"presets/{i}.preset", b"x")
    with pytest.raises(CorruptContainerError):
        open_musx(path)


def test_structural_violations_are_reported_for_a_finale_archive(
    make_archive: Callable[..., Path],
) -> None:
    """The structural gate runs before any member is read. A Finale-shaped
    archive (a valid mimetype member is present) that also has an unsafe
    member name and too many members must still fail as
    CorruptContainerError: a Finale-shaped but hostile archive is reported
    as corrupt, not as a valid Finale file."""
    members = [("mimetype", MIMETYPE), ("../../../../etc/passwd", b"x")]
    members += [(f"presets/{i}.preset", b"y") for i in range(MAX_MEMBERS + 1)]
    with pytest.raises(CorruptContainerError):
        open_musx(make_archive(tuple(members)))


def test_wrong_mimetype_value_over_member_cap_raises_corrupt_not_not_finale(
    tmp_path: Path,
) -> None:
    """The test that actually pins the ordering: a `mimetype` member that is
    *present* but carries the wrong *value*, in an archive that also violates
    MAX_MEMBERS, must raise CorruptContainerError -- not NotFinaleFileError.
    Structural validation runs before the mimetype value is ever compared, so
    the member-count violation wins. Swapping the two statements in
    `open_musx` (structural validation and the mimetype-value read) makes
    this test fail, because a wrong-value mimetype would then be caught
    first and reported as NotFinaleFileError instead."""
    path = tmp_path / "wrong-mimetype-over-cap.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"not/the/right/value", compress_type=zipfile.ZIP_STORED)
        for i in range(MAX_MEMBERS + 1):
            archive.writestr(f"presets/{i}.preset", b"x")
    with pytest.raises(CorruptContainerError):
        open_musx(path)


# --- Error contract: not-a-Finale-file vs corrupt ----------------------------


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


def test_rejects_unsupported_extract_version(tmp_path: Path) -> None:
    """zipfile's own central-directory parse raises NotImplementedError when an
    entry declares an extract_version above MAX_EXTRACT_VERSION. That is a
    malformed archive, and must surface as NotFinaleFileError rather than
    escaping raw."""
    path = tmp_path / "future.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE)
        archive.writestr("score.dat", b"payload")
    raw = bytearray(path.read_bytes())
    index = raw.find(b"PK\x01\x02")
    assert index != -1, "no central directory record found"
    raw[index + 6] = 99  # extract_version, well above MAX_EXTRACT_VERSION (63)
    path.write_bytes(bytes(raw))

    with pytest.raises(NotFinaleFileError):
        open_musx(path)


# --- Decompression failures translate to our error types ---------------------
#
# The guard around `archive.read()` (both at the mimetype-value check inside
# `open_musx` and at `MusxContainer.read()`) catches `Exception` broadly
# rather than an enumerated list of concrete types. Decompressing a hostile
# member can fail via whatever exception its codec happens to raise:
# `BadZipFile` (local header disagrees with the central directory),
# `RuntimeError` (encryption bit set), `OSError` (a codec rejects the stream
# outright, e.g. bzip2), `NotImplementedError` (unsupported or deflate64
# method), or `zlib.error` (a DEFLATE-declared member with corrupt bytes --
# this one subclasses only `Exception`, not any of the above, which is why
# three successive passes of naming concrete types each missed one). Each test
# below drives one of those failure modes and confirms the guard categorises
# by "however decompression failed", not by an enumerated list.


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


def _set_central_directory_compress_type(path: Path, member_name: str, compress_type: int) -> None:
    """Patch the declared compression method of `member_name`'s central
    directory record in place, leaving the actual member bytes untouched.

    The point of each escape being tested is that zipfile's decompressor
    rejects what it finds for the declared method; genuine compressed data
    for that method is not required.
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
            struct.pack_into("<H", data, pos + 10, compress_type)
            path.write_bytes(bytes(data))
            return
        pos += len(signature)


def _set_local_header_compress_type(path: Path, header_offset: int, compress_type: int) -> None:
    """Patch the compression-method field of the local file header located at
    `header_offset`, leaving the rest of the local header untouched."""
    data = bytearray(path.read_bytes())
    struct.pack_into("<H", data, header_offset + 8, compress_type)
    path.write_bytes(bytes(data))


def _declare_member_as_deflate(path: Path, member_name: str) -> None:
    """Patch `member_name`'s declared compression method to ZIP_DEFLATED in
    both the local file header and the central directory record, without
    touching the member's actual (still-ZIP_STORED-written) bytes. The result
    is a member zipfile will try to inflate that was never deflated."""
    with zipfile.ZipFile(path) as archive:
        header_offset = archive.getinfo(member_name).header_offset
    _set_local_header_compress_type(path, header_offset, zipfile.ZIP_DEFLATED)
    _set_central_directory_compress_type(path, member_name, zipfile.ZIP_DEFLATED)


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


def test_rejects_bzip2_mimetype_member(tmp_path: Path) -> None:
    """A mimetype member declared as bzip2-compressed makes archive.read()
    raise OSError: Invalid data stream, since the stored bytes are not valid
    bzip2. Must translate to NotFinaleFileError, same as any other unreadable
    mimetype member."""
    path = tmp_path / "bzip2-mimetype.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"x")
    _set_central_directory_compress_type(path, "mimetype", zipfile.ZIP_BZIP2)
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_read_translates_bzip2_score_member(tmp_path: Path) -> None:
    """The same bzip2 escape, but on a post-open member read: score.dat
    declared as bzip2-compressed must translate to CorruptContainerError."""
    path = tmp_path / "bzip2-score.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"not actually bzip2 data")
    _set_central_directory_compress_type(path, "score.dat", zipfile.ZIP_BZIP2)
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError):
            container.score_stream()


def test_read_translates_unsupported_compression_method(tmp_path: Path) -> None:
    """An unknown/unsupported compression method on a member raises
    NotImplementedError from zipfile; must translate to CorruptContainerError,
    not escape raw."""
    path = tmp_path / "unsupported-method.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"payload")
    _set_central_directory_compress_type(path, "score.dat", 99)
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError):
            container.read("score.dat", max_bytes=1024)


def test_read_translates_encrypted_non_mimetype_member(tmp_path: Path) -> None:
    """The encryption-bit escape, previously only tested against mimetype
    (inside open_musx's guard), must also translate at the read()/
    score_stream() guard for a member encountered after a successful open."""
    path = tmp_path / "encrypted-score.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"payload")
    _set_central_directory_flag_bits(path, "score.dat", 0x1)  # bit 0: encrypted
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError):
            container.read("score.dat", max_bytes=1024)


def test_rejects_mimetype_declared_deflate_with_corrupt_bytes(tmp_path: Path) -> None:
    """A mimetype member declared ZIP_DEFLATED whose bytes are garbage raises
    zlib.error from archive.read(); must translate to NotFinaleFileError.
    Garbage is exactly len(MIMETYPE_VALUE) bytes so the file-size
    short-circuit in _require_finale_mimetype does not mask the decompression
    failure -- the read must actually be attempted."""
    path = tmp_path / "deflate-mimetype.musx"
    garbage = bytes(range(256))[: len(MIMETYPE)]  # not a valid DEFLATE stream
    assert len(garbage) == len(MIMETYPE)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", garbage, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", b"x")
    _declare_member_as_deflate(path, "mimetype")
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_read_translates_deflate_score_member_with_corrupt_bytes(tmp_path: Path) -> None:
    """The same escape, but on a post-open member read: score.dat declared
    ZIP_DEFLATED with bytes that are not valid DEFLATE data must translate to
    CorruptContainerError."""
    path = tmp_path / "deflate-score.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "score.dat", b"not a valid deflate stream", compress_type=zipfile.ZIP_STORED
        )
    _declare_member_as_deflate(path, "score.dat")
    with open_musx(path) as container:
        with pytest.raises(CorruptContainerError):
            container.read("score.dat", max_bytes=1024)


def test_member_cap_is_the_documented_value(make_archive: Callable[..., Path]) -> None:
    """Pin MAX_MEMBERS to a literal, not to itself.

    Every other cap test derives its archive size from the constant, so raising
    MAX_MEMBERS would leave them all passing while silently diverging from the
    64 documented in docs/SECURITY.md. This asserts the value and exercises the
    boundary with literal counts.
    """
    assert MAX_MEMBERS == 64

    at_cap = [("mimetype", MIMETYPE)] + [(f"presets/{i}.preset", b"x") for i in range(63)]
    with open_musx(make_archive(tuple(at_cap))) as container:
        assert len(container.entries) == 64

    over_cap = [("mimetype", MIMETYPE)] + [(f"presets/{i}.preset", b"x") for i in range(64)]
    with pytest.raises(CorruptContainerError, match="too many members"):
        open_musx(make_archive(tuple(over_cap)))
