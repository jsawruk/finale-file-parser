"""Result types for Finale file version detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Re-exported so existing imports of `finale_file_parser.version.models.FinaleFileError`
# / `.NotFinaleFileError` keep working. The types themselves live in
# `finale_file_parser.errors`, which neither `version` nor `container` owns —
# see that module's docstring for why.
from finale_file_parser.errors import FinaleFileError as FinaleFileError
from finale_file_parser.errors import NotFinaleFileError as NotFinaleFileError


class Family(Enum):
    """Which on-disk container family a file belongs to."""

    MUS = "mus"
    MUSX = "musx"


class Confidence(Enum):
    """How certain the reported version is."""

    EXACT = "exact"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AppVersion:
    """A Finale application version, as reported by .musx metadata."""

    major: int
    maint: int | None
    dev_status: str
    build: int | None


@dataclass(frozen=True)
class MusDetail:
    """Version evidence from a legacy .mus header."""

    banner: str
    """The copyright banner, cut at the first NUL and decoded verbatim."""

    year: int | None
    """Marketing year parsed from the banner, or None if it did not match."""


@dataclass(frozen=True)
class MusxDetail:
    """Version evidence from a .musx NotationMetadata.xml."""

    created: AppVersion | None
    modified: AppVersion | None
    """The last writer. This is the layout authority — prefer it over `created`."""

    metadata_schema: str
    platform: str | None


@dataclass(frozen=True)
class FileVersion:
    """The result of detecting a file's writing version."""

    family: Family
    label: str
    """Human-readable version, e.g. "Finale 2011" or "18.5 dev (build 7098)"."""

    confidence: Confidence
    detail: MusDetail | MusxDetail
