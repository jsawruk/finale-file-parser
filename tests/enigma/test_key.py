import pytest

from finale_file_parser.enigma.key import (
    KeySignature,
    Mode,
    UnsupportedKeyError,
    decode_key,
    tonic_for,
)


def test_tonic_for_major_and_minor() -> None:
    assert tonic_for(0, Mode.MAJOR) == "C"
    assert tonic_for(2, Mode.MAJOR) == "D"
    assert tonic_for(-2, Mode.MAJOR) == "Bb"
    assert tonic_for(0, Mode.MINOR) == "A"
    assert tonic_for(-1, Mode.MINOR) == "D"


@pytest.mark.parametrize(
    "raw,fifths,mode,tonic",
    [
        (0, 0, Mode.MAJOR, "C"),
        (1, 1, Mode.MAJOR, "G"),
        (2, 2, Mode.MAJOR, "D"),  # +2 = D major (the spec's example)
        (3, 3, Mode.MAJOR, "A"),
        (255, -1, Mode.MAJOR, "F"),  # -1 = F major
        (254, -2, Mode.MAJOR, "Bb"),
        (253, -3, Mode.MAJOR, "Eb"),
        (251, -5, Mode.MAJOR, "Db"),
        (256, 0, Mode.MINOR, "A"),  # 0 fifths, minor = A minor
        (257, 1, Mode.MINOR, "E"),
        (511, -1, Mode.MINOR, "D"),
        (510, -2, Mode.MINOR, "G"),
        (507, -5, Mode.MINOR, "Bb"),
    ],
)
def test_decodes_corpus_keys(raw: int, fifths: int, mode: Mode, tonic: str) -> None:
    key = decode_key(raw)
    assert key == KeySignature(fifths=fifths, mode=mode, tonic=tonic)


def test_enharmonic_keys_are_distinct() -> None:
    # +6 (F# major, raw 6) and -6 (Gb major, raw 250) must not collide
    fsharp = decode_key(6)
    gflat = decode_key(250)
    assert fsharp == KeySignature(6, Mode.MAJOR, "F#")
    assert gflat == KeySignature(-6, Mode.MAJOR, "Gb")
    assert fsharp != gflat


def test_extreme_signatures() -> None:
    assert decode_key(7) == KeySignature(7, Mode.MAJOR, "C#")
    assert decode_key(249) == KeySignature(-7, Mode.MAJOR, "Cb")


def test_mode_two_or_more_raises() -> None:
    with pytest.raises(UnsupportedKeyError):
        decode_key(512)  # mode 2 — a church mode / custom key, not decoded


def test_fifths_out_of_range_raises() -> None:
    with pytest.raises(UnsupportedKeyError):
        decode_key(8)  # fifths +8, beyond ±7
    with pytest.raises(UnsupportedKeyError):
        decode_key(248)  # low byte 248 -> fifths -8


def test_frozen() -> None:
    key = decode_key(0)
    with pytest.raises((AttributeError, TypeError)):
        key.fifths = 1  # type: ignore[misc]


def test_error_is_a_finale_file_error() -> None:
    from finale_file_parser.errors import FinaleFileError

    assert issubclass(UnsupportedKeyError, FinaleFileError)


@pytest.mark.parametrize("raw", [-1, -2, -256, -257, -512])
def test_negative_raw_raises_unsupported_not_bare_valueerror(raw: int) -> None:
    """A negative raw (a plausible XML-parsed integer) arithmetic-shifts to a
    negative mode byte; it must raise UnsupportedKeyError, never a bare
    ValueError leaked from Mode()."""
    with pytest.raises(UnsupportedKeyError):
        decode_key(raw)


# Exhaustive coverage of the tonic tables: all 30 standard keys (major and minor
# x fifths -7..+7). The tonic is the anchor every spelled pitch resolves through,
# so a silent table regression must fail a test. Expected tonics are the circle
# of fifths (major) and its relative minor.
_ALL_MAJOR = {
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
_ALL_MINOR = {
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


@pytest.mark.parametrize("fifths", range(-7, 8))
def test_every_major_tonic(fifths: int) -> None:
    raw = fifths & 0xFF
    assert decode_key(raw) == KeySignature(fifths, Mode.MAJOR, _ALL_MAJOR[fifths])


@pytest.mark.parametrize("fifths", range(-7, 8))
def test_every_minor_tonic(fifths: int) -> None:
    raw = (1 << 8) | (fifths & 0xFF)
    assert decode_key(raw) == KeySignature(fifths, Mode.MINOR, _ALL_MINOR[fifths])
