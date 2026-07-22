"""Public entry point for Finale file version detection."""

from __future__ import annotations

import os
from pathlib import Path

from finale_file_parser.version import mus, musx
from finale_file_parser.version.family import classify
from finale_file_parser.version.models import (
    Confidence,
    Family,
    FileVersion,
    MusDetail,
    MusxDetail,
    ProvenanceStamp,
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
        # MUS_METADATA_SIZE (0xA0) exceeds HEADER_SIZE (0x60): the read is sized
        # to reach both .mus provenance stamps, not just the banner that
        # `classify` inspects, so one read serves both `classify` and
        # `mus.parse`.
        header = handle.read(MUS_METADATA_SIZE)

    family = classify(header)
    if family is Family.MUS:
        detail = mus.parse(header)
        return _assemble(Family.MUS, _mus_label(detail), detail.year is not None, detail)

    musx_detail = musx.read(path)
    stamp = _musx_stamp(musx_detail)
    known = stamp is not None and stamp.app_version is not None
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


def _musx_stamp(detail: MusxDetail) -> ProvenanceStamp | None:
    """Select the stamp that is the layout authority.

    `modified` wins over `created`, but only when it actually carries a
    version: a stamp can exist (a usable date, platform, etc.) without an
    `app_version`, and a modified-but-versionless stamp must not shadow a
    versioned `created` stamp. This selection is shared by both the label and
    the `known`/confidence computation in `detect_version`, so the two can
    never disagree about which stamp is authoritative.
    """
    return detail.modified if detail.modified and detail.modified.app_version else detail.created


def _musx_label(detail: MusxDetail) -> str:
    stamp = _musx_stamp(detail)
    app = stamp.app_version if stamp is not None else None
    if app is None:
        return UNKNOWN_LABEL
    number = f"{app.major}.{app.maint}" if app.maint is not None else str(app.major)
    parts = [number]
    if app.dev_status:
        parts.append(app.dev_status)
    if app.build is not None:
        parts.append(f"(build {app.build})")
    return " ".join(parts)
