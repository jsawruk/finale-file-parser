"""Work out where beams begin and end.

Enigma does not store beams. It stores one bit per entry -- `BEATBIT` in
`eeppd.txt`, surfaced by EnigmaXML as a `beam` field -- meaning **this entry
starts a beam group**. Everything else follows from the durations: consecutive
beamable entries belong to the group opened by the last entry carrying the bit.

Confirmed against the corpus: a measure of eight eighth notes carries the bit on
the first and the fifth, which is exactly two groups of four.

MusicXML asks for more than the grouping. Each note carries one `<beam>` per
beam level -- an eighth has one, a sixteenth two, a thirty-second three -- and
each says whether that level begins, continues or ends there. Where a level
covers a single note the beam becomes a **hook**, the short stub seen on the
sixteenth of a dotted-eighth pair. 93% of corpus groups are one duration
throughout and need no hooks; the remaining 6.6% are why they exist.

This module is otherwise pure: durations and bits in, beams out. It produces the
IR's `Beam` directly rather than an Enigma-flavoured twin, since the two would
be the same three fields and `ir.py` is the layer both containers already share.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from finale_file_parser.ir import Beam

__all__ = ["BeamedNote", "beams_for"]

_EIGHTH = Fraction(1, 8)


@dataclass(frozen=True)
class BeamedNote:
    """What this module needs to know about one event, in playing order."""

    written_duration: Fraction
    """Including dots -- a dotted eighth is 3/16."""

    dots: int
    is_rest: bool
    starts_group: bool
    """Enigma's `beam` bit: this entry opens a new group."""


def beams_for(notes: Sequence[BeamedNote]) -> list[tuple[Beam, ...]]:
    """Beams for each note of one (staff, measure, layer), in playing order.

    Returns one tuple per input note, empty where the note carries no beam --
    a lone eighth is written with a flag instead, so a group of one gets
    nothing.
    """
    out: list[tuple[Beam, ...]] = [() for _ in notes]
    for group in _groups(notes):
        if len(group) < 2:
            continue
        levels = [_levels(notes[index]) for index in group]
        for level in range(1, max(levels) + 1):
            for start, end in _runs(levels, level):
                _assign(out, group, levels, level, start, end)
    return out


def _groups(notes: Sequence[BeamedNote]) -> list[list[int]]:
    """Indices of the notes in each beam group, in order."""
    groups: list[list[int]] = []
    current: list[int] = []
    for index, note in enumerate(notes):
        if not _beamable(note):
            current = []
            continue
        if note.starts_group or not current:
            current = []
            groups.append(current)
        current.append(index)
    return groups


def _beamable(note: BeamedNote) -> bool:
    """A rest breaks a group here.

    MusicXML can beam over a rest and Finale can draw one, but Enigma's bit
    says where groups *start*, not where they survive a rest -- so treating a
    rest as a break is the reading the data supports.
    """
    return not note.is_rest and note.written_duration <= _EIGHTH * 2 and _levels(note) >= 1


def _levels(note: BeamedNote) -> int:
    """How many beams this note's value carries: eighth 1, sixteenth 2, ...

    Dots do not add beams, so they are divided back out first: a dotted eighth
    is written 3/16 and beams once, like the eighth it is.
    """
    base = note.written_duration * (1 << note.dots) / ((1 << (note.dots + 1)) - 1)
    if base <= 0 or base > _EIGHTH:
        return 0
    count = 0
    while base <= _EIGHTH:
        base *= 2
        count += 1
    return count


def _runs(levels: Sequence[int], level: int) -> list[tuple[int, int]]:
    """(first, last) positions of each maximal run of notes reaching `level`."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for position, count in enumerate(levels):
        if count >= level:
            if start is None:
                start = position
        elif start is not None:
            runs.append((start, position - 1))
            start = None
    if start is not None:
        runs.append((start, len(levels) - 1))
    return runs


def _assign(
    out: list[tuple[Beam, ...]],
    group: Sequence[int],
    levels: Sequence[int],
    level: int,
    start: int,
    end: int,
) -> None:
    if start == end:
        # A single note at this level draws a hook rather than a beam. It points
        # back toward the note it belongs with, which is the previous one unless
        # this opens the group.
        direction = "forward hook" if start == 0 else "backward hook"
        _add(out, group[start], Beam(number=level, type=direction))
        return
    for position in range(start, end + 1):
        if position == start:
            kind = "begin"
        elif position == end:
            kind = "end"
        else:
            kind = "continue"
        _add(out, group[position], Beam(number=level, type=kind))
    _ = levels


def _add(out: list[tuple[Beam, ...]], index: int, beam: Beam) -> None:
    out[index] = (*out[index], beam)
