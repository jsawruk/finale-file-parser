"""Validate the `.mus` details-pool reader against paired `.musx` files.

Skipped wherever corpus/ is absent (e.g. CI). Pairs that name different
arrangements in the two collections are excluded using the entry counts from
the already-validated entry-pool reader, so the exclusion never depends on the
reader under test.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_details import TAG_GFHOLD, MusDetailRecord, read_mus_details
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.score import score_xml

Sweep = list[tuple[tuple[MusDetailRecord, ...], EnigmaDocument]]
"""Every readable details pool whose paired `.musx` holds the same music."""

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

READABLE = 91
"""Every pair's `.mus` details pool tiles its stream exactly.

It was 84 until `0xFFFF` was recognised as filler alongside `0x0000`. The seven
that failed hit a run of `0xFFFF` words, which parse as records of declared
length 0 and leave the walk four bytes short each time. The `others` pool still
refuses those seven for an unrelated reason -- a `tupletDef`-sized record under
tag 158 whose length field is not understood.
"""

SAME_CONTENT = 83
"""Readable pairs holding the same music and carrying `gfhold` records.

Was 80 until `0xFFFF` was recognised as filler; the three added are documents
whose details pool the walk could not previously finish.
"""

CLEF_ID = 8356
CLEF_ID_DEFAULTED = 272
"""`clefID` matches outright in 8,356 records. The other 272 are `.mus` storing
0 where the `.musx` materialises that staff's `defaultClef` -- so every record
is accounted for, and a regression would show up as an *unexplained* miss."""


def pairs() -> list[tuple[Path, Path]]:
    mus = {p.stem: p for p in CORPUS.rglob("*.mus")}
    musx = {p.stem: p for p in CORPUS.rglob("*.musx")}
    return [(mus[s], musx[s]) for s in sorted(set(mus) & set(musx))]


def gfhold_payloads(records: tuple[MusDetailRecord, ...]) -> dict[tuple[int, int], bytes]:
    return {(r.cmper1, r.cmper2): r.payload for r in records if r.tag == TAG_GFHOLD}


def musx_gfhold_keys(document: EnigmaDocument) -> list[tuple[int, int]]:
    return [
        (int(r.attrs["cmper1"]), int(r.attrs["cmper2"])) for r in document.details.of_tag("gfhold")
    ]


def default_clefs(document: EnigmaDocument) -> dict[int, int]:
    out = {}
    for spec in document.others.of_tag("staffSpec"):
        clef = spec.fields.get("defaultClef")
        out[int(spec.attrs["cmper"])] = int(clef) if isinstance(clef, str) else 0
    return out


@pytest.fixture(scope="module")
def readable() -> int:
    count = 0
    for mus_path, _musx_path in pairs():
        try:
            read_mus_details(mus_path)
        except CorruptScoreError:
            continue
        count += 1
    return count


@pytest.fixture(scope="module")
def sweep() -> Sweep:
    out: Sweep = []
    for mus_path, musx_path in pairs():
        try:
            records = read_mus_details(mus_path)
            document = parse_enigma(score_xml(musx_path))
            entries = len(read_mus_entries(mus_path))
        except CorruptScoreError:
            continue
        if entries == len(document.entries.records) and document.details.of_tag("gfhold"):
            out.append((records, document))
    return out


def test_the_pool_tiles_its_stream_exactly(readable: int) -> None:
    assert readable == READABLE


def test_gfhold_keys_are_the_musx_sequence_restricted_to_them(sweep: Sweep) -> None:
    """The finding under test: `.mus` details records carry their own key pair.

    Equality with the full `.musx` sequence is the wrong assertion -- a `.musx`
    sometimes carries a `gfhold` the `.mus` does not. What must hold is that
    every `.mus` key is a `.musx` key and the order is preserved; a walk that
    lost alignment would fail that immediately.
    """
    assert len(sweep) == SAME_CONTENT
    for records, document in sweep:
        mine = [(r.cmper1, r.cmper2) for r in records if r.tag == TAG_GFHOLD]
        theirs = musx_gfhold_keys(document)
        assert [key for key in theirs if key in set(mine)] == mine


def test_gfhold_payload_matches_the_paired_musx(sweep: Sweep) -> None:
    """`clefPercent` at +4 and `frame1` at +6, exactly, on every record."""
    percent_seen = percent_ok = frame_seen = frame_ok = 0
    for records, document in sweep:
        payloads = gfhold_payloads(records)
        for record in document.details.of_tag("gfhold"):
            key = (int(record.attrs["cmper1"]), int(record.attrs["cmper2"]))
            payload = payloads.get(key)
            if payload is None or len(payload) < 20:
                continue
            fields = struct.unpack_from("<10H", payload, 0)
            percent, frame = record.fields.get("clefPercent"), record.fields.get("frame1")
            if isinstance(percent, str):
                percent_seen += 1
                percent_ok += fields[2] == int(percent)
            if isinstance(frame, str):
                frame_seen += 1
                frame_ok += fields[3] == int(frame)
    assert percent_seen > 8_000
    assert frame_seen > 8_000
    assert (percent_ok, frame_ok) == (percent_seen, frame_seen)


def test_every_gfhold_clef_is_accounted_for(sweep: Sweep) -> None:
    """`clefID` at +0, with `.mus` writing 0 for "use the staff default".

    The point of the test is the third bucket: it must stay empty. A record
    where `.mus` and `.musx` disagree *and* the `.musx` value is not the staff
    default would mean the offset or the rule is wrong.
    """
    exact = defaulted = unexplained = 0
    for records, document in sweep:
        payloads = gfhold_payloads(records)
        defaults = default_clefs(document)
        for record in document.details.of_tag("gfhold"):
            key = (int(record.attrs["cmper1"]), int(record.attrs["cmper2"]))
            payload = payloads.get(key)
            clef = record.fields.get("clefID")
            if payload is None or len(payload) < 20 or not isinstance(clef, str):
                continue
            stored = struct.unpack_from("<H", payload, 0)[0]
            if stored == int(clef):
                exact += 1
            elif stored == 0 and int(clef) == defaults.get(key[0]):
                defaulted += 1
            else:
                unexplained += 1
    assert unexplained == 0
    assert (exact, defaulted) == (CLEF_ID, CLEF_ID_DEFAULTED)
