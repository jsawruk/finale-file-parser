"""Decoding score.dat into EnigmaXML, and parsing it into a document model."""

from __future__ import annotations

from finale_file_parser.enigma.blast import CorruptDclStreamError, blast_decompress
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
from finale_file_parser.enigma.key import (
    KeySignature,
    Mode,
    UnsupportedKeyError,
    decode_key,
)
from finale_file_parser.enigma.location import (
    EntryLocation,
    MalformedScoreError,
    locate_entries,
)
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.mus_payload import (
    MAX_MUS_PAYLOAD,
    read_mus_payload,
    read_mus_streams,
)
from finale_file_parser.enigma.music import (
    Duration,
    Entry,
    MalformedEntryError,
    Note,
    NoteValue,
    duration_from_edu,
    read_entry,
)
from finale_file_parser.enigma.pitch import (
    SpelledNote,
    SpelledPitch,
    StaffTransposition,
    read_transposition,
    spell_note,
    spell_pitch,
    transpose_key,
    transpose_pitch,
)
from finale_file_parser.enigma.score import MAX_INFLATED, score_xml

__all__ = [
    "MAX_INFLATED",
    "MAX_MUS_PAYLOAD",
    "CorruptDclStreamError",
    "CorruptScoreError",
    "DetailsPool",
    "Duration",
    "EnigmaDocument",
    "EntriesPool",
    "Entry",
    "EntryLocation",
    "KeySignature",
    "MalformedEnigmaError",
    "MalformedEntryError",
    "MalformedScoreError",
    "Mode",
    "Note",
    "NoteValue",
    "OptionsPool",
    "OthersPool",
    "Pool",
    "Record",
    "SpelledNote",
    "SpelledPitch",
    "StaffTransposition",
    "TextsPool",
    "UnsupportedKeyError",
    "blast_decompress",
    "decode_key",
    "duration_from_edu",
    "decrypt",
    "locate_entries",
    "parse_enigma",
    "read_entry",
    "read_mus_entries",
    "read_mus_payload",
    "read_mus_streams",
    "read_transposition",
    "score_xml",
    "spell_note",
    "spell_pitch",
    "transpose_key",
    "transpose_pitch",
]
