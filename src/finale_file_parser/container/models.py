"""Types for the .musx container reader."""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.version.models import FinaleFileError


class CorruptContainerError(FinaleFileError):
    """The archive violates a structural safety rule.

    Structural validation runs before the Finale mimetype is confirmed, so
    this can be raised by an archive that is not a Finale file at all, not
    only by a confirmed Finale container that turns out malformed or hostile.
    """


@dataclass(frozen=True)
class ContainerEntry:
    """One member of a .musx archive, as declared by its central directory."""

    name: str
    size: int
    """Declared uncompressed size. Never trusted for allocation without a cap."""

    compressed_size: int
    compress_type: int
    """zipfile compression constant: 0 = STORED, 8 = DEFLATE."""
