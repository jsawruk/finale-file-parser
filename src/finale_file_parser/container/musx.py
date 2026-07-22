"""Read the structure of a .musx archive.

A .musx is a zip container. This module opens one, validates its structure,
enumerates its members, and hands back member bytes. It does not interpret any
payload.

Every archive is treated as hostile: structural limits are checked once at open
time against the central directory, before any member is read, and nothing is
ever extracted to disk.
"""

from __future__ import annotations

import os
import zipfile
from types import TracebackType

from finale_file_parser.container.models import ContainerEntry, CorruptContainerError
from finale_file_parser.container.names import is_safe_name
from finale_file_parser.version.models import NotFinaleFileError

MIMETYPE_NAME = "mimetype"
MIMETYPE_VALUE = b"application/vnd.makemusic.notation"
SCORE_NAME = "score.dat"

MAX_MEMBERS = 64
"""Corpus maximum is 10 members."""

MAX_TOTAL_UNCOMPRESSED = 16 * 1024 * 1024
"""Corpus maximum is 419,972 bytes per archive. A per-member cap alone does not
stop an archive of many members each just under that cap."""

MAX_SCORE_BYTES = 8 * 1024 * 1024
"""Observed corpus maximum is 412,805 bytes. This sits comfortably above real
files while staying genuinely below MAX_TOTAL_UNCOMPRESSED, so it is a real
per-call bound rather than an echo of the member's own declared size."""


class MusxContainer:
    """An open .musx archive.

    Use as a context manager; it owns the underlying zip handle.
    """

    def __init__(self, archive: zipfile.ZipFile, entries: tuple[ContainerEntry, ...]) -> None:
        self._archive = archive
        self._entries = entries

    @property
    def entries(self) -> tuple[ContainerEntry, ...]:
        """The archive's members, as validated at open time. Read-only."""
        return self._entries

    def __enter__(self) -> MusxContainer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._archive.close()

    def read(self, name: str, *, max_bytes: int) -> bytes:
        """Return the bytes of member `name`.

        `max_bytes` is required and has no default: every call site states its
        own bound, rather than inheriting one that silently stops fitting.

        Raises:
            KeyError: no such member.
            CorruptContainerError: the member declares more than `max_bytes`.
        """
        info = self._archive.getinfo(name)
        if info.file_size > max_bytes:
            raise CorruptContainerError(
                f"member {name!r} declares {info.file_size} bytes, which exceeds max_bytes"
                f" of {max_bytes}"
            )
        try:
            # This guards exactly one stdlib call, with no code of ours inside
            # it, so there is no project logic whose bugs a broad except could
            # mask. Decompressing a hostile member can fail via whatever
            # exception its codec happens to raise: BadZipFile (local header
            # disagrees with the central directory), RuntimeError (encryption
            # bit set), OSError (a codec rejects the stream outright, e.g.
            # bzip2), NotImplementedError (unsupported or deflate64 method),
            # or zlib.error (a DEFLATE-declared member with corrupt bytes —
            # this one subclasses only Exception, not any of the above, which
            # is why three successive passes of naming concrete types each
            # missed one). Any way this call fails means the member could not
            # be decompressed, which is exactly what CorruptContainerError
            # reports below — so catching the category, not an enumerated
            # list, is correct here, not sloppy. Do not narrow this back to a
            # tuple of named types. KeyboardInterrupt and SystemExit derive
            # from BaseException, not Exception, so they still propagate.
            return self._archive.read(name)
        except ValueError:
            # zipfile raises exactly this type when the handle is already
            # closed (see MusxContainer.close()). That is a caller misusing a
            # closed resource, not a hostile member failing to decompress -
            # a different failure category from everything the comment above
            # covers, so it must not be relabeled as CorruptContainerError.
            raise
        except Exception as exc:
            raise CorruptContainerError(f"member {name!r} could not be decompressed") from exc

    def score_stream(self) -> bytes:
        """Return the raw, still-obfuscated score payload.

        Raises:
            CorruptContainerError: the archive carries no score.dat, or it
                declares more than MAX_SCORE_BYTES. All 401 corpus archives
                have a score.dat, so its absence is malformed input rather
                than a caller mistake.
        """
        try:
            self._archive.getinfo(SCORE_NAME)
        except KeyError as exc:
            raise CorruptContainerError("archive has no score.dat") from exc
        return self.read(SCORE_NAME, max_bytes=MAX_SCORE_BYTES)


def open_musx(path: str | os.PathLike[str]) -> MusxContainer:
    """Open a .musx archive and validate its structure.

    Raises:
        FileNotFoundError: no such path.
        NotFinaleFileError: not a readable zip, or a zip that does not carry the
            Finale notation mimetype.
        CorruptContainerError: the archive violates a structural limit.
            Structural validation runs before the Finale mimetype is
            confirmed, so this can be raised by an archive that turns out not
            to be a Finale file at all.

    OS-level errors from opening the path itself (e.g. IsADirectoryError,
    PermissionError) propagate unchanged.
    """
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise NotFinaleFileError(f"{path} is not a readable archive") from exc

    try:
        entries = _validated_entries(archive)
        _require_finale_mimetype(archive, path)
    except Exception:
        # Translation of any archive-level failure into our public exception
        # types happens closer to the calls that can raise them (see
        # _require_finale_mimetype and read()). This catch-all exists only to
        # guarantee the handle is closed before whatever was raised propagates.
        archive.close()
        raise
    return MusxContainer(archive, entries)


def _require_finale_mimetype(archive: zipfile.ZipFile, path: object) -> None:
    try:
        info = archive.getinfo(MIMETYPE_NAME)
    except KeyError as exc:
        raise NotFinaleFileError(f"{path} is a zip archive with no mimetype member") from exc
    if info.file_size > len(MIMETYPE_VALUE):
        raise NotFinaleFileError(f"{path} is a zip archive but not a Finale .musx")
    try:
        # This guards exactly one stdlib call, with no code of ours inside it,
        # so there is no project logic whose bugs a broad except could mask.
        # Decompressing a hostile member can fail via whatever exception its
        # codec happens to raise: BadZipFile (local header disagrees with the
        # central directory), RuntimeError (encryption bit set), OSError (a
        # codec rejects the stream outright, e.g. bzip2), NotImplementedError
        # (unsupported or deflate64 method), or zlib.error (a
        # DEFLATE-declared member with corrupt bytes — this one subclasses
        # only Exception, not any of the above, which is why three successive
        # passes of naming concrete types each missed one). Any way this call
        # fails means the mimetype member could not be decompressed, which is
        # exactly "not a readable Finale archive" — so catching the category,
        # not an enumerated list, is correct here, not sloppy. Do not narrow
        # this back to a tuple of named types. KeyboardInterrupt and
        # SystemExit derive from BaseException, not Exception, so they still
        # propagate.
        contents = archive.read(MIMETYPE_NAME)
    except Exception as exc:
        raise NotFinaleFileError(f"{path} is a zip archive but not a Finale .musx") from exc
    if contents != MIMETYPE_VALUE:
        raise NotFinaleFileError(f"{path} is a zip archive but not a Finale .musx")


def _validated_entries(archive: zipfile.ZipFile) -> tuple[ContainerEntry, ...]:
    infos = archive.infolist()

    if len(infos) > MAX_MEMBERS:
        raise CorruptContainerError(f"archive has too many members: {len(infos)} > {MAX_MEMBERS}")

    seen: set[str] = set()
    total = 0
    entries: list[ContainerEntry] = []
    for info in infos:
        if not is_safe_name(info.filename):
            raise CorruptContainerError(f"unsafe member name: {info.filename!r}")
        if info.filename in seen:
            raise CorruptContainerError(f"duplicate member name: {info.filename!r}")
        seen.add(info.filename)

        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise CorruptContainerError(
                f"total declared size exceeds {MAX_TOTAL_UNCOMPRESSED} bytes"
            )

        entries.append(
            ContainerEntry(
                name=info.filename,
                size=info.file_size,
                compressed_size=info.compress_size,
                compress_type=info.compress_type,
            )
        )
    return tuple(entries)
