"""Decoding score.dat into EnigmaXML, and parsing it into a document model."""

from __future__ import annotations

from finale_file_parser.enigma.articulations import (
    ARTICULATION_CHARACTERS,
    articulations_by_entry,
)
from finale_file_parser.enigma.beams import BeamedNote, beams_for
from finale_file_parser.enigma.blast import CorruptDclStreamError, blast_decompress
from finale_file_parser.enigma.clef import (
    Clef,
    ClefSign,
    clef_definitions,
    clefs_by_measure,
    default_clefs,
)
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
from finale_file_parser.enigma.lyrics import (
    Lyric,
    LyricKind,
    Syllabic,
    lyrics_by_entry,
    verse_syllables,
)
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_details import (
    TAG_GFHOLD,
    MusDetailRecord,
    read_mus_details,
)
from finale_file_parser.enigma.mus_document import UNTRANSLATED, read_mus_document
from finale_file_parser.enigma.mus_entries import (
    harm_lev_octave_shift,
    read_mus_entries,
    read_mus_entry_records,
)
from finale_file_parser.enigma.mus_others import (
    TAG_FRAME_SPEC,
    TAG_MEAS_SPEC,
    MusOther,
    read_mus_others,
)
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
from finale_file_parser.enigma.text import (
    StaffNames,
    file_info,
    plain_text,
    staff_names,
    text_block,
)
from finale_file_parser.enigma.timesig import (
    TimeSignature,
    display_time_signature,
    read_time_signature,
    time_signatures,
)
from finale_file_parser.enigma.tuplet import (
    EntryChain,
    Tuplet,
    entry_chain,
    read_tuplet,
    sounded_durations,
    tuplets_by_entry,
)

__all__ = [
    "ARTICULATION_CHARACTERS",
    "BeamedNote",
    "MAX_INFLATED",
    "MAX_MUS_PAYLOAD",
    "UNTRANSLATED",
    "TAG_FRAME_SPEC",
    "TAG_GFHOLD",
    "TAG_MEAS_SPEC",
    "CorruptDclStreamError",
    "CorruptScoreError",
    "DetailsPool",
    "Duration",
    "EnigmaDocument",
    "EntriesPool",
    "Entry",
    "EntryLocation",
    "KeySignature",
    "Lyric",
    "LyricKind",
    "MalformedEnigmaError",
    "MalformedEntryError",
    "MalformedScoreError",
    "MusDetailRecord",
    "MusOther",
    "Mode",
    "Note",
    "NoteValue",
    "OptionsPool",
    "OthersPool",
    "Pool",
    "Record",
    "SpelledNote",
    "Syllabic",
    "SpelledPitch",
    "StaffTransposition",
    "TextsPool",
    "UnsupportedKeyError",
    "articulations_by_entry",
    "beams_for",
    "blast_decompress",
    "EntryChain",
    "Tuplet",
    "entry_chain",
    "read_tuplet",
    "sounded_durations",
    "tuplets_by_entry",
    "TimeSignature",
    "display_time_signature",
    "read_time_signature",
    "time_signatures",
    "Clef",
    "ClefSign",
    "clef_definitions",
    "clefs_by_measure",
    "default_clefs",
    "StaffNames",
    "file_info",
    "plain_text",
    "staff_names",
    "text_block",
    "decode_key",
    "harm_lev_octave_shift",
    "duration_from_edu",
    "decrypt",
    "locate_entries",
    "lyrics_by_entry",
    "parse_enigma",
    "read_entry",
    "read_mus_document",
    "read_mus_details",
    "read_mus_entries",
    "read_mus_entry_records",
    "read_mus_others",
    "read_mus_payload",
    "read_mus_streams",
    "read_transposition",
    "verse_syllables",
    "score_xml",
    "spell_note",
    "spell_pitch",
    "transpose_key",
    "transpose_pitch",
]
