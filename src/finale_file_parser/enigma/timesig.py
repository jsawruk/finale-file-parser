"""Time signatures.

Enigma does not store a numerator and denominator. It stores how many divisions a
measure has (`beats`) and how long each division is in EDU (`divbeat`), which is
how it represents compound meters naturally: 6/8 is two dotted-quarter divisions,
not six eighths. `TimeSignature` keeps that representation and derives the
conventional pair on request.

Every `measSpec` in the corpus carries both fields (2,622 of 2,622), so unlike the
key signature there is no inheritance to apply.

A measure may also carry a *display* time signature -- what is printed, as opposed
to what the measure actually holds. It is only meaningful when `useDisplayTimesig`
is set; see `display_time_signature`.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.models import CorruptScoreError

__all__ = [
    "TimeSignature",
    "display_time_signature",
    "read_time_signature",
    "time_signatures",
]

_WHOLE_EDU = 4096
_MEASURE_SPEC = "measSpec"
_DOTTED_FACTOR = 3
"""A dotted division is three of the next-smaller undotted unit."""


@dataclass(frozen=True)
class TimeSignature:
    """How a measure divides its time.

    `beats` divisions of `division_edu` each. 4/4 is 4 x 1024; 6/8 is 2 x 1536,
    because a dotted quarter is 1536 EDU.
    """

    beats: int
    division_edu: int

    @property
    def total_edu(self) -> int:
        """Written EDU the measure holds."""
        return self.beats * self.division_edu

    @property
    def is_compound(self) -> bool:
        """Does each division subdivide into three rather than two?"""
        return self.division_edu % _DOTTED_FACTOR == 0 and _is_power_of_two(
            self.division_edu // _DOTTED_FACTOR
        )

    @property
    def numerator(self) -> int:
        """Conventional numerator: 6 for 6/8, not 2."""
        return self.beats * _DOTTED_FACTOR if self.is_compound else self.beats

    @property
    def denominator(self) -> int:
        """Conventional denominator: 8 for 6/8."""
        unit = self.division_edu // _DOTTED_FACTOR if self.is_compound else self.division_edu
        if not _is_power_of_two(unit) or unit > _WHOLE_EDU:
            raise CorruptScoreError(
                f"division of {self.division_edu} EDU is not a notatable note value"
            )
        return _WHOLE_EDU // unit

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def _positive_int(record: Record, name: str) -> int:
    raw = record.fields.get(name)
    if not isinstance(raw, str):
        raise CorruptScoreError(f"measSpec is missing {name!r}")
    try:
        value = int(raw)
    except ValueError as exc:
        raise CorruptScoreError(f"measSpec {name}={raw!r} is not an integer") from exc
    if value <= 0:
        raise CorruptScoreError(f"measSpec {name}={value} must be positive")
    return value


def read_time_signature(record: Record) -> TimeSignature:
    """The time signature a `measSpec` actually holds.

    Raises:
        CorruptScoreError: `beats` or `divbeat` is missing or not a positive
            integer.
    """
    return TimeSignature(
        beats=_positive_int(record, "beats"),
        division_edu=_positive_int(record, "divbeat"),
    )


def display_time_signature(record: Record) -> TimeSignature | None:
    """The time signature *printed* on this measure, if it differs.

    Returns None unless the measure sets `useDisplayTimesig`. The `dispBeats` and
    `dispDivbeat` fields are present on every measure but hold a default when the
    flag is clear -- reading them unconditionally reports a display signature for
    1,937 of 2,622 corpus measures that do not have one, usually claiming 4/4 over
    a measure that is really 3/4.

    Raises:
        CorruptScoreError: the flag is set but the display fields are unusable.
    """
    if "useDisplayTimesig" not in record.fields:
        return None
    return TimeSignature(
        beats=_positive_int(record, "dispBeats"),
        division_edu=_positive_int(record, "dispDivbeat"),
    )


def time_signatures(document: EnigmaDocument) -> dict[int, TimeSignature]:
    """Every measure's time signature, keyed by measure number.

    Score records only; a linked-part `measSpec` would overwrite the score's.
    """
    out: dict[int, TimeSignature] = {}
    for record in document.others.of_tag(_MEASURE_SPEC):
        if "part" in record.attrs:
            continue
        raw = record.attrs.get("cmper")
        if raw is None:
            raise CorruptScoreError("measSpec has no cmper")
        out[int(raw)] = read_time_signature(record)
    return out
