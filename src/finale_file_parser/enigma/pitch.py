"""Spell a Note (harmLev/harmAlt) plus the key in force into an absolute pitch.

Combines decode_key (tonic + key accidentals), read_entry (harmLev/harmAlt), and
the staff's transposition into written and concert (sounding) spelled pitches. The
transposition encoding is reverse-engineered from the corpus; see
docs/superpowers/specs/2026-07-24-pitch-spelling-design.md for the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.key import (
    KeySignature,
    UnsupportedKeyError,
    tonic_for,
)
from finale_file_parser.enigma.music import Note

_LETTERS = "CDEFGAB"  # C-indexed, so the octave boundary falls at C (scientific pitch)
_SHARP_ORDER = "FCGDAEB"
_FLAT_ORDER = "BEADGCF"
_LETTER_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_OCTAVE = 7  # diatonic steps per octave
_MIDDLE_C_OCTAVE = 4  # harm_lev = 0 tonic sits in octave 4 (middle C region)
_MAX_FIFTHS = 7


def _key_accidental(letter: str, fifths: int) -> int:
    """The alteration a key signature applies to a bare letter: +1 sharp, -1 flat, 0 natural."""
    if fifths > 0 and letter in _SHARP_ORDER[:fifths]:
        return 1
    if fifths < 0 and letter in _FLAT_ORDER[:-fifths]:
        return -1
    return 0


@dataclass(frozen=True)
class SpelledPitch:
    """An absolute spelled pitch: letter, alteration, and octave."""

    letter: str
    """The note letter, "C".."B"."""

    alteration: int
    """Semitones vs the natural letter: sharps positive, flats negative."""

    octave: int
    """Scientific-pitch octave; middle C is C4."""

    @property
    def name(self) -> str:
        """The pitch name, e.g. "C#5", "Bb3", "F4", "F##4"."""
        if self.alteration > 0:
            accidental = "#" * self.alteration
        elif self.alteration < 0:
            accidental = "b" * -self.alteration
        else:
            accidental = ""
        return f"{self.letter}{accidental}{self.octave}"


def _midi(pitch: SpelledPitch) -> int:
    """Semitone number of a spelled pitch; C4 = 60."""
    return (pitch.octave + 1) * 12 + _LETTER_SEMITONE[pitch.letter] + pitch.alteration


def _natural_midi(letter: str, octave: int) -> int:
    """Semitone number of a bare (natural) letter at an octave; C4 = 60."""
    return (octave + 1) * 12 + _LETTER_SEMITONE[letter]


def spell_pitch(note: Note, key: KeySignature) -> SpelledPitch:
    """Spell a note relative to a key into an absolute pitch.

    Given the written key this yields the written pitch; given the concert key it
    yields the concert letter and accidental.
    """
    pos = _LETTERS.index(key.tonic[0]) + note.harm_lev
    letter = _LETTERS[pos % _OCTAVE]
    octave = _MIDDLE_C_OCTAVE + pos // _OCTAVE
    alteration = _key_accidental(letter, key.fifths) + note.harm_alt
    return SpelledPitch(letter=letter, alteration=alteration, octave=octave)


def transpose_key(key: KeySignature, interval: int, adjust: int) -> KeySignature:
    """The written key a transposing staff reads, from its concert key.

    `adjust` shifts the key signature on the circle of fifths; `mode` is preserved.
    `interval` (diatonic steps written sits above concert) is accepted for symmetry
    with transpose_pitch and does not affect the key. Raises UnsupportedKeyError if
    the written key leaves -7..+7 fifths.
    """
    fifths = key.fifths + adjust
    if not (-_MAX_FIFTHS <= fifths <= _MAX_FIFTHS):
        raise UnsupportedKeyError(
            f"transposed key out of range: {key.fifths} + {adjust} = {fifths} fifths"
        )
    return KeySignature(fifths=fifths, mode=key.mode, tonic=tonic_for(fifths, key.mode))


def transpose_pitch(pitch: SpelledPitch, interval: int, adjust: int) -> SpelledPitch:
    """Transpose a written pitch down to its concert (sounding) pitch.

    The concert pitch is `interval` diatonic steps and T semitones below the written
    pitch, where T = ((7 * adjust) % 12) + 12 * (interval // _OCTAVE). For a concert
    staff (interval 0, adjust 0) this is the identity.
    """
    semitones = (7 * adjust) % 12 + 12 * (interval // _OCTAVE)
    dpos = pitch.octave * _OCTAVE + _LETTERS.index(pitch.letter) - interval
    letter = _LETTERS[dpos % _OCTAVE]
    octave = dpos // _OCTAVE
    alteration = _midi(pitch) - semitones - _natural_midi(letter, octave)
    return SpelledPitch(letter=letter, alteration=alteration, octave=octave)


@dataclass(frozen=True)
class StaffTransposition:
    """A staff's transposition: how its written pitch sits above concert."""

    interval: int
    """Diatonic steps the written pitch sits above concert."""

    adjust: int
    """The written key signature's shift, in fifths."""

    @property
    def is_concert(self) -> bool:
        """True when the staff is concert pitch (no transposition)."""
        return self.interval == 0 and self.adjust == 0


def read_transposition(staff_spec: Record) -> StaffTransposition:
    """Read a staffSpec's transposition, defaulting to concert pitch when absent.

    Raises ValueError if a present interval/adjust field is not an integer (malformed
    input fails loudly rather than silently spelling the wrong pitch).
    """
    transposition = staff_spec.fields.get("transposition")
    if not isinstance(transposition, Record):
        return StaffTransposition(interval=0, adjust=0)
    keysig = transposition.fields.get("keysig")
    if not isinstance(keysig, Record):
        return StaffTransposition(interval=0, adjust=0)
    interval = keysig.fields.get("interval")
    adjust = keysig.fields.get("adjust")
    return StaffTransposition(
        interval=int(interval) if isinstance(interval, str) and interval else 0,
        adjust=int(adjust) if isinstance(adjust, str) and adjust else 0,
    )


@dataclass(frozen=True)
class SpelledNote:
    """A note spelled as both its written and its concert (sounding) pitch."""

    written: SpelledPitch
    """The pitch as printed on the (possibly transposing) staff."""

    concert: SpelledPitch
    """The sounding pitch."""


def spell_note(
    note: Note, concert_key: KeySignature, transposition: StaffTransposition
) -> SpelledNote:
    """Spell a note into both its written and concert (sounding) pitch."""
    written_key = transpose_key(concert_key, transposition.interval, transposition.adjust)
    written = spell_pitch(note, written_key)
    concert = transpose_pitch(written, transposition.interval, transposition.adjust)
    return SpelledNote(written=written, concert=concert)
