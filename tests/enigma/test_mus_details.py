"""Unit tests for the `.mus` details-pool reader.

Exercised through `read_mus_details` against synthetic streams, so the record
walk, the padding rule and every safety limit are covered without a corpus
file. The test that matters most is that the twelve-byte details header and the
ten-byte `others` header do not accept each other's streams.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from finale_file_parser.enigma import mus_details, mus_others
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_details import MusDetailRecord, read_mus_details

PATH = "unused.mus"
"""`read_mus_streams` is stubbed out, so no file is ever opened."""


def record(tag: int, cmper1: int, cmper2: int, inci: int, payload: bytes) -> bytes:
    """One well-formed record: twelve-byte header, payload, four-byte trailer."""
    header = (
        tag.to_bytes(2, "little")
        + cmper1.to_bytes(2, "little")
        + cmper2.to_bytes(2, "little")
        + inci.to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
    )
    return header + payload + bytes(4)


def record_with_extra(tag: int, cmper1: int, cmper2: int, payload: bytes, extra: bytes) -> bytes:
    """A record carrying a second block after its payload."""
    header = (
        tag.to_bytes(2, "little")
        + cmper1.to_bytes(2, "little")
        + cmper2.to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
    )
    return header + payload + len(extra).to_bytes(4, "little") + extra


def pool(*records: bytes) -> bytes:
    """A stream holding `records`, padded out to the reader's floor."""
    filler = b"".join(record(1044, 1, n, 0, bytes(20)) for n in range(mus_details._MIN_RECORDS))
    return b"".join(records) + filler


@pytest.fixture
def streams(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Make `read_mus_streams` return whatever a test hands this."""

    def install(*payloads: bytes) -> None:
        monkeypatch.setattr(mus_details, "read_mus_streams", lambda _path: list(payloads))

    return install


def test_reads_a_record_s_key_pair_and_payload(streams: Callable[..., None]) -> None:
    streams(pool(record(1044, 1, 7, 0, b"\x00\x00\x00\x00\x4b\x00\x20\x00")))
    assert read_mus_details(PATH)[0] == MusDetailRecord(
        tag=1044, cmper1=1, cmper2=7, inci=0, payload=b"\x00\x00\x00\x00\x4b\x00\x20\x00"
    )


def test_reads_consecutive_records_of_differing_length(
    streams: Callable[..., None],
) -> None:
    streams(pool(record(1043, 2, 1, 0, bytes(40)), record(1044, 2, 2, 0, bytes(20))))
    first, second = read_mus_details(PATH)[:2]
    assert (first.tag, len(first.payload)) == (1043, 40)
    assert (second.tag, len(second.payload)) == (1044, 20)


def test_keeps_a_non_zero_incidence(streams: Callable[..., None]) -> None:
    """`inci` is zero throughout the corpus, so nothing else would catch a
    reader that dropped the field or read the wrong two bytes."""
    streams(pool(record(1044, 1, 1, 3, bytes(20))))
    assert read_mus_details(PATH)[0].inci == 3


def test_skips_two_byte_padding_between_sections(streams: Callable[..., None]) -> None:
    streams(pool(record(1044, 1, 1, 0, b""), bytes(48), record(1043, 2, 1, 0, b"")))
    assert [r.tag for r in read_mus_details(PATH)[:2]] == [1044, 1043]


def test_skips_all_ones_filler_as_well_as_zeros(streams: Callable[..., None]) -> None:
    """A run of 0xFFFF parses as records of declared length 0, which leaves the
    walk four bytes short of the next real record each time. Seven corpus
    documents stopped here before it was recognised as filler."""
    streams(pool(record(1044, 1, 1, 0, b""), b"\xff\xff" * 10, record(1043, 2, 1, 0, b"")))
    assert [r.tag for r in read_mus_details(PATH)[:2]] == [1044, 1043]


def test_all_ones_filler_yields_no_record(streams: Callable[..., None]) -> None:
    """Filler must vanish, not become a tag-65535 record: the old walk produced
    four such phantoms in one corpus document."""
    streams(pool(b"\xff\xff" * 12))
    assert all(r.tag != 0xFFFF for r in read_mus_details(PATH))


def test_an_extra_block_is_skipped_whole(streams: Callable[..., None]) -> None:
    """The four bytes after a payload are the length of a second block, not a
    fixed trailer -- see the others reader's test for how that was found."""
    # Non-zero filler, or an all-zero block would be skipped as padding anyway.
    streams(
        pool(record_with_extra(1044, 2, 7, bytes(20), b"\xaa" * 48), record(1043, 5, 1, 0, b""))
    )
    first, second = read_mus_details(PATH)[:2]
    assert (first.tag, first.cmper1, first.cmper2) == (1044, 2, 7)
    assert (second.tag, second.cmper1) == (1043, 5)


def test_an_extra_block_is_kept_not_discarded(streams: Callable[..., None]) -> None:
    streams(pool(record_with_extra(1044, 2, 7, bytes(20), b"\xbb" * 48)))
    assert read_mus_details(PATH)[0].extra == b"\xbb" * 48


def test_picks_the_stream_that_tiles_exactly(streams: Callable[..., None]) -> None:
    streams(b"\x01\x02\x03", pool(record(1044, 1, 1, 0, bytes(20))))
    assert read_mus_details(PATH)[0].tag == 1044


PAYLOAD_LENGTHS = (12, 26, 8, 24, 96, 48)
"""Payload lengths taken from real `others` sections, for the rejection tests.

Mutual rejection is **not structural**: a degenerate stream of uniform
zero-payload records satisfies both readers' rules, because each reads its
length field out of the other's zeroed payload and gets a self-consistent
walk. It holds on every corpus pool and on records of varying length, which is
what these tests pin -- not a guarantee that no stream can satisfy both.
"""


def mus_others_record(tag: int, cmper: int, part: int, payload: bytes) -> bytes:
    """An `others` record: the ten-byte header, for the rejection tests."""
    header = (
        tag.to_bytes(2, "little")
        + cmper.to_bytes(2, "little")
        + part.to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
    )
    return header + payload + bytes(4)


def others_pool() -> bytes:
    """An `others` stream shaped like a real one: varied, non-zero payloads."""
    return b"".join(
        mus_others_record(
            146 + n % 3,
            n,
            0,
            bytes(range(1, 1 + PAYLOAD_LENGTHS[n % len(PAYLOAD_LENGTHS)])),
        )
        for n in range(mus_details._MIN_RECORDS * 2)
    )


def test_does_not_accept_an_others_pool(streams: Callable[..., None]) -> None:
    """The two pools differ only by header width, so this is the real risk:
    a details reader that happily walks the `others` stream would produce
    plausible-looking records with every field shifted."""
    streams(others_pool())
    with pytest.raises(CorruptScoreError, match="no recognisable details pool"):
        read_mus_details(PATH)


def test_the_others_reader_does_not_accept_a_details_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The converse of the test above, so neither reader can drift into the
    other's stream unnoticed."""
    details = pool(record(1044, 1, 1, 0, bytes(20)))
    monkeypatch.setattr(mus_others, "read_mus_streams", lambda _path: [details])
    with pytest.raises(CorruptScoreError, match="no recognisable others pool"):
        mus_others.read_mus_others(PATH)


def test_rejects_a_stream_whose_records_do_not_tile_it(
    streams: Callable[..., None],
) -> None:
    streams(pool(record(1044, 1, 1, 0, b"")) + b"\x14\x04\x01\x00\x01\x00\x00\x00\xff\x00\x00\x00")
    with pytest.raises(CorruptScoreError, match="no recognisable details pool"):
        read_mus_details(PATH)


def test_rejects_a_payload_length_over_the_cap(streams: Callable[..., None]) -> None:
    """The cap must fire on its own, not because the stream ran out, so
    deleting `_MAX_PAYLOAD` makes this record parse and the test fail."""
    oversized = mus_details._MAX_PAYLOAD + 1
    header = (
        (1044).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + oversized.to_bytes(4, "little")
    )
    streams(pool(header + bytes(oversized + 4)))
    with pytest.raises(CorruptScoreError):
        read_mus_details(PATH)


def test_rejects_more_records_than_the_cap_allows(
    streams: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mus_details, "_MAX_RECORDS", 3)
    streams(pool(*[record(1044, 1, n, 0, b"") for n in range(8)]))
    with pytest.raises(CorruptScoreError):
        read_mus_details(PATH)


def test_rejects_a_truncated_final_record(streams: Callable[..., None]) -> None:
    streams(pool(record(1044, 1, 1, 0, b"\x01\x02\x03\x04"))[:-3])
    with pytest.raises(CorruptScoreError):
        read_mus_details(PATH)


def test_rejects_a_stream_of_padding_alone(streams: Callable[..., None]) -> None:
    streams(bytes(4096))
    with pytest.raises(CorruptScoreError):
        read_mus_details(PATH)
