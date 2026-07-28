"""The format-neutral intermediate representation.

Every input converges here before any exporter sees it (`docs/DECISIONS.md`,
2026-07-20). This module therefore imports **nothing** from `enigma` or
`container`: readers build an IR, exporters consume one, and neither knows about
the other. A `.mus` reader added later produces the same types and every exporter
works unchanged.

Consequence recorded in that decision, and worth restating because it shapes the
types: **MusicXML's limits must not constrain the IR.** Where Finale represents
something MusicXML cannot, the IR keeps it and the exporter drops it at the edge.
So durations here are exact `Fraction`s of a whole note rather than MusicXML
integer divisions, and a `Voice` carries its source layer number rather than a
MusicXML voice index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

__all__ = [
    "Beam",
    "Ending",
    "Event",
    "Lyric",
    "Measure",
    "Part",
    "PartGroup",
    "Pitch",
    "Score",
    "TimeSignature",
    "Voice",
]


@dataclass(frozen=True)
class Pitch:
    """A spelled pitch: letter, chromatic alteration, and octave."""

    step: str
    """Letter name, ``A``-``G``."""

    octave: int
    """Scientific pitch notation: middle C is octave 4."""

    alteration: int
    """Semitones from the natural: -1 flat, 0 natural, +1 sharp."""


@dataclass(frozen=True)
class TimeSignature:
    """A conventional time signature."""

    beats: int
    beat_type: int


@dataclass(frozen=True)
class Beam:
    """One beam level on one note, and what it does there."""

    number: int
    """1 is the primary beam, 2 the sixteenth's second, and so on."""

    type: str
    """MusicXML's vocabulary: begin, continue, end, forward hook, backward hook."""


@dataclass(frozen=True)
class Lyric:
    """One syllable sung by one event, in one verse.

    `syllabic` says where the syllable sits in its word -- "single", "begin",
    "middle" or "end". Enigma stores only the hyphens, so this is derived; see
    `enigma.lyrics`.
    """

    number: int
    """Verse number. Several lyrics on one event are several verses."""

    text: str
    syllabic: str = "single"
    extend: bool = False
    """A word extension: the line drawn under a syllable held across notes."""


@dataclass(frozen=True)
class Event:
    """One note, chord, or rest.

    A chord is one event with several pitches; a rest is one with none. Keeping
    them a single type means duration handling is written once, and a chord
    cannot accidentally be emitted as separate notes with separate durations.
    """

    duration: Fraction
    """Sounded length as a fraction of a whole note, tuplet scaling already
    applied. Exact rather than rounded: a triplet eighth is 1/12, which no
    integer division count represents without a common denominator chosen later
    by the exporter."""

    written_duration: Fraction
    """Length as written, before tuplet scaling -- what determines the notehead.
    A triplet eighth is written 1/8 but sounds 1/12."""

    pitches: tuple[Pitch, ...] = ()
    """Empty for a rest."""

    dots: int = 0
    tie_start: bool = False
    tie_end: bool = False
    is_grace: bool = False
    """A grace note: it is written and played, but occupies no metric time.

    Kept as a flag rather than as a zero duration because the two are not the
    same thing -- a grace note still has a notehead and a written value, and
    MusicXML represents it by omitting duration entirely rather than by writing
    zero, which its schema rejects.
    """
    tuplet_ratio: Fraction | None = None
    """Sounded over written, when this event is inside a tuplet. 2/3 for a
    triplet. None outside one."""

    lyrics: tuple[Lyric, ...] = ()
    """Syllables sung on this event, one per verse, in verse order."""

    beams: tuple[Beam, ...] = ()
    """One entry per beam level: 1 is the primary beam. Empty on a note that
    carries a flag rather than a beam."""

    is_measure_rest: bool = False
    """A rest filling the whole measure, however long the measure is.

    Distinct from a rest that happens to last a whole note: it is written as one
    symbol centred in the bar, and its length follows the time signature rather
    than any note value -- so a 3/4 measure rest is 3/4 long and has no note
    value at all.
    """

    articulations: tuple[str, ...] = ()
    """MusicXML articulation names -- "staccato", "accent", "tenuto",
    "strong-accent", "breath-mark" -- in document order."""

    @property
    def is_rest(self) -> bool:
        return not self.pitches

    @property
    def is_chord(self) -> bool:
        return len(self.pitches) > 1


@dataclass(frozen=True)
class Voice:
    """A single line of music within a measure."""

    number: int
    """The source layer, 1-based. Preserved rather than renumbered so a reader's
    layout stays inspectable; an exporter maps it to its own voice numbering."""

    events: tuple[Event, ...] = ()


@dataclass(frozen=True)
class Ending:
    """One end of an ending bracket -- a "first time" / "second time" volta."""

    numbers: tuple[int, ...]
    """The passes this bracket is taken on. `1.` is (1,), `1., 2.` is (1, 2)."""

    type: str
    """`start` where the bracket opens; at its close, `stop` if it ends in a
    downward hook and `discontinue` if it just stops being drawn."""


@dataclass(frozen=True)
class Measure:
    """One measure of one part."""

    number: int
    voices: tuple[Voice, ...] = ()

    key_fifths: int | None = None
    """Position on the circle of fifths, negative for flats. Set only where it
    changes, so an exporter emits an attribute only when it must."""

    is_minor: bool = False
    time: TimeSignature | None = None
    clef_sign: str | None = None
    """``G``, ``F``, ``C``, or ``percussion``."""

    clef_line: int | None = None

    repeat_forward: bool = False
    """A forward repeat barline on the left of this measure."""

    repeat_backward: bool = False
    """A backward repeat barline on the right of this measure."""

    repeat_passes: int = 2
    """How many times the repeated section is played. Only meaningful with
    `repeat_backward`; 2 is the ordinary "play it twice"."""

    endings: tuple[Ending, ...] = ()
    """Ending brackets opening or closing at this measure. A single-measure
    ending does both, so this can hold two."""


@dataclass(frozen=True)
class Part:
    """One instrumental part."""

    id: str
    name: str
    measures: tuple[Measure, ...] = ()


@dataclass(frozen=True)
class PartGroup:
    """A brace or bracket joining a run of consecutive parts."""

    part_ids: tuple[str, ...]
    """The parts it joins, in score order. Always contiguous in `Score.parts`."""

    symbol: str | None = None
    """MusicXML `<group-symbol>` -- "brace", "bracket", "line", "square" -- or
    None where the source names a shape this project cannot identify."""

    barline: bool = False
    """Barlines run through the group rather than stopping at each staff."""

    name: str = ""
    abbreviation: str = ""


@dataclass(frozen=True)
class Score:
    """A whole score."""

    parts: tuple[Part, ...] = ()
    groups: tuple[PartGroup, ...] = ()
    """Braces and brackets down the left edge, outermost first."""

    title: str = ""
    composer: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    """Anything a reader recovered that the IR does not model yet. Kept so
    information is not silently discarded on the way in -- the decision above
    puts the loss at the exporter, not the reader."""
