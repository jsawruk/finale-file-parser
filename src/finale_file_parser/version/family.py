"""Classify a file into a Finale container family from its leading bytes."""

from __future__ import annotations

from finale_file_parser.version.models import Family, NotFinaleFileError

MUS_MAGIC = b"ENIGMA BINARY FILE"
"""Present at offset 0 in every .mus file observed, across Finale 2001-2012."""

ZIP_MAGIC = b"PK\x03\x04"

HEADER_SIZE = 0x60
"""Bytes read for classification and .mus banner parsing. Fixed; never content-derived."""


def classify(header: bytes) -> Family:
    """Return the container family for `header`.

    Any zip archive classifies as MUSX; confirming it is genuinely a Finale
    archive requires reading its `mimetype` member, which `musx.read` does.

    Raises:
        NotFinaleFileError: the bytes match no known Finale container.
    """
    if header.startswith(MUS_MAGIC):
        return Family.MUS
    if header.startswith(ZIP_MAGIC):
        return Family.MUSX
    raise NotFinaleFileError(f"unrecognised file header: {header[:16]!r}")
