"""PKWARE Data Compression Library ("implode") decompressor.

Legacy `.mus` files (Finale 2001-2005) store their payload as a single PKWARE
DCL stream. No stdlib module reads this format, so it is implemented here.

This is an independent Python port of Mark Adler's `blast.c`
(https://github.com/madler/zlib, `contrib/blast`, zlib licence). The format
knowledge -- the bit-length tables, the inverted canonical code assignment, the
length/distance encodings -- is his; the implementation and its safety limits
are this project's. See `docs/REFERENCES.md`.

Correctness is pinned by `blast.c`'s own documented test vector; see
`tests/enigma/test_blast.py`.
"""

from __future__ import annotations

from finale_file_parser.errors import FinaleFileError

__all__ = ["CorruptDclStreamError", "blast_decompress"]


class CorruptDclStreamError(FinaleFileError):
    """The bytes are not a decodable PKWARE DCL stream.

    Raised for a bad header, a malformed code, a back-reference pointing before
    the start of the output, truncated input, or output exceeding the cap.
    """


_LEN_BASE = (3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264)
_LEN_EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8)

_END_OF_STREAM = 519
"""A decoded length of 519 terminates the stream rather than copying."""

# Bit lengths for the three fixed Huffman tables, run-length coded exactly as in
# blast.c: high nibble + 1 = repeat count, low nibble = code bit length.
_LITERAL_LENGTHS = (
    11,
    124,
    8,
    7,
    28,
    7,
    188,
    13,
    76,
    4,
    10,
    8,
    12,
    10,
    12,
    10,
    8,
    23,
    8,
    9,
    7,
    6,
    7,
    8,
    7,
    6,
    55,
    8,
    23,
    24,
    12,
    11,
    7,
    9,
    11,
    12,
    6,
    7,
    22,
    5,
    7,
    24,
    6,
    11,
    9,
    6,
    7,
    22,
    7,
    11,
    38,
    7,
    9,
    8,
    25,
    11,
    8,
    11,
    9,
    12,
    8,
    12,
    5,
    38,
    5,
    38,
    5,
    11,
    7,
    5,
    6,
    21,
    6,
    10,
    53,
    8,
    7,
    24,
    10,
    27,
    44,
    253,
    253,
    253,
    252,
    252,
    252,
    13,
    12,
    45,
    12,
    45,
    12,
    61,
    12,
    45,
    44,
    173,
)
_LENGTH_LENGTHS = (2, 35, 36, 53, 38, 23)
_DISTANCE_LENGTHS = (2, 20, 53, 230, 247, 151, 248)

_VALID_LITERAL_FLAGS = (0, 1)
_VALID_DICT_BITS = (4, 5, 6)
"""Dictionary size selector: 1024, 2048 or 4096 bytes."""

_MAX_CODE_BITS = 16


class _Huffman:
    """A canonical code table in blast.c's form: counts per length, plus symbols."""

    __slots__ = ("count", "symbol")

    def __init__(self, run_length_coded: tuple[int, ...]) -> None:
        lengths: list[int] = []
        for byte in run_length_coded:
            lengths.extend([byte & 0x0F] * ((byte >> 4) + 1))
        self.count = [0] * (_MAX_CODE_BITS + 1)
        for length in lengths:
            self.count[length] += 1
        offsets = [0] * (_MAX_CODE_BITS + 1)
        for length in range(1, _MAX_CODE_BITS - 1):
            offsets[length + 1] = offsets[length] + self.count[length]
        self.symbol = [0] * len(lengths)
        for symbol, length in enumerate(lengths):
            if length:
                self.symbol[offsets[length]] = symbol
                offsets[length] += 1


_LITERAL_CODE = _Huffman(_LITERAL_LENGTHS)
_LENGTH_CODE = _Huffman(_LENGTH_LENGTHS)
_DISTANCE_CODE = _Huffman(_DISTANCE_LENGTHS)


class _BitReader:
    """LSB-first bit reader over a fixed buffer."""

    __slots__ = ("_data", "_pos", "_bits", "_count")

    def __init__(self, data: bytes, start: int) -> None:
        self._data = data
        self._pos = start
        self._bits = 0
        self._count = 0

    def take(self, needed: int) -> int:
        value = self._bits
        while self._count < needed:
            if self._pos >= len(self._data):
                raise CorruptDclStreamError("stream ended mid-symbol (truncated input)")
            value |= self._data[self._pos] << self._count
            self._pos += 1
            self._count += 8
        self._bits = value >> needed
        self._count -= needed
        return value & ((1 << needed) - 1)

    def decode(self, table: _Huffman) -> int:
        """Decode one symbol.

        PKWARE's canonical codes are stored inverted relative to the usual
        convention, hence the `^ 1` on each bit -- getting this wrong yields
        plausible-looking garbage rather than an obvious failure.
        """
        code = first = index = 0
        for length in range(1, _MAX_CODE_BITS):
            code |= self.take(1) ^ 1
            count = table.count[length]
            if code < first + count:
                return table.symbol[index + (code - first)]
            index += count
            first = (first + count) << 1
            code <<= 1
        raise CorruptDclStreamError("no valid Huffman code within 16 bits")


def blast_decompress(data: bytes, start: int, max_output: int) -> bytes:
    """Decompress the PKWARE DCL stream beginning at `start` in `data`.

    `max_output` is required, not optional: this runs on untrusted input, and a
    malformed stream can otherwise expand without bound. The limit is enforced
    while decoding rather than after, so a bomb is refused before it is built.

    Raises:
        CorruptDclStreamError: bad header, malformed code, back-reference
            before the start of output, truncated input, or output past the cap.
    """
    if start < 0 or start + 2 > len(data):
        raise CorruptDclStreamError(f"no room for a DCL header at offset {start}")
    literal_flag = data[start]
    dictionary_bits = data[start + 1]
    if literal_flag not in _VALID_LITERAL_FLAGS:
        raise CorruptDclStreamError(f"invalid DCL literal flag {literal_flag}")
    if dictionary_bits not in _VALID_DICT_BITS:
        raise CorruptDclStreamError(f"invalid DCL dictionary size selector {dictionary_bits}")

    reader = _BitReader(data, start + 2)
    out = bytearray()
    while True:
        if reader.take(1):
            symbol = reader.decode(_LENGTH_CODE)
            length = _LEN_BASE[symbol] + reader.take(_LEN_EXTRA[symbol])
            if length == _END_OF_STREAM:
                return bytes(out)
            symbol = reader.decode(_DISTANCE_CODE)
            if length == 2:
                distance = (symbol << 2) + reader.take(2)
            else:
                distance = (symbol << dictionary_bits) + reader.take(dictionary_bits)
            distance += 1
            if distance > len(out):
                raise CorruptDclStreamError(
                    f"back-reference of {distance} reaches before the start of output"
                )
            source = len(out) - distance
            # Overlapping copies are legal and common: distance 1 with length
            # 500 repeats one byte 500 times. A forward byte-at-a-time copy
            # implements that correctly; slicing does not.
            for offset in range(length):
                out.append(out[source + offset])
        else:
            out.append(reader.decode(_LITERAL_CODE) if literal_flag else reader.take(8))
        if len(out) > max_output:
            raise CorruptDclStreamError(
                f"DCL stream exceeds the {max_output}-byte output cap; refusing"
            )
