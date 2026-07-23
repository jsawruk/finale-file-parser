from finale_file_parser.enigma.crypt import (
    INITIAL_STATE,
    RESET_EVERY,
    decrypt,
)


def _reference(data: bytes) -> bytes:
    """Per-byte LCG, written independently of the implementation.

    Deliberately the naive form from docs/formats/score-dat.md, so the tiled
    implementation is checked against a different construction rather than
    against itself.
    """
    out = bytearray(len(data))
    state = INITIAL_STATE
    for i, byte in enumerate(data):
        if i % RESET_EVERY == 0:
            state = INITIAL_STATE
        state = (state * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        upper = (state >> 16) & 0xFFFF
        out[i] = byte ^ ((upper + upper // 255) & 0xFF)
    return bytes(out)


def test_matches_the_reference_implementation() -> None:
    data = bytes(range(256)) * 8
    assert decrypt(data) == _reference(data)


def test_round_trips() -> None:
    """XOR is its own inverse, so decrypting twice returns the input."""
    data = b"the quick brown fox" * 100
    assert decrypt(decrypt(data)) == data


def test_known_keystream_prefix() -> None:
    """keystream[0:3] is 09 5c 5b — derived in docs/formats/score-dat.md from a
    real ciphertext XOR the gzip magic, independently of the cipher source."""
    assert decrypt(bytes(3)) == bytes([0x09, 0x5C, 0x5B])


def test_decrypts_a_real_gzip_header_shape() -> None:
    """Ciphertext 16 d7 53 must decrypt to the gzip magic 1f 8b 08."""
    assert decrypt(bytes([0x16, 0xD7, 0x53])) == b"\x1f\x8b\x08"


def test_keystream_resets_at_the_block_boundary() -> None:
    """The byte at RESET_EVERY must use the same keystream as byte 0.

    This is the bug that hides: only 68 of 401 corpus archives exceed
    RESET_EVERY, so an implementation without the reset decodes 333 of 401
    files correctly.

    RESET_EVERY is pinned to the corpus-verified value here, independently of
    whatever the implementation claims it to be: importing RESET_EVERY and
    checking self-consistency alone would be tautological (a keystream block
    built and tiled with *any* period reproduces itself at that period), so
    that check alone can't catch a wrong constant.
    """
    assert RESET_EVERY == 0x20000
    plain = bytes(RESET_EVERY + 16)
    ks = decrypt(plain)
    assert ks[:16] == ks[RESET_EVERY : RESET_EVERY + 16]


def test_matches_reference_across_the_boundary() -> None:
    data = bytes((i * 7 + 3) & 0xFF for i in range(RESET_EVERY + 5000))
    assert decrypt(data) == _reference(data)


def test_empty_input() -> None:
    assert decrypt(b"") == b""


def test_single_byte() -> None:
    assert decrypt(b"\x00") == bytes([0x09])
