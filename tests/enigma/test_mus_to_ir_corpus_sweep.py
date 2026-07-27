"""Compare the IR built from a `.mus` against the IR built from its `.musx`.

Skipped wherever corpus/ is absent (e.g. CI). This is the strongest oracle the
project has: the same music exists in both containers, so the two `Score`
objects can be compared field by field rather than merely "built without
raising". Every gap the adapter documents in `UNTRANSLATED` shows up here as a
number, and closing one is a number moving.

Pairs naming different arrangements are excluded using the entry counts from the
already-validated entry-pool reader, so the exclusion never depends on the code
under test.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.pitch import read_transposition
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Event, Score

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

COMPARED = 73
"""Same-content pairs whose `.mus` builds a Score."""

UNBUILDABLE = 1
"""One document's `.mus` frame chain references an entry the pool does not hold.

The same document is the one whose `.musx` carries three frameSpec records its
`.mus` does not (see the others-pool sweep), so the two containers disagree
about its frames rather than the adapter mis-reading them. Pinned, not excused.
"""

TUPLET_EVENTS = 0
"""Events whose sounded duration differs. Zero since `tupletDef` was decoded.

It was 1,092 -- every corpus tuplet -- while tuplets read as their written
durations. This is the assertion that pins the `tupletDef` field offsets: every
corpus tuplet is 3:2 over a 512-EDU reference, so no offset sweep can tell
`symbolicNum`/`symbolicDur` from `refNum`/`refDur`, and swapping the two pairs
would invert every ratio. Sounded durations agreeing end to end is what rules
that out.
"""

TRANSPOSED_PITCHES = 4138
"""Pitches differing on a transposing staff, from `staffSpec` being untranslated.

Both causes are the missing transposition: it selects the written key, so
letters shift as well as octaves, and it feeds `harm_lev_octave_shift`.
"""

OTHER_PITCHES = 2
"""The two pitch differences not on a transposing staff.

Both are known `.mus`/`.musx` content revisions already pinned by the entry-pool
sweep -- one entry storing two notes against one, and one note an octave apart.
"""

CLEF_MEASURES = 22
"""Measures whose clef differs, down from 327 before the clef table was decoded.

Every one is the same case: the `gfhold` stores `clefID` 0, meaning "use the
staff's `defaultClef`", and the `.mus` `staffSpec` stores 0 there as well while
the `.musx` materialises clef 3. The value lives with the instrument, not in the
file -- the same root cause as the transposition gap. So this is a floor, not a
decode error, until an instrument table is found.
"""


@dataclass
class Tally:
    compared: int = 0
    unbuildable: int = 0
    structure: int = 0
    attributes: int = 0
    events: int = 0
    tuplet_events: int = 0
    tuplet_ratios: int = 0
    transposed_pitches: int = 0
    other_pitches: int = 0
    clef_measures: int = 0


def pairs() -> list[tuple[Path, Path]]:
    mus = {p.stem: p for p in CORPUS.rglob("*.mus")}
    musx = {p.stem: p for p in CORPUS.rglob("*.musx")}
    return [(mus[s], musx[s]) for s in sorted(set(mus) & set(musx))]


def rhythm(event: Event) -> tuple[object, ...]:
    """Everything about an event except its pitches and sounded duration."""
    return (
        event.written_duration,
        event.dots,
        event.tie_start,
        event.tie_end,
        event.is_grace,
    )


def transposing_staves(document: object) -> set[int]:
    out = set()
    for record in document.others.of_tag("staffSpec"):  # type: ignore[attr-defined]
        if "part" in record.attrs:
            continue
        transposition = read_transposition(record)
        if transposition is not None and transposition.interval:
            out.add(int(record.attrs["cmper"]))
    return out


def compare(mine: Score, theirs: Score, transposed: set[int], tally: Tally) -> None:
    if len(mine.parts) != len(theirs.parts):
        tally.structure += 1
        return
    for index, (part, other) in enumerate(zip(mine.parts, theirs.parts, strict=True), start=1):
        if len(part.measures) != len(other.measures):
            tally.structure += 1
            continue
        for measure, expected in zip(part.measures, other.measures, strict=True):
            if (measure.key_fifths, measure.is_minor, measure.time) != (
                expected.key_fifths,
                expected.is_minor,
                expected.time,
            ):
                tally.attributes += 1
            if measure.clef_sign != expected.clef_sign:
                tally.clef_measures += 1
            events = [e for v in measure.voices for e in v.events]
            others = [e for v in expected.voices for e in v.events]
            if len(events) != len(others):
                tally.structure += 1
                continue
            for event, want in zip(events, others, strict=True):
                if rhythm(event) != rhythm(want):
                    tally.events += 1
                elif event.duration != want.duration:
                    tally.tuplet_events += 1
                if event.tuplet_ratio != want.tuplet_ratio:
                    tally.tuplet_ratios += 1
                if event.pitches != want.pitches:
                    if index in transposed:
                        tally.transposed_pitches += 1
                    else:
                        tally.other_pitches += 1


@pytest.fixture(scope="module")
def tally() -> Tally:
    out = Tally()
    for mus_path, musx_path in pairs():
        try:
            document = parse_enigma(score_xml(musx_path))
            if len(read_mus_entries(mus_path)) != len(document.entries.records):
                continue
            theirs = build_score(document)
            mine = build_score(read_mus_document(mus_path))
        except CorruptScoreError:
            continue
        except Exception:  # noqa: BLE001 - the point is to count, not to diagnose
            out.unbuildable += 1
            continue
        out.compared += 1
        compare(mine, theirs, transposing_staves(document), out)
    return out


def test_a_mus_file_builds_the_same_score_shape(tally: Tally) -> None:
    """Parts, measures and events, one for one, with no exceptions.

    This is the load-bearing assertion. Everything below is a known gap with a
    pinned size; this one has to be exactly zero, because a structural
    difference means entries are being placed in the wrong measure -- the kind
    of error that produces plausible output nobody notices.
    """
    assert tally.compared == COMPARED
    assert tally.unbuildable == UNBUILDABLE
    assert tally.structure == 0


def test_keys_and_time_signatures_match_exactly(tally: Tally) -> None:
    assert tally.attributes == 0


def test_written_rhythm_matches_exactly(tally: Tally) -> None:
    """Written duration, dots, ties and grace notes, on every event."""
    assert tally.events == 0


def test_sounded_durations_and_tuplet_ratios_match_exactly(tally: Tally) -> None:
    """The ratio is the stronger of the two: it is what a swapped
    `symbolicNum`/`refNum` pair would invert."""
    assert tally.tuplet_events == TUPLET_EVENTS
    assert tally.tuplet_ratios == 0


def test_pitch_differences_are_confined_to_transposing_staves(tally: Tally) -> None:
    """The gap this measures is `staffSpec`, and nothing else.

    `other_pitches` is the meaningful number: it counts pitch differences that
    the missing transposition does *not* explain, and both of its two are
    content revisions already pinned by the entry-pool sweep.
    """
    assert tally.transposed_pitches == TRANSPOSED_PITCHES
    assert tally.other_pitches == OTHER_PITCHES


def test_clefs_match_except_where_the_clef_is_instrument_derived(tally: Tally) -> None:
    assert tally.clef_measures == CLEF_MEASURES
