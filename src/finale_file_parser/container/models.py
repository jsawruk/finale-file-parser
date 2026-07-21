"""Types for the .musx container reader."""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.version.models import FinaleFileError


class CorruptContainerError(FinaleFileError):
    """The archive is a Finale container but violates a structural safety rule.

    Distinct from NotFinaleFileError, which means "this is not a Finale file at
    all". This means "it is one, and it is malformed or hostile".
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
