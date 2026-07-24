from dataclasses import FrozenInstanceError

import pytest

from finale_file_parser.enigma.key import KeySignature, Mode, UnsupportedKeyError
from finale_file_parser.enigma.music import Note
from finale_file_parser.enigma.pitch import (
    SpelledPitch,
    spell_pitch,
    transpose_key,
    transpose_pitch,
)


def _note(harm_lev: int, harm_alt: int = 0) -> Note:
    return Note(harm_lev=harm_lev, harm_alt=harm_alt, tie_start=False, tie_end=False)


def _key(fifths: int, mode: Mode, tonic: str) -> KeySignature:
    return KeySignature(fifths=fifths, mode=mode, tonic=tonic)


C_MAJOR = _key(0, Mode.MAJOR, "C")
D_MAJOR = _key(2, Mode.MAJOR, "D")
BB_MAJOR = _key(-2, Mode.MAJOR, "Bb")
A_MINOR = _key(0, Mode.MINOR, "A")


def test_c_major_scale_up() -> None:
    got = [spell_pitch(_note(h), C_MAJOR).name for h in range(8)]
    assert got == ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]


def test_c_major_scale_down_octave_boundary_at_c() -> None:
    got = [spell_pitch(_note(h), C_MAJOR).name for h in range(-1, -8, -1)]
    assert got == ["B3", "A3", "G3", "F3", "E3", "D3", "C3"]


def test_d_major_applies_key_sharps() -> None:
    got = [spell_pitch(_note(h), D_MAJOR).name for h in range(8)]
    assert got == ["D4", "E4", "F#4", "G4", "A4", "B4", "C#5", "D5"]


def test_bb_major_applies_key_flats() -> None:
    got = [spell_pitch(_note(h), BB_MAJOR).name for h in range(8)]
    assert got == ["Bb4", "C5", "D5", "Eb5", "F5", "G5", "A5", "Bb5"]


def test_a_minor_relative_scale() -> None:
    got = [spell_pitch(_note(h), A_MINOR).name for h in range(8)]
    assert got == ["A4", "B4", "C5", "D5", "E5", "F5", "G5", "A5"]


def test_harm_alt_lowers_and_raises_against_key() -> None:
    assert spell_pitch(_note(2, harm_alt=-1), D_MAJOR).name == "F4"  # F# -> F natural
    assert spell_pitch(_note(0, harm_alt=1), C_MAJOR).name == "C#4"  # C -> C#


def test_double_accidental_names() -> None:
    assert SpelledPitch("F", 2, 4).name == "F##4"
    assert SpelledPitch("B", -2, 3).name == "Bbb3"
    assert SpelledPitch("G", 0, 4).name == "G4"


def test_spelled_pitch_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        SpelledPitch("C", 0, 4).letter = "D"  # type: ignore[misc]


def test_transpose_key_bb_instrument_c_to_d() -> None:
    written = transpose_key(C_MAJOR, interval=1, adjust=2)
    assert (written.fifths, written.mode, written.tonic) == (2, Mode.MAJOR, "D")


def test_transpose_key_f_horn_c_to_g() -> None:
    written = transpose_key(C_MAJOR, interval=4, adjust=1)
    assert (written.fifths, written.tonic) == (1, "G")


def test_transpose_key_eb_alto_c_to_a() -> None:
    written = transpose_key(C_MAJOR, interval=5, adjust=3)
    assert (written.fifths, written.tonic) == (3, "A")


def test_transpose_key_preserves_minor_mode() -> None:
    written = transpose_key(A_MINOR, interval=1, adjust=2)
    assert (written.fifths, written.mode, written.tonic) == (2, Mode.MINOR, "B")


def test_transpose_key_identity_for_concert() -> None:
    written = transpose_key(D_MAJOR, interval=0, adjust=0)
    assert (written.fifths, written.mode, written.tonic) == (2, Mode.MAJOR, "D")


def test_transpose_key_out_of_range_raises() -> None:
    with pytest.raises(UnsupportedKeyError):
        transpose_key(_key(6, Mode.MAJOR, "F#"), interval=1, adjust=2)  # 6 + 2 = 8 fifths


def test_transpose_pitch_bb_down_major_second() -> None:
    # B-flat instrument (interval 1, adjust 2): written C5 sounds Bb4.
    assert transpose_pitch(SpelledPitch("C", 0, 5), interval=1, adjust=2).name == "Bb4"


def test_transpose_pitch_octave_down() -> None:
    # interval 7, adjust 0 => T = 12: written C4 sounds C3, same letter.
    assert transpose_pitch(SpelledPitch("C", 0, 4), interval=7, adjust=0).name == "C3"


def test_transpose_pitch_octave_up() -> None:
    # interval -7 => T = -12: written C4 sounds C5.
    assert transpose_pitch(SpelledPitch("C", 0, 4), interval=-7, adjust=0).name == "C5"


def test_transpose_pitch_octave_borrow_on_letter_wrap() -> None:
    # written C4 down a major second sounds Bb3 (octave borrow across the C boundary).
    assert transpose_pitch(SpelledPitch("C", 0, 4), interval=1, adjust=2).name == "Bb3"


def test_transpose_pitch_identity_for_concert() -> None:
    assert transpose_pitch(SpelledPitch("F", 1, 4), interval=0, adjust=0).name == "F#4"
