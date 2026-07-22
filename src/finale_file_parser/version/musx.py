"""Read version evidence from a .musx archive's metadata.

Every input is treated as hostile: the archive is validated by mimetype, the
metadata member's declared size is capped before it is read, and the XML is
parsed with defusedxml so entity-expansion payloads are refused.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from finale_file_parser.container.models import CorruptContainerError
from finale_file_parser.container.musx import open_musx
from finale_file_parser.version.models import AppVersion, MusxDetail

METADATA_NAME = "NotationMetadata.xml"

MAX_METADATA_BYTES = 1 << 20
"""Refuse to read a metadata member larger than 1 MiB uncompressed. Observed
files are ~1 KB; anything vastly larger is a zip bomb, not a score."""

NAMESPACE = {"m": "http://www.makemusic.com/2012/NotationMetadata"}


def read(path: Path) -> MusxDetail:
    """Return the version evidence carried by a .musx archive.

    Raises:
        NotFinaleFileError: `path` opens but is not a valid zip archive, or is
            a zip that does not carry the Finale notation mimetype. A path
            that does not exist raises `FileNotFoundError` instead, unchanged.

    Unparseable *metadata* is not an error: it yields a MusxDetail with empty
    fields, so an unrecognised variant remains inspectable. This covers a
    missing metadata member, one over `MAX_METADATA_BYTES`, one that fails to
    read (e.g. a CRC/decompression error), one that fails to parse as XML, and
    an archive whose structure violates a container safety limit.
    """
    try:
        with open_musx(path) as container:
            try:
                raw: bytes | None = container.read(METADATA_NAME, max_bytes=MAX_METADATA_BYTES)
            except (KeyError, CorruptContainerError, zipfile.BadZipFile):
                # Missing, oversized, or unreadable metadata degrades to an
                # empty detail. Only "not a Finale file" raises.
                raw = None
    except CorruptContainerError:
        # A structurally hostile archive makes the version unknown; it does
        # not make version detection fail. Nothing oversized was read to get
        # here.
        return _empty()

    if raw is None:
        return _empty()

    try:
        root = fromstring(raw)
    except (ParseError, DefusedXmlException):
        # ParseError covers malformed XML; DefusedXmlException covers attack
        # payloads (entity expansion, external entities, etc). Both mean "no
        # usable metadata", which is a result, not a failure.
        return _empty()

    modified = _find_block(root, "modified")
    created = _find_block(root, "created")
    return MusxDetail(
        created=_app_version(created),
        modified=_app_version(modified),
        metadata_schema=root.get("version") or "",
        platform=_platform(modified) or _platform(created),
    )


def _empty() -> MusxDetail:
    return MusxDetail(created=None, modified=None, metadata_schema="", platform=None)


def _find(parent: Element, tag: str, *, deep: bool = False) -> Element | None:
    """Find `tag` under `parent`, preferring the `m:` namespace prefix and
    falling back to a bare (unnamespaced) match if that finds nothing.

    Set `deep=True` to search all descendants (`.//`) instead of only direct
    children.
    """
    prefix = ".//" if deep else ""
    found = parent.find(f"{prefix}m:{tag}", NAMESPACE)
    return found if found is not None else parent.find(f"{prefix}{tag}")


def _find_block(root: Element, tag: str) -> Element | None:
    return _find(root, tag, deep=True)


def _text(parent: Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    found = _find(parent, tag)
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
    found = _find(block, "appVersion")
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
