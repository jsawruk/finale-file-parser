"""Extract version evidence from a legacy .mus header."""

from __future__ import annotations

import re

from finale_file_parser.version.models import MusDetail

BANNER_OFFSET = 0x20
BANNER_FIELD_SIZE = 0x40

_BANNER_YEAR = re.compile(r"Finale\(R\)\s+(\d{4})\b")


def parse(header: bytes) -> MusDetail:
    """Return the version evidence carried by a .mus header.

    The banner field is fixed-size and is *not* zero-filled when Finale
    rewrites it, so a shorter banner can leave a tail of the previous, longer
    one behind. Everything from the first NUL onward is therefore discarded.

    Never raises: an unrecognised banner yields `year=None` with the raw text
    preserved, so an unknown variant stays inspectable.
    """
    field = header[BANNER_OFFSET : BANNER_OFFSET + BANNER_FIELD_SIZE]
    banner = field.split(b"\x00", 1)[0].decode("latin-1")
    match = _BANNER_YEAR.match(banner)
    return MusDetail(banner=banner, year=int(match.group(1)) if match else None)
