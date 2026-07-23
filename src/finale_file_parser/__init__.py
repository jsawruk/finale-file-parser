"""A parser for Finale music notation files (.mus/.musx)."""

from finale_file_parser.container import (
    ContainerEntry,
    CorruptContainerError,
    MusxContainer,
    open_musx,
)
from finale_file_parser.enigma import (
    MAX_INFLATED,
    CorruptScoreError,
    EnigmaDocument,
    MalformedEnigmaError,
    Pool,
    Record,
    decrypt,
    parse_enigma,
    score_xml,
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
    ProvenanceStamp,
)

__all__ = [
    "MAX_INFLATED",
    "AppVersion",
    "Confidence",
    "ContainerEntry",
    "CorruptContainerError",
    "CorruptScoreError",
    "EnigmaDocument",
    "Family",
    "FileVersion",
    "FinaleFileError",
    "MalformedEnigmaError",
    "MusDetail",
    "MusxContainer",
    "MusxDetail",
    "NotFinaleFileError",
    "Pool",
    "ProvenanceStamp",
    "Record",
    "decrypt",
    "detect_version",
    "open_musx",
    "parse_enigma",
    "score_xml",
]
