"""Unit tests for the `.mus` others-pool reader.

The pool is exercised through `read_mus_others` against synthetic streams, so
the record walk, the padding rule and every safety limit are covered without a
corpus file. `read_mus_streams` is the only seam that needs standing in for.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from finale_file_parser.enigma import mus_others
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_others import MusOther, read_mus_others

PATH = "unused.mus"
"""`read_mus_streams` is stubbed out, so no file is ever opened."""


def record(tag: int, cmper: int, part: int, payload: bytes) -> bytes:
    """One well-formed record: header, payload, four-byte trailer."""
    header = (
        tag.to_bytes(2, "little")
        + cmper.to_bytes(2, "little")
        + part.to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
    )
    return header + payload + bytes(4)


def record_with_extra(tag: int, cmper: int, payload: bytes, extra: bytes) -> bytes:
    """A record carrying a second block after its payload."""
    header = (
        tag.to_bytes(2, "little")
        + cmper.to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
    )
    return header + payload + len(extra).to_bytes(4, "little") + extra


def pool(*records: bytes) -> bytes:
    """A stream holding `records`, padded out to the reader's floor."""
    filler = b"".join(record(9, n, 0, b"\x00\x00") for n in range(mus_others._MIN_RECORDS))
    return b"".join(records) + filler


@pytest.fixture
def streams(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Make `read_mus_streams` return whatever a test hands this."""

    def install(*payloads: bytes) -> None:
        monkeypatch.setattr(mus_others, "read_mus_streams", lambda _path: list(payloads))

    return install


def test_reads_a_record_s_key_and_payload(streams: Callable[..., None]) -> None:
    streams(pool(record(146, 3, 0, b"\x09\x00\x00\x00")))
    assert read_mus_others(PATH)[0] == MusOther(
        tag=146, cmper=3, part=0, payload=b"\x09\x00\x00\x00"
    )


def test_reads_consecutive_records_of_differing_length(streams: Callable[..., None]) -> None:
    streams(pool(record(176, 1, 0, bytes(26)), record(176, 1, 1, bytes(8))))
    first, second = read_mus_others(PATH)[:2]
    assert (first.cmper, first.part, len(first.payload)) == (1, 0, 26)
    assert (second.cmper, second.part, len(second.payload)) == (1, 1, 8)


def test_skips_two_byte_padding_between_sections(streams: Callable[..., None]) -> None:
    streams(pool(record(146, 3, 0, b""), bytes(48), record(147, 4, 0, b"")))
    tags = [r.tag for r in read_mus_others(PATH)[:2]]
    assert tags == [146, 147]


def test_skips_all_ones_filler_as_well_as_zeros(streams: Callable[..., None]) -> None:
    """0xFFFF is filler, like 0x0000 -- see the details reader's test for why."""
    streams(pool(record(146, 3, 0, b""), b"\xff\xff" * 10, record(147, 4, 0, b"")))
    assert [r.tag for r in read_mus_others(PATH)[:2]] == [146, 147]


def test_an_extra_block_is_skipped_whole(streams: Callable[..., None]) -> None:
    """What looks like a fixed four-byte trailer is the length of a second
    block. It is zero on 99.4% of corpus records, so ignoring it went unnoticed
    -- and left the walk short by 24, 48 or 96 bytes on the rest, which is what
    stopped one document."""
    # Non-zero filler: an all-zero extra block would be skipped as padding
    # anyway, so the test would pass with or without the field.
    streams(pool(record_with_extra(146, 3, b"\x01\x02", b"\xaa" * 24), record(147, 9, 0, b"")))
    first, second = read_mus_others(PATH)[:2]
    assert (first.tag, first.cmper, first.payload) == (146, 3, b"\x01\x02")
    assert (second.tag, second.cmper) == (147, 9)


def test_an_extra_block_is_kept_not_discarded(streams: Callable[..., None]) -> None:
    """It is real record data of unknown meaning; dropping it would lose
    something a later reader could not recover."""
    streams(pool(record_with_extra(146, 3, b"\x01\x02", b"\xaa" * 24)))
    record = read_mus_others(PATH)[0]
    assert record.payload == b"\x01\x02"
    assert record.extra == b"\xaa" * 24


def test_a_record_without_an_extra_block_has_none(streams: Callable[..., None]) -> None:
    streams(pool(record(146, 3, 0, b"\x01\x02")))
    assert read_mus_others(PATH)[0].extra == b""


def test_an_extra_block_is_not_read_as_records(streams: Callable[..., None]) -> None:
    """Under-advancing parses the extra block as records: six phantom records
    with implausible tags appeared in one corpus document that way."""
    extra = b"".join(record(48, n, 0, b"") for n in range(3))
    streams(pool(record_with_extra(146, 3, b"", extra)))
    assert all(r.tag != 48 for r in read_mus_others(PATH))


def test_picks_the_stream_that_tiles_exactly(streams: Callable[..., None]) -> None:
    streams(b"\x01\x02\x03", pool(record(146, 3, 0, b"")))
    assert read_mus_others(PATH)[0].tag == 146


def test_rejects_a_stream_whose_records_do_not_tile_it(streams: Callable[..., None]) -> None:
    streams(pool(record(146, 3, 0, b"")) + b"\x92\x00\x03\x00\x00\x00\xff\x00\x00\x00")
    with pytest.raises(CorruptScoreError, match="no recognisable others pool"):
        read_mus_others(PATH)


def test_rejects_a_payload_length_over_the_cap(streams: Callable[..., None]) -> None:
    """The cap must fire on its own, not because the stream ran out.

    The stream is deliberately long enough to satisfy the bounds check, so
    deleting `_MAX_PAYLOAD` makes this record parse and the test fail.
    """
    oversized = mus_others._MAX_PAYLOAD + 1
    header = (
        (146).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + oversized.to_bytes(4, "little")
    )
    streams(pool(header + bytes(oversized + 4)))
    with pytest.raises(CorruptScoreError):
        read_mus_others(PATH)


def test_rejects_more_records_than_the_cap_allows(
    streams: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mus_others, "_MAX_RECORDS", 3)
    streams(pool(*[record(146, n, 0, b"") for n in range(8)]))
    with pytest.raises(CorruptScoreError):
        read_mus_others(PATH)


def test_rejects_a_truncated_final_record(streams: Callable[..., None]) -> None:
    streams(pool(record(146, 3, 0, b"\x01\x02\x03\x04"))[:-3])
    with pytest.raises(CorruptScoreError):
        read_mus_others(PATH)


def test_rejects_a_stream_of_padding_alone(streams: Callable[..., None]) -> None:
    streams(bytes(4096))
    with pytest.raises(CorruptScoreError):
        read_mus_others(PATH)
