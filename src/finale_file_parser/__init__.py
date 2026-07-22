"""A parser for Finale music notation files (.mus/.musx)."""

from finale_file_parser.container import (
    ContainerEntry,
    CorruptContainerError,
    MusxContainer,
    open_musx,
)
from finale_file_parser.version.detect import detect_version
from finale_file_parser.version.models import (
    AppVersion,
    Confidence,
    Family,
    FileVersion,
    FinaleFileError,
    MusDetail,
    MusxDetail,
    NotFinaleFileError,
)

__all__ = [
    "AppVersion",
    "Confidence",
    "ContainerEntry",
    "CorruptContainerError",
    "Family",
    "FileVersion",
    "FinaleFileError",
    "MusDetail",
    "MusxContainer",
    "MusxDetail",
    "NotFinaleFileError",
    "detect_version",
    "open_musx",
]
