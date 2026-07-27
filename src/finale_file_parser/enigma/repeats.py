"""Resolve a document's repeat structure: forward and backward repeats, and endings.

Repeats live in two places at once, and both are needed.

The **barlines** are flags on `measSpec`: `forRepBar` means a forward repeat at
this measure's left barline, `bacRepBar` a backward repeat at its right. Nothing
else is stored about them there -- a forward repeat is only ever a barline.

The **endings** need three records to reconstruct one bracket:

    repeatEndingStart(measure)  -- the bracket opens here
    repeatPassList(measure)     -- which passes it is taken on ("1.", "1., 2.")
    measSpec.barEnding          -- flagged on the bracket's first and last measure

That last one is the part worth stating plainly, because the obvious reading of
it is wrong. `barEnding` is **not** set on every measure a bracket covers: in a
four-measure first ending the corpus flags the first measure and the fourth, and
leaves the two in between clear. So a bracket's extent is *the last flagged
measure at or after its start, and before the next bracket starts* -- not a run
of consecutive flags. Reading it as a run stretches a bracket over the ending
that follows it.

That rule was checked against the two independent things that ought to agree
with it: the measure carrying the backward repeat (71 brackets, no
disagreement), and `nextEnd` where a `repeatEndingStart` supplies one. The
remaining 67 brackets are single measures with no backward repeat -- a final
"2." ending, which closes with no hook.

Not read, and deliberately: `repeatBack.target`, `trigger`, `action`, and the
`textRepeatAssign` family (D.C., D.S., Fine, To Coda). Those describe *jumps*
rather than repeat barlines, and MusicXML expresses them differently; they are
the next slice, not this one. See `docs/ARCHITECTURE.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.ir import Ending

__all__ = ["MeasureRepeats", "Repeats", "repeats_for"]

_ENDING_START = "repeatEndingStart"
_PASS_LIST = "repeatPassList"
_BACK = "repeatBack"
_MEASURE = "measSpec"

DEFAULT_PASSES = 2
"""How many times a repeated section is played when `actuate` says nothing.

Finale calls it "Total Passes" and writes nothing for the default, which is also
MusicXML's default for a backward repeat -- so a `times` attribute is emitted
only where the document disagrees with it.
"""


@dataclass(frozen=True)
class MeasureRepeats:
    """Everything attached to one measure's barlines."""

    forward: bool = False
    """A forward repeat at the left barline."""

    backward: bool = False
    """A backward repeat at the right barline."""

    passes: int = DEFAULT_PASSES
    """Total times the repeated section is played. Only meaningful with
    `backward`."""

    endings: tuple[Ending, ...] = ()
    """Ending brackets opening or closing here. A single-measure ending both
    opens and closes on its own measure, so this can hold two."""


@dataclass(frozen=True)
class Repeats:
    """A document's repeat structure, by measure number."""

    by_measure: dict[int, MeasureRepeats]

    def get(self, measure: int) -> MeasureRepeats:
        return self.by_measure.get(measure, _NOTHING)


_NOTHING = MeasureRepeats()


def repeats_for(document: EnigmaDocument) -> Repeats:
    """Resolve every repeat barline and ending bracket in `document`."""
    flags = _measure_flags(document)
    passes = _backward_passes(document)
    out: dict[int, list[Ending]] = {}
    for start, stop, numbers in _endings(document, flags):
        out.setdefault(start, []).append(Ending(numbers=numbers, type="start"))
        # A bracket closes with a downward hook only where the music actually
        # repeats there; the last ending of a set just stops being drawn, which
        # MusicXML spells "discontinue".
        closing = "stop" if flags.get(stop, _NO_FLAGS).backward else "discontinue"
        out.setdefault(stop, []).append(Ending(numbers=numbers, type=closing))

    measures = set(out) | {m for m, f in flags.items() if f.forward or f.backward}
    return Repeats(
        by_measure={
            measure: MeasureRepeats(
                forward=flags.get(measure, _NO_FLAGS).forward,
                backward=flags.get(measure, _NO_FLAGS).backward,
                passes=passes.get(measure, DEFAULT_PASSES),
                endings=tuple(out.get(measure, ())),
            )
            for measure in sorted(measures)
        }
    )


@dataclass(frozen=True)
class _Flags:
    forward: bool = False
    backward: bool = False
    ending: bool = False


_NO_FLAGS = _Flags()


def _measure_flags(document: EnigmaDocument) -> dict[int, _Flags]:
    """The three `measSpec` barline flags, per measure.

    Score records only. A part can override a barline, and honouring that here
    would give the score a repeat it does not have.
    """
    out: dict[int, _Flags] = {}
    for record in document.others.of_tag(_MEASURE):
        if "part" in record.attrs:
            continue
        measure = _int(record.attrs.get("cmper"))
        if measure is None:
            continue
        out[measure] = _Flags(
            forward="forRepBar" in record.fields,
            backward="bacRepBar" in record.fields,
            ending="barEnding" in record.fields,
        )
    return out


def _backward_passes(document: EnigmaDocument) -> dict[int, int]:
    """`repeatBack.actuate` -- how many times through -- by measure."""
    out: dict[int, int] = {}
    for record in document.others.of_tag(_BACK):
        if "part" in record.attrs:
            continue
        measure = _int(record.attrs.get("cmper"))
        actuate = _int(record.fields.get("actuate"))
        if measure is None:
            continue
        out[measure] = actuate if actuate and actuate > 0 else DEFAULT_PASSES
    return out


def _endings(
    document: EnigmaDocument, flags: dict[int, _Flags]
) -> list[tuple[int, int, tuple[int, ...]]]:
    """(first measure, last measure, pass numbers) for each ending bracket."""
    starts = sorted(_ending_starts(document))
    passes = _pass_lists(document)
    flagged = sorted(m for m, f in flags.items() if f.ending)
    last = max(flags, default=0)

    out: list[tuple[int, int, tuple[int, ...]]] = []
    for index, start in enumerate(starts):
        limit = starts[index + 1] - 1 if index + 1 < len(starts) else last
        stop = max((m for m in flagged if start <= m <= limit), default=start)
        out.append((start, stop, passes.get(start, ())))
    return out


def _ending_starts(document: EnigmaDocument) -> set[int]:
    return {
        measure
        for record in document.others.of_tag(_ENDING_START)
        if "part" not in record.attrs and (measure := _int(record.attrs.get("cmper"))) is not None
    }


def _pass_lists(document: EnigmaDocument) -> dict[int, tuple[int, ...]]:
    """Which passes each bracket is taken on: `1.` is (1,), `1., 2.` is (1, 2)."""
    out: dict[int, tuple[int, ...]] = {}
    for record in document.others.of_tag(_PASS_LIST):
        if "part" in record.attrs:
            continue
        measure = _int(record.attrs.get("cmper"))
        if measure is None:
            continue
        numbers = tuple(
            number for raw in _acts(record) if (number := _int(raw)) is not None and number > 0
        )
        if numbers:
            out[measure] = numbers
    return out


def _acts(record: Record) -> tuple[str, ...]:
    """`act` repeats within one `repeatPassList` -- an ending taken on both the
    first and second pass writes it twice -- so the field can be a tuple."""
    value = record.fields.get("act")
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    return () if value is None else (str(value),)


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
