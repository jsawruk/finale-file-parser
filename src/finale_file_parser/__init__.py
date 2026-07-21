"""A parser for Finale music notation files (.mus/.musx)."""

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
    "Family",
    "FileVersion",
    "FinaleFileError",
    "MusDetail",
    "MusxDetail",
    "NotFinaleFileError",
    "detect_version",
]
