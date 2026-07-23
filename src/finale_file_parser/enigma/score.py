"""Decode a .musx's score.dat into EnigmaXML.

Pipeline: open the container, read score.dat, decrypt, inflate. See
docs/formats/score-dat.md.
"""

from __future__ import annotations

import os
import zlib

from finale_file_parser.container.musx import open_musx
from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.models import CorruptScoreError

GZIP_MAGIC = b"\x1f\x8b"

MAX_INFLATED = 64 * 1024 * 1024
"""Refuse output larger than 64 MiB. The largest corpus file inflates to
10,781,112 bytes, and observed ratios run 25.6x to 37.3x."""

_CHUNK = 1 << 20
_GZIP_WBITS = 31
"""zlib window size selecting gzip framing rather than raw or zlib framing."""


def score_xml(path: str | os.PathLike[str]) -> bytes:
    """Return the EnigmaXML inside the `.musx` at `path`.

    Raises:
        FileNotFoundError: no such path.
        NotFinaleFileError: not a readable zip, or not a Finale archive.
        CorruptContainerError: the archive violates a structural limit, or
            carries no score.dat.
        CorruptScoreError: the score stream is not decodable EnigmaXML.
    """
    with open_musx(path) as container:
        encrypted = container.score_stream()
    plaintext = decrypt(encrypted)
    if not plaintext.startswith(GZIP_MAGIC):
        raise CorruptScoreError(
            f"{path} score stream is not a gzip stream after decryption "
            f"(starts {plaintext[:4].hex(' ')!r})"
        )
    return _inflate(plaintext, path)


def _inflate(data: bytes, path: str | os.PathLike[str]) -> bytes:
    """Inflate `data`, refusing to allocate past MAX_INFLATED.

    Decompresses incrementally rather than in one call: a one-shot decompress
    on untrusted input allocates the whole output before anything can object,
    which is the entire decompression-bomb problem.
    """
    engine = zlib.decompressobj(wbits=_GZIP_WBITS)
    out = bytearray()
    try:
        chunk = engine.decompress(data, _CHUNK)
        while chunk:
            out += chunk
            if len(out) > MAX_INFLATED:
                raise CorruptScoreError(
                    f"{path} score stream exceeds the {MAX_INFLATED}-byte inflation cap; refusing"
                )
            # Feed back `unconsumed_tail`, NOT b"". When `decompress` is given a
            # max_length it parks the rest of the input there; passing b"" makes
            # the loop exit early and silently truncates the output to one chunk.
            chunk = engine.decompress(engine.unconsumed_tail, _CHUNK)
    except zlib.error as exc:
        raise CorruptScoreError(f"{path} score stream failed to inflate: {exc}") from exc
    if not engine.eof:
        raise CorruptScoreError(f"{path} score stream is a truncated gzip stream")
    return bytes(out)
