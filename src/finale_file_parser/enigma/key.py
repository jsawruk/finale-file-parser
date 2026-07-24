"""Decode the raw `keySig.key` integer into a structured key signature.

The encoding is reverse-engineered from the corpus (documented nowhere read):

    key = (mode << 8) | (fifths & 0xFF)

where `mode` is 0 (major) or 1 (minor) and `fifths` is a signed accidental count
(sharps positive, flats negative) in the MusicXML convention. See
docs/superpowers/specs/2026-07-24-key-decode-design.md for the evidence and for
what is proven vs inferred (notably mode = 1 => minor is inferred).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from finale_file_parser.errors import FinaleFileError

_MAX_FIFTHS = 7

_MAJOR_TONIC = {
    0: "C",
    1: "G",
    2: "D",
    3: "A",
    4: "E",
    5: "B",
    6: "F#",
    7: "C#",
    -1: "F",
    -2: "Bb",
    -3: "Eb",
    -4: "Ab",
    -5: "Db",
    -6: "Gb",
    -7: "Cb",
}
_MINOR_TONIC = {
    0: "A",
    1: "E",
    2: "B",
    3: "F#",
    4: "C#",
    5: "G#",
    6: "D#",
    7: "A#",
    -1: "D",
    -2: "G",
    -3: "C",
    -4: "F",
    -5: "Bb",
    -6: "Eb",
    -7: "Ab",
}


class UnsupportedKeyError(FinaleFileError):
    """A raw key value outside the reverse-engineered standard model.

    `mode >= 2` (a church mode or custom/linear key we have not established) or
    `fifths` outside -7..+7. Raised rather than guessed: a wrong key would
    silently misspell every pitch that resolves through it.
    """


class Mode(Enum):
    """Major or minor, decoded from the high byte of the raw key integer."""

    MAJOR = 0
    MINOR = 1


@dataclass(frozen=True)
class KeySignature:
    """A decoded key signature."""

    fifths: int
    """Signed accidental count: sharps positive, flats negative (MusicXML)."""

    mode: Mode

    tonic: str
    """The tonic note name, e.g. "C", "F#", "Bb"; "A" for A minor."""


def decode_key(raw: int) -> KeySignature:
    """Decode a raw `keySig.key` integer into a `KeySignature`.

    Raises:
        UnsupportedKeyError: `mode >= 2`, or `fifths` outside -7..+7.
    """
    mode_value = raw >> 8
    low = raw & 0xFF
    fifths = low - 256 if low > 127 else low
    # `not (0 <= mode_value < len(Mode))` rejects a negative mode too: a negative
    # `raw` arithmetic-shifts to a negative high byte, which would otherwise slip
    # past a `>= len(Mode)` check and reach `Mode(mode_value)` as a bare ValueError.
    if not (0 <= mode_value < len(Mode)) or not (-_MAX_FIFTHS <= fifths <= _MAX_FIFTHS):
        raise UnsupportedKeyError(
            f"unsupported key value {raw} (mode={mode_value}, fifths={fifths})"
        )
    mode = Mode(mode_value)
    tonic = (_MAJOR_TONIC if mode is Mode.MAJOR else _MINOR_TONIC)[fifths]
    return KeySignature(fifths=fifths, mode=mode, tonic=tonic)
