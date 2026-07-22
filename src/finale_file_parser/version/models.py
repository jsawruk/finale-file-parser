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
class ProvenanceStamp:
    """When a file was written, by what application, on which platform.

    Both formats produce these. `.musx` additionally fills `app_version`, and
    may fill `modified_by`; `.mus` leaves both at their defaults.
    """

    year: int
    month: int
    day: int

    application: str
    """Observed: "FIN"."""

    platform: str
    """Observed: "MAC" or "WIN". Each stamp carries its own — do not assume
    both stamps in a file agree."""

    modified_by: str = ""
    """Who last wrote the file. `.musx` only; non-empty in 28 of 802 corpus
    blocks, where it holds a person's initials. Empty for `.mus`."""

    app_version: AppVersion | None = None
    """The writing application's version. `.musx` only — `.mus` records no
    version in its stamps, only the banner year."""


@dataclass(frozen=True)
class MusDetail:
    """Version evidence from a legacy .mus header.

    `created`/`modified` share both their names and their `ProvenanceStamp`
    shape with `MusxDetail.created`/`.modified`, but `.mus` never populates
    `app_version` or `modified_by` on its stamps — it records *when and where*
    a file was written, not *which application version* wrote it.
    """

    banner: str
    """The copyright banner, cut at the first NUL and decoded verbatim."""

    year: int | None
    """Marketing year parsed from the banner, or None if it did not match."""

    created: ProvenanceStamp | None = None
    """When and where the file was first written, or None if unparseable."""

    modified: ProvenanceStamp | None = None
    """When and where the file was last written, or None if unparseable."""


@dataclass(frozen=True)
class MusxDetail:
    """Version evidence from a .musx NotationMetadata.xml."""

    created: ProvenanceStamp | None
    modified: ProvenanceStamp | None
    """The last writer. This is the layout authority — prefer it over `created`."""

    metadata_schema: str


@dataclass(frozen=True)
class FileVersion:
    """The result of detecting a file's writing version."""

    family: Family
    label: str
    """Human-readable version, e.g. "Finale 2011" or "18.5 dev (build 7098)"."""

    confidence: Confidence
    detail: MusDetail | MusxDetail
