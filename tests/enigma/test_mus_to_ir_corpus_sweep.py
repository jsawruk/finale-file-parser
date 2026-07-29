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
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Event, Score

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

COMPARED = 81
"""Same-content pairs whose `.mus` builds a Score.

Was 73, then 76, now 81, as the two pool-walk fixes landed. The five added by
the payload-cap fix contribute **no differences of any kind** -- more coverage at
the same fidelity.
"""

UNBUILDABLE = 2
"""Documents whose `.mus` frame chain references an entry the pool does not hold.

Both fail the same way (`frameSpec N chain references missing entry M`). One is
newly readable, so this is a second instance of a known class rather than a new
failure mode.
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

OCTAVE_ONLY_PITCHES = 1
"""Pitches whose letter and accidental are right and only the octave is wrong.

Down from 4,140 total differences once the transposition's key alteration was
recovered, from 2,491 once the written octave stopped ignoring the octaves
Finale folds into `harm_lev`, and from 845 once that correction stopped
exempting whole-octave transpositions.

**The one that remains is not a transposition fault.** It sits on a concert
staff, where the two files disagree about the music: the `.mus` holds a chord
(`harm_lev` 7 and 9) where the `.musx` holds a single note (9), with a different
pitch on a neighbouring entry. It lands in this bucket by coincidence, the
comparison lining a D4 up against a D5, and is one of the `.mus`/`.musx`
revision differences the entry-pool sweep already pins.

So a `.mus` gives the same written pitch as its `.musx` on every transposing
staff in the corpus. The octave was never missing from it.
"""

OTHER_PITCHES = 3
"""Differences that are not a clean octave: two notes spelled enharmontically
(F-flat against E, C-flat against B) and one entry storing a different number of
notes in the two containers. All three are `.mus`/`.musx` content differences
already pinned by the entry-pool sweep, not decode errors."""

CLEF_MEASURES = 10
"""Measures whose clef differs, down from 327 before the clef table was decoded
and from 22 before clefs were carried across a silence.

Carrying them forward cut it by 12 without touching the clef reading itself.
`gfhold` is where a clef lives and a measure a staff rests through has none, so
half of those 22 were one container having a `gfhold` where the other did not,
rather than the two disagreeing about a clef.

What is left is the original case: the `gfhold` stores `clefID` 0, meaning "use
the staff's `defaultClef`", and the `.mus` `staffSpec` stores 0 there as well
while the `.musx` materialises clef 3. The value lives with the instrument, not
in the file -- the same root cause as the transposition gap. So this is a floor,
not a decode error, until an instrument table is found.
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
    octave_only_pitches: int = 0
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


def compare(mine: Score, theirs: Score, tally: Tally) -> None:
    # Compare the part *sequences*, not just their lengths: parts now follow the
    # document's staff layout rather than staff number, so a positional zip
    # could quietly line up two different staves and report them as matching.
    if [part.id for part in mine.parts] != [part.id for part in theirs.parts]:
        tally.structure += 1
        return
    for part, other in zip(mine.parts, theirs.parts, strict=True):
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
                if event.pitches == want.pitches:
                    continue
                same_letters = len(event.pitches) == len(want.pitches) and all(
                    a.step == b.step and a.alteration == b.alteration
                    for a, b in zip(event.pitches, want.pitches, strict=True)
                )
                if same_letters:
                    tally.octave_only_pitches += 1
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
        compare(mine, theirs, out)
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


def test_every_pitch_letter_is_right_and_only_octaves_remain(tally: Tally) -> None:
    """`other_pitches` is the meaningful number: it counts differences the
    missing transposition interval does *not* explain, and all three of them are
    content differences already pinned by the entry-pool sweep."""
    assert tally.octave_only_pitches == OCTAVE_ONLY_PITCHES
    assert tally.other_pitches == OTHER_PITCHES


def test_clefs_match_except_where_the_clef_is_instrument_derived(tally: Tally) -> None:
    assert tally.clef_measures == CLEF_MEASURES
