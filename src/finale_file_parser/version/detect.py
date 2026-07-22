"""Public entry point for Finale file version detection."""

from __future__ import annotations

import os
from pathlib import Path

from finale_file_parser.version import mus, musx
from finale_file_parser.version.family import HEADER_SIZE, classify
from finale_file_parser.version.models import (
    Confidence,
    Family,
    FileVersion,
    MusDetail,
    MusxDetail,
)
from finale_file_parser.version.mus import MUS_METADATA_SIZE

UNKNOWN_LABEL = "unknown version"


def detect_version(path: str | os.PathLike[str]) -> FileVersion:
    """Identify which Finale version wrote the file at `path`.

    `path` accepts anything `open()` does — a `str` or any `os.PathLike[str]`
    (including `pathlib.Path`) — and is converted to a `Path` internally.

    Reads only the header (and, for .musx, the archive metadata) — never the
    score body.

    Raises:
        FileNotFoundError: no such file.
        NotFinaleFileError: the file is not a Finale file.
    """
    path = Path(path)
    with open(path, "rb") as handle:
        header = handle.read(max(HEADER_SIZE, MUS_METADATA_SIZE))

    family = classify(header)
    if family is Family.MUS:
        detail = mus.parse(header)
        return _assemble(Family.MUS, _mus_label(detail), detail.year is not None, detail)

    musx_detail = musx.read(path)
    known = musx_detail.modified is not None or musx_detail.created is not None
    return _assemble(Family.MUSX, _musx_label(musx_detail), known, musx_detail)


def _assemble(
    family: Family, label: str, known: bool, detail: MusDetail | MusxDetail
) -> FileVersion:
    return FileVersion(
        family=family,
        label=label,
        confidence=Confidence.EXACT if known else Confidence.UNKNOWN,
        detail=detail,
    )


def _mus_label(detail: MusDetail) -> str:
    return f"Finale {detail.year}" if detail.year is not None else UNKNOWN_LABEL


def _musx_label(detail: MusxDetail) -> str:
    app = detail.modified or detail.created
    if app is None:
        return UNKNOWN_LABEL
    number = f"{app.major}.{app.maint}" if app.maint is not None else str(app.major)
    parts = [number]
    if app.dev_status:
        parts.append(app.dev_status)
    if app.build is not None:
        parts.append(f"(build {app.build})")
    return " ".join(parts)
