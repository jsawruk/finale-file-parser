"""Read version evidence from a .musx archive's metadata.

Every input is treated as hostile: the archive is validated by mimetype, the
metadata member's declared size is capped before it is read, and the XML is
parsed with defusedxml so entity-expansion payloads are refused.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

from finale_file_parser.version.models import AppVersion, MusxDetail, NotFinaleFileError

MIMETYPE_NAME = "mimetype"
MIMETYPE_VALUE = b"application/vnd.makemusic.notation"
METADATA_NAME = "NotationMetadata.xml"

MAX_METADATA_BYTES = 1 << 20
"""Refuse to read a metadata member larger than 1 MiB uncompressed. Observed
files are ~1 KB; anything vastly larger is a zip bomb, not a score."""

NAMESPACE = {"m": "http://www.makemusic.com/2012/NotationMetadata"}


def read(path: Path) -> MusxDetail:
    """Return the version evidence carried by a .musx archive.

    Raises:
        NotFinaleFileError: the archive is unreadable, or is a zip that is not
            a Finale notation container.

    Unparseable *metadata* is not an error: it yields a MusxDetail with empty
    fields, so an unrecognised variant remains inspectable.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            _require_finale_mimetype(archive, path)
            raw = _read_capped(archive, METADATA_NAME, MAX_METADATA_BYTES)
    except zipfile.BadZipFile as exc:
        raise NotFinaleFileError(f"{path} is not a readable archive") from exc

    if raw is None:
        return MusxDetail(created=None, modified=None, metadata_schema="", platform=None)

    try:
        root = fromstring(raw)
    except Exception:
        # defusedxml raises its own DefusedXmlException subclasses for attack
        # payloads and ParseError for malformed input. Both mean "no usable
        # metadata", which is a result, not a failure.
        return MusxDetail(created=None, modified=None, metadata_schema="", platform=None)

    modified = _find_block(root, "modified")
    created = _find_block(root, "created")
    return MusxDetail(
        created=_app_version(created),
        modified=_app_version(modified),
        metadata_schema=root.get("version") or "",
        platform=_platform(modified) or _platform(created),
    )


def _require_finale_mimetype(archive: zipfile.ZipFile, path: Path) -> None:
    raw = _read_capped(archive, MIMETYPE_NAME, len(MIMETYPE_VALUE))
    if raw != MIMETYPE_VALUE:
        raise NotFinaleFileError(f"{path} is a zip archive but not a Finale .musx")


def _read_capped(archive: zipfile.ZipFile, name: str, cap: int) -> bytes | None:
    """Read `name` only if it declares no more than `cap` uncompressed bytes."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > cap:
        return None
    return archive.read(name)


def _find_block(root: Element, tag: str) -> Element | None:
    block = root.find(f".//m:{tag}", NAMESPACE)
    return block if block is not None else root.find(f".//{tag}")


def _text(parent: Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    found = parent.find(f"m:{tag}", NAMESPACE)
    if found is None:
        found = parent.find(tag)
    return found.text if found is not None and found.text else None


def _int(parent: Element | None, tag: str) -> int | None:
    raw = _text(parent, tag)
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _app_version(block: Element | None) -> AppVersion | None:
    if block is None:
        return None
    found: Any = block.find("m:appVersion", NAMESPACE)
    if found is None:
        found = block.find("appVersion")
    if found is None:
        return None
    major = _int(found, "major")
    if major is None:
        return None
    return AppVersion(
        major=major,
        maint=_int(found, "maint"),
        dev_status=_text(found, "devStatus") or "",
        build=_int(found, "build"),
    )


def _platform(block: Element | None) -> str | None:
    return _text(block, "platform")
