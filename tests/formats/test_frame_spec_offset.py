"""Where a frameSpec keeps its entry pair.

The specification drew this record with `startEntry` at +6 for two releases.
The reader never read it there, and the corpus says the reader is right. This
pins the finding against both drifting back.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from finale_file_parser.enigma.mus_others import TAG_FRAME_SPEC, read_mus_others
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.formats.layouts import FRAME_SLOT, FRAME_SPEC

sys.path.insert(0, str(Path(__file__).parent.parent))

CORPUS = Path(__file__).parent.parent.parent / "corpus"


def test_the_layout_puts_the_pair_at_the_start_of_a_slot() -> None:
    """+0 and +4 of a 12-byte slot, not +6 and +10 of the payload."""
    by_name = {f.name: f for f in FRAME_SPEC.fields}
    assert by_name["startEntry"].offset == 0
    assert by_name["endEntry"].offset == 4
    assert FRAME_SPEC.stride == FRAME_SLOT == 12
    assert FRAME_SPEC.computed, "which slot holds the pair depends on the record"


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_the_paired_documents_put_the_pair_in_the_last_slot() -> None:
    """The measurement itself, run against every pair the corpus offers.

    For each `.mus` frameSpec whose paired `.musx` states a start/end pair, every
    candidate offset in the payload is tried. The last slot must match every
    time, and +6 -- what the specification used to draw -- must match never.
    """
    from corpus_files import oracle_pairs

    from finale_file_parser.enigma.document import parse_enigma
    from finale_file_parser.enigma.score import score_xml

    last_slot = 0
    at_six = 0
    compared = 0
    for mus_path, musx_path in oracle_pairs():
        try:
            others = read_mus_others(mus_path)
            document = parse_enigma(score_xml(musx_path))
        except (FinaleFileError, OSError):
            continue
        truth: dict[int, tuple[int, int]] = {}
        for record in document.others.records:
            if record.tag != "frameSpec" or "cmper" not in record.attrs:
                continue
            start, end = record.fields.get("startEntry"), record.fields.get("endEntry")
            if isinstance(start, str) and isinstance(end, str):
                truth[int(record.attrs["cmper"])] = (int(start), int(end))
        if not truth:
            continue

        for spec in others:
            if spec.tag != TAG_FRAME_SPEC or spec.cmper not in truth:
                continue
            payload = spec.payload
            incidences = len(payload) // FRAME_SLOT
            if incidences < 1:
                continue
            compared += 1

            def pair_at(offset: int, data: bytes = payload) -> tuple[int, int]:
                return (
                    int.from_bytes(data[offset : offset + 4], "little"),
                    int.from_bytes(data[offset + 4 : offset + 8], "little"),
                )

            want = truth[spec.cmper]
            if pair_at((incidences - 1) * FRAME_SLOT) == want:
                last_slot += 1
            if len(payload) >= 14 and pair_at(6) == want:
                at_six += 1

    assert compared > 10_000, f"only {compared} records compared; the sweep found too few"
    assert last_slot == compared, (
        f"the last slot held the pair in {last_slot} of {compared} records"
    )
    assert at_six == 0, f"+6 held the pair in {at_six} records; it should hold it in none"
