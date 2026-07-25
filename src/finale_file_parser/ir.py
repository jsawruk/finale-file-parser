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
    "Event",
    "Measure",
    "Part",
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


@dataclass(frozen=True)
class Part:
    """One instrumental part."""

    id: str
    name: str
    measures: tuple[Measure, ...] = ()


@dataclass(frozen=True)
class Score:
    """A whole score."""

    parts: tuple[Part, ...] = ()
    title: str = ""
    composer: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    """Anything a reader recovered that the IR does not model yet. Kept so
    information is not silently discarded on the way in -- the decision above
    puts the loss at the exporter, not the reader."""
