"""Extract version evidence from a legacy .mus header."""

from __future__ import annotations

import re

from finale_file_parser.version.models import MusDetail, MusStamp

BANNER_OFFSET = 0x20
BANNER_FIELD_SIZE = 0x40

MUS_METADATA_SIZE = 0xA0
"""Bytes of header needed to reach both provenance stamps (they end at 0x9D)."""

_CREATED = (0x66, 0x70, 0x74)
_MODIFIED = (0x8C, 0x96, 0x9A)
"""(date, application tag, platform tag) offsets. Validated across all 238
corpus files; see the design spec."""

_MIN_YEAR, _MAX_YEAR = 1980, 2030

_BANNER_YEAR = re.compile(r"Finale\(R\)\s+(\d{4})\b")


def parse(header: bytes) -> MusDetail:
    """Return the version evidence carried by a .mus header.

    The banner field is fixed-size and is *not* zero-filled when Finale
    rewrites it, so a shorter banner can leave a tail of the previous, longer
    one behind. Everything from the first NUL onward is therefore discarded.

    Never raises: an unrecognised banner yields `year=None` with the raw text
    preserved, so an unknown variant stays inspectable.

    Provenance stamps are all-or-nothing: a stamp with an implausible date or
    an empty application tag is None rather than partially filled, because a
    caller cannot tell which half of a partial stamp to trust.
    """
    field = header[BANNER_OFFSET : BANNER_OFFSET + BANNER_FIELD_SIZE]
    banner = field.split(b"\x00", 1)[0].decode("latin-1")
    match = _BANNER_YEAR.match(banner)
    return MusDetail(
        banner=banner,
        year=int(match.group(1)) if match else None,
        created=_stamp(header, *_CREATED),
        modified=_stamp(header, *_MODIFIED),
    )


def _stamp(header: bytes, date_off: int, app_off: int, plat_off: int) -> MusStamp | None:
    """Return the stamp at these offsets, or None if it is absent or implausible."""
    date = header[date_off : date_off + 3]
    if len(date) < 3:
        return None
    year, month, day = 1900 + date[0], date[1], date[2]
    if not (_MIN_YEAR <= year <= _MAX_YEAR and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    application = _tag(header, app_off)
    if not application:
        return None
    return MusStamp(
        year=year,
        month=month,
        day=day,
        application=application,
        platform=_tag(header, plat_off),
    )


def _tag(header: bytes, offset: int, limit: int = 8) -> str:
    """Read a NUL-terminated ASCII tag, bounded by `limit` bytes."""
    return header[offset : offset + limit].split(b"\x00", 1)[0].decode("latin-1")
