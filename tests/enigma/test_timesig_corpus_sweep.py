"""Check time signatures against the whole local corpus.

Skipped wherever corpus/ is absent (e.g. CI).

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.timesig import display_time_signature, time_signatures

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

SAMPLE = 40
MIN_MEASURES = 2000
EXPECTED_SIGNATURES = {"4/4", "3/4", "2/4", "2/2", "6/8", "9/8", "3/8", "1/4", "1/8"}
"""Every conventional signature the sampled corpus produces. Pinned so a change in
the beats/divbeat conversion shows up as a new or missing entry rather than as a
silently different score."""


def _archives() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*")) if p.is_file() and p.suffix.lower() == ".musx"][
        :SAMPLE
    ]


def test_every_measure_yields_a_notatable_signature() -> None:
    seen: set[str] = set()
    measures = 0
    compound = 0
    for path in _archives():
        document = parse_enigma(score_xml(path))
        for signature in time_signatures(document).values():
            measures += 1
            # Raises if the division is not a notatable note value.
            assert signature.denominator > 0
            assert signature.numerator > 0
            assert signature.total_edu == signature.beats * signature.division_edu
            seen.add(str(signature))
            compound += signature.is_compound

    assert measures >= MIN_MEASURES
    assert seen == EXPECTED_SIGNATURES, f"signature set changed: {sorted(seen)}"
    assert compound > 0, "no compound meter in the sample; the 6/8 path is untested"


def test_display_signatures_appear_only_where_flagged() -> None:
    """The flag is rare, and reading the fields without it invents signatures.

    Guards the specific bug: `dispBeats`/`dispDivbeat` exist on every measure, so
    an unguarded read would report a display signature for nearly every measure
    rather than the 76 that actually set the flag.
    """
    flagged = total = 0
    for path in _archives():
        document = parse_enigma(score_xml(path))
        for record in document.others.of_tag("measSpec"):
            if "part" in record.attrs:
                continue
            total += 1
            if display_time_signature(record) is not None:
                flagged += 1
                assert "useDisplayTimesig" in record.fields

    assert total >= MIN_MEASURES
    assert 0 < flagged < total // 10, (
        f"{flagged} of {total} measures report a display signature; "
        "the flag guard has probably been dropped"
    )
