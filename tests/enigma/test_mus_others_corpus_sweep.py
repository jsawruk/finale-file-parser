"""Validate the `.mus` others-pool reader against paired `.musx` files.

Skipped wherever corpus/ is absent (e.g. CI). The same document exists in both
containers, so the reader's keys and payloads can be compared against ground
truth rather than merely "parsed without raising".

Pairs are matched by filename stem, which is not a guarantee of identical
content -- several stems name different arrangements in the two collections.
Those are excluded using the entry counts from the already-validated entry-pool
reader, so the exclusion never depends on the reader under test.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from corpus_files import oracle_pairs

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.mus_others import (
    TAG_FRAME_SPEC,
    TAG_MEAS_SPEC,
    MusOther,
    read_mus_others,
)
from finale_file_parser.enigma.score import score_xml

Sweep = tuple[
    list[tuple[MusOther, ...]],
    list[tuple[tuple[MusOther, ...], EnigmaDocument]],
]
"""Every readable pool, and those whose paired `.musx` holds the same music."""

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

PAIRS = 95
"""Filename stems present as both a `.mus` and a `.musx`."""

READABLE = 95
"""Every pair's `.mus` others pool tiles its stream exactly.

It was 84 until two things were fixed: `0xFFFF` recognised as filler, and the
payload cap raised. The cap was the larger cause and was measured circularly --
see `_MAX_PAYLOAD` in `mus_others.py`.
"""

SAME_CONTENT = 95
"""Readable pairs whose two containers hold the same music."""

FRAME_SPEC_KEY_EXCEPTIONS = 5
"""Documents whose `.musx` carries part-override frameSpec records its `.mus`
does not. Every `.mus` key is present in the `.musx`; the `.musx` simply has
more. Pinned rather than explained away.

Was 2 until pairing stopped guessing which `.musx` a stem meant. The three added
are the same shape as the original two -- more documents in the sweep, not a new
kind of difference."""

FRAME_SPEC_PAYLOAD_MISSES = 15
"""Three `startEntry`/`endEntry` pairs differ, out of 7,922."""

MEAS_SPEC_WIDTH_MISSES = 59
"""Measure widths that differ, all of them in a single document.

`width` is layout, not music: a score re-spaced between the two saves changes
every width while leaving `beats`/`divbeat` -- which match everywhere -- alone.
"""


def pairs() -> list[tuple[Path, Path]]:
    return oracle_pairs()


def keyed(records: tuple[MusOther, ...], tag: int) -> dict[tuple[int, int], bytes]:
    return {(r.cmper, r.part): r.payload for r in records if r.tag == tag}


def musx_keys(document: EnigmaDocument, tag_name: str) -> list[tuple[int, int]]:
    """`.musx` records keyed the way `.mus` keys them: (cmper, part index)."""
    records = document.others.of_tag(tag_name)
    order = sorted({r.attrs.get("part", "0") for r in records})
    return [(int(r.attrs["cmper"]), order.index(r.attrs.get("part", "0"))) for r in records]


@pytest.fixture(scope="module")
def sweep() -> Sweep:
    """Read every pair once; the whole module reports on the same walk."""
    readable: list[tuple[MusOther, ...]] = []
    same_content: list[tuple[tuple[MusOther, ...], EnigmaDocument]] = []
    for mus_path, musx_path in pairs():
        try:
            records = read_mus_others(mus_path)
        except CorruptScoreError:
            continue
        readable.append(records)
        document = parse_enigma(score_xml(musx_path))
        try:
            entries = len(read_mus_entries(mus_path))
        except CorruptScoreError:
            continue
        if entries == len(document.entries.records):
            same_content.append((records, document))
    return readable, same_content


def test_every_pair_is_still_present() -> None:
    assert len(pairs()) == PAIRS


def test_the_pool_tiles_its_stream_exactly(sweep: Sweep) -> None:
    readable, _ = sweep
    assert len(readable) == READABLE


def test_no_document_yields_an_empty_pool(sweep: Sweep) -> None:
    readable, _ = sweep
    assert all(records for records in readable)


def test_frame_spec_keys_match_the_paired_musx(sweep: Sweep) -> None:
    """The finding under test: each record carries its own key.

    A mismatch here means the walk lost alignment or the key is not where the
    header says it is.
    """
    _, same_content = sweep
    assert len(same_content) == SAME_CONTENT
    misses = sum(
        1
        for records, document in same_content
        if [(r.cmper, r.part) for r in records if r.tag == TAG_FRAME_SPEC]
        != musx_keys(document, "frameSpec")
    )
    assert misses == FRAME_SPEC_KEY_EXCEPTIONS


def test_frame_spec_payloads_match_the_paired_musx(sweep: Sweep) -> None:
    _, same_content = sweep
    compared = misses = 0
    for records, document in same_content:
        payloads = keyed(records, TAG_FRAME_SPEC)
        for key, record in zip(
            musx_keys(document, "frameSpec"),
            document.others.of_tag("frameSpec"),
            strict=True,
        ):
            payload = payloads.get(key)
            start, end = record.fields.get("startEntry"), record.fields.get("endEntry")
            if payload is None or len(payload) < 8:
                continue
            if not isinstance(start, str) or not isinstance(end, str):
                continue
            compared += 1
            if struct.unpack_from("<II", payload, 0) != (int(start), int(end)):
                misses += 1
    assert compared > 8_000
    assert misses == FRAME_SPEC_PAYLOAD_MISSES


def test_meas_spec_payloads_match_the_paired_musx(sweep: Sweep) -> None:
    """`measSpec`'s payload is `width, key, beats, divbeat` from offset zero.

    This is the independent confirmation that tag 176 really is `measSpec`:
    the key sequence could coincide, four field values across thousands of
    records could not.
    """
    _, same_content = sweep
    compared = width_misses = timing_misses = 0
    for records, document in same_content:
        payloads = keyed(records, TAG_MEAS_SPEC)
        for key, record in zip(
            musx_keys(document, "measSpec"),
            document.others.of_tag("measSpec"),
            strict=True,
        ):
            payload = payloads.get(key)
            if payload is None or len(payload) < 8:
                continue
            width, _key, beats, divbeat = struct.unpack_from("<4H", payload, 0)
            compared += 1
            for name, got in (("width", width), ("beats", beats), ("divbeat", divbeat)):
                expected = record.fields.get(name)
                if not isinstance(expected, str) or int(expected) == got:
                    continue
                if name == "width":
                    width_misses += 1
                else:
                    timing_misses += 1
    assert compared > 5_000
    assert timing_misses == 0
    assert width_misses == MEAS_SPEC_WIDTH_MISSES
