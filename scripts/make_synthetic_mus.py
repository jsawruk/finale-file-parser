"""Build a synthetic .mus carrying records we wrote ourselves.

Run: PYTHONPATH=src python scripts/make_synthetic_mus.py [out.mus]

No corpus bytes. The point is a `.mus` whose *others* pool parses, so the
inspector's Records tab has real binary records to hex-dump -- the half of the
new record view a `.musx` can never exercise, because a `.musx` record arrives
as XML and has no undecoded form.

Container, 2011-era scheme: a 160-byte metadata header, then a chain of zlib
streams. Pool framing, per `enigma.mus_others._walk`: each record is a 10-byte
header (tag u16, cmper u16, part u16, length u32), `length` payload bytes, a
u32 extra length, then that many extra bytes. All little-endian.
"""

import struct
import sys
import zlib
from pathlib import Path

from finale_file_parser.version import mus as mus_header

# Mirrors `enigma.mus_others`: a 10-byte record header, then the payload, then a
# u32 extra length and that many extra bytes. Restated rather than imported so
# this script documents the shape it writes instead of hiding it behind a name.
_HEADER = 10
_EXTRA_LENGTH = 4

# Tags this reader names, so the tree shows words rather than numbers.
TAG_MEAS_SPEC = 0x0001
TAG_STAFF_SPEC = 0x000B


def record(tag: int, cmper: int, part: int, payload: bytes, extra: bytes = b"") -> bytes:
    """One others record, framed exactly as `_walk` reads it."""
    out = struct.pack("<HHHI", tag, cmper, part, len(payload)) + payload
    out += struct.pack("<I", len(extra)) + extra
    assert len(out) == _HEADER + len(payload) + _EXTRA_LENGTH + len(extra)
    return out


def others_pool() -> bytes:
    """A pool of recognisable records. `_walk` wants at least `_MIN_RECORDS`
    before it will accept a stream as the others pool, and it wants them to tile
    the stream exactly."""
    out = b""
    # Enough records that the pool inflates past _MIN_FIRST_STREAM_OUTPUT (4096),
    # the floor the chain's first stream must clear to be found by scanning.
    for measure in range(1, 301):
        # A plausible measSpec shape: widths, then a flags byte pair.
        payload = struct.pack("<HHHHH", 288 * 4, 0, 0, 0, 0x0100)
        out += record(TAG_MEAS_SPEC, measure, 0, payload)
    for staff in (1, 2):
        out += record(TAG_STAFF_SPEC, staff, 0, struct.pack("<HHHH", 0, 96, 0, 0))
    return out


def build(path: Path) -> None:
    header = bytearray(b"\x00" * mus_header.MUS_METADATA_SIZE)
    # The banner the version reader looks for. Year past the DCL cutoff so the
    # zlib scheme is tried first; the rest of the metadata stays zeroed, which
    # the reader reports as an unknown version rather than refusing the file.
    banner = b"ENIGMA BINARY FILE V2011"
    header[0 : len(banner)] = banner

    pool = zlib.compress(others_pool(), 6)
    # A short preamble before the chain, as real files carry.
    body = b"\x00" * 0x20 + pool
    path.write_bytes(bytes(header) + body)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "synthetic.mus")
    build(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")

    from finale_file_parser.enigma.mus_others import read_mus_others

    records = read_mus_others(out)
    print(f"others pool parsed: {len(records)} records")
    print(
        f"  first: tag={records[0].tag} cmper={records[0].cmper} "
        f"payload={records[0].payload.hex(' ')}"
    )
