"""The score.dat cipher.

`score.dat` is XOR-encrypted with a keystream from a BSD `rand()` linear
congruential generator seeded with a fixed constant. The generator is reseeded
at every RESET_EVERY-byte boundary, so the keystream is one constant block
repeated end to end.

The cipher parameters were not discovered by this project. They come from
denigma (https://github.com/chrisroode/denigma, MIT), whose source credits
Deguerre (https://github.com/Deguerre). This implementation is written
independently; see docs/formats/score-dat.md for the full pipeline and for what
this project did and did not derive from the corpus.
"""

from __future__ import annotations

INITIAL_STATE = 0x28006D45
MULTIPLIER = 0x41C64E6D
INCREMENT = 0x3039

RESET_EVERY = 0x20000
"""The generator is reseeded every 131,072 bytes.

Only 68 of 401 corpus archives have a score.dat larger than this, so omitting
the reset decodes 333 of 401 files correctly and fails only on the largest.
"""


def _build_keystream_block() -> bytes:
    """Generate the one constant keystream block, RESET_EVERY bytes long."""
    out = bytearray(RESET_EVERY)
    state = INITIAL_STATE
    for i in range(RESET_EVERY):
        state = (state * MULTIPLIER + INCREMENT) & 0xFFFFFFFF
        upper = (state >> 16) & 0xFFFF
        out[i] = (upper + upper // 255) & 0xFF
    return bytes(out)


_KEYSTREAM = _build_keystream_block()
"""Built once at import. Tiling this is byte-identical to stepping the LCG per
byte and measurably faster; see docs/formats/score-dat.md."""


def decrypt(data: bytes) -> bytes:
    """Return `data` XORed with the score.dat keystream.

    XOR is its own inverse, so this both encrypts and decrypts. Never raises.
    """
    if not data:
        return b""
    repeats = len(data) // RESET_EVERY + 1
    keystream = (_KEYSTREAM * repeats)[: len(data)]
    return bytes(a ^ b for a, b in zip(data, keystream, strict=True))
