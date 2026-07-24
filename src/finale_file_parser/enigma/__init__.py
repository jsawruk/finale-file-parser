"""Decoding score.dat into EnigmaXML, and parsing it into a document model."""

from __future__ import annotations

from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    MalformedEnigmaError,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
    parse_enigma,
)
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.music import (
    Duration,
    Entry,
    MalformedEntryError,
    Note,
    NoteValue,
    read_entry,
)
from finale_file_parser.enigma.score import MAX_INFLATED, score_xml

__all__ = [
    "MAX_INFLATED",
    "CorruptScoreError",
    "DetailsPool",
    "Duration",
    "EnigmaDocument",
    "EntriesPool",
    "Entry",
    "MalformedEnigmaError",
    "MalformedEntryError",
    "Note",
    "NoteValue",
    "OptionsPool",
    "OthersPool",
    "Pool",
    "Record",
    "TextsPool",
    "decrypt",
    "parse_enigma",
    "read_entry",
    "score_xml",
]
