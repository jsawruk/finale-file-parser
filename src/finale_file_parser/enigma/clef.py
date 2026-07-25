"""Clefs: the definition table, and which clef is in force where.

Enigma keeps a document-wide table of clef definitions (`clefOptions.clefDef`,
18 entries) and refers to them by index. Two things carry an index:

* `staffSpec.defaultClef` -- the staff's clef, omitted when it is 0.
* `gfhold.clefID` -- the clef at that (staff, measure).

`clefID` is present on **every** `gfhold` in the corpus (4,214 of 4,214), so it is
the *effective* clef at that measure rather than only a change marker. Unlike the
key signature, there is no inheritance to apply.

A definition gives a font character (`clefChar`) plus staff placement, or, when
`isShape` is set, a drawn shape instead of a character.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.models import CorruptScoreError

__all__ = [
    "Clef",
    "ClefSign",
    "clef_definitions",
    "clefs_by_measure",
    "default_clefs",
]

_CLEF_OPTIONS = "clefOptions"
_CLEF_DEF = "clefDef"
_STAFF_SPEC = "staffSpec"
_GFHOLD = "gfhold"


class ClefSign(Enum):
    """What kind of clef a definition draws.

    Derived from the Maestro font character. Only G and F are *confirmed by use*
    in the corpus, which exercises clef indices 0, 3 and 16 only; C and the other
    characters appear in the definition table but no staff selects them, so their
    mapping is from the font's layout rather than from observed data. Anything
    unrecognised stays UNKNOWN rather than being guessed into a wrong clef.
    """

    G = "G"
    F = "F"
    C = "C"
    SHAPE = "shape"
    """Drawn from a shape rather than a character -- percussion, in practice."""
    UNKNOWN = "unknown"


_CHARACTER_SIGNS = {
    38: ClefSign.G,
    63: ClefSign.F,
    66: ClefSign.C,
}
"""Maestro characters: '&' treble, '?' bass, 'B' the C clef. Confirmed for 38 and
63, which are the only characters any corpus staff actually selects."""


@dataclass(frozen=True)
class Clef:
    """One entry in the document's clef table."""

    index: int
    clef_char: int | None
    """Maestro font character, or None for a shape clef."""

    adjust: int
    """Staff-position offset for the clef's placement."""

    y_displacement: int
    shape_id: int | None
    """Set instead of `clef_char` when the clef is drawn as a shape."""

    @property
    def is_shape(self) -> bool:
        return self.shape_id is not None

    @property
    def sign(self) -> ClefSign:
        if self.is_shape:
            return ClefSign.SHAPE
        if self.clef_char is None:
            return ClefSign.UNKNOWN
        return _CHARACTER_SIGNS.get(self.clef_char, ClefSign.UNKNOWN)


def _optional_int(record: Record, name: str) -> int | None:
    """A numeric field, or None when absent.

    Absent is meaningful here: EnigmaXML omits a field rather than writing 0, so
    `adjust` missing means 0 while `clefChar` missing means there is no character.
    """
    raw = record.fields.get(name)
    if not isinstance(raw, str) or raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise CorruptScoreError(f"clefDef {name}={raw!r} is not an integer") from exc


def clef_definitions(document: EnigmaDocument) -> dict[int, Clef]:
    """The document's clef table, keyed by index.

    Returns an empty mapping when the document defines no `clefOptions`.
    """
    options = [r for r in document.options.of_tag(_CLEF_OPTIONS) if "part" not in r.attrs]
    if not options:
        return {}
    raw = options[0].fields.get(_CLEF_DEF)
    definitions = raw if isinstance(raw, tuple) else (raw,) if isinstance(raw, Record) else ()
    out: dict[int, Clef] = {}
    for index, record in enumerate(definitions):
        if not isinstance(record, Record):
            continue
        out[index] = Clef(
            index=index,
            clef_char=_optional_int(record, "clefChar"),
            adjust=_optional_int(record, "adjust") or 0,
            y_displacement=_optional_int(record, "clefYDisp") or 0,
            shape_id=_optional_int(record, "shapeID"),
        )
    return out


def default_clefs(document: EnigmaDocument) -> dict[int, int]:
    """Each staff's default clef index, keyed by staff number.

    `defaultClef` is omitted when it is 0 (treble), so an absent field is reported
    as 0 rather than skipped -- dropping those staves would lose every
    treble-clef staff in the document.
    """
    out: dict[int, int] = {}
    for record in document.others.of_tag(_STAFF_SPEC):
        if "part" in record.attrs:
            continue
        raw = record.attrs.get("cmper")
        if raw is None:
            raise CorruptScoreError("staffSpec has no cmper")
        out[int(raw)] = _optional_int(record, "defaultClef") or 0
    return out


def clefs_by_measure(document: EnigmaDocument) -> dict[tuple[int, int], int]:
    """Effective clef index at each (staff, measure).

    Taken from `gfhold.clefID`, which every corpus `gfhold` carries. A `gfhold`
    without one falls back to the staff's default rather than being dropped, so a
    caller never has to distinguish "no clef" from "treble".
    """
    defaults = default_clefs(document)
    out: dict[tuple[int, int], int] = {}
    for record in document.details.of_tag(_GFHOLD):
        if "part" in record.attrs:
            continue
        staff = int(record.attrs["cmper1"])
        measure = int(record.attrs["cmper2"])
        clef = _optional_int(record, "clefID")
        out[(staff, measure)] = defaults.get(staff, 0) if clef is None else clef
    return out
