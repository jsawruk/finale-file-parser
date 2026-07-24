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
from finale_file_parser.enigma.location import (
    EntryLocation,
    MalformedScoreError,
    locate_entries,
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
    "EntryLocation",
    "MalformedEnigmaError",
    "MalformedEntryError",
    "MalformedScoreError",
    "Note",
    "NoteValue",
    "OptionsPool",
    "OthersPool",
    "Pool",
    "Record",
    "TextsPool",
    "decrypt",
    "locate_entries",
    "parse_enigma",
    "read_entry",
    "score_xml",
]
