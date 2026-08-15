"""Which Maestro character a dynamic marking is written with, and what it is called.

A dynamic is not stored as text. `"ff"` appears nowhere in a Finale file --
searching the whole corpus for it finds the `ff` inside *Staff* and nothing
else. What is stored is a single character in the Maestro music font, and
Maestro draws one glyph per marking rather than one per letter.

**The file names them itself.** A `textExprDef` carries a `descStr`, and for a
dynamic that field spells the marking out in words with its playback level
attached -- `'fortissimo (velocity = 101)'`, `'forte (velocity = 88)'`. So no
font chart is needed to say which glyph is which: `descStr` and `value` sit in
the *same record*, and they agree with each other in 4,369 records against 9
exceptions, every one of them a document whose playback level a user edited.

Joining a definition to the character it prints does need the text pool, on
`cmper` -- see `docs/formats/expressions-and-dynamics.md` for why that key and
not `textIDKey`. The glyph and the description agree in 393 of 396 documents
that carry a dynamics category; the three that do not are three corpus copies of
one document, explained there, and none of them contradicts this table.

The ten graded dynamics land on an even ladder, 127 down to 10 in steps of 13.
The abbreviations below (`ff`, `mp`) are the conventional spellings of the
Italian words the file uses; the words are what was read out of the file.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ACCENT_DYNAMICS",
    "DYNAMICS",
    "DYNAMICS_CATEGORY",
    "GRADED_DYNAMICS",
    "MAESTRO_DYNAMICS",
    "OTHER_DYNAMICS",
    "Dynamic",
    "dynamic_for",
    "marking_of",
    "velocity_of",
]

DYNAMICS_CATEGORY = "dynamics"
"""The `categoryType` a `markingsCategory` gives its dynamics.

The file classifies its own expressions -- `dynamics`, `tempoMarks`,
`tempoAlts`, `expressiveText`, `techniqueText`, `rehearsalMarks`, `misc` -- and
`markingsCategoryName` gives the display name. Nothing here is inferred from
what an expression looks like.
"""


@dataclass(frozen=True)
class Dynamic:
    """One entry of the dynamics library Finale ships in every document."""

    glyph: str
    """The Maestro character that prints it. One character, except `subito p`."""

    name: str
    """The words the file uses for it, from `descStr` with the velocity stripped."""

    marking: str | None
    """The conventional abbreviation, or None where the file does not settle it.

    `None` is not "unknown character" -- it means `descStr` does not distinguish
    this glyph from another, or the marking has no single agreed spelling.
    """

    velocity: int | None
    """The default playback velocity, or None where the shipped definition
    carries no `value` -- the accent dynamics, which modify an attack rather
    than setting a level. None means "no default", not "never has one": a user
    can give any expression a playback level."""


GRADED_DYNAMICS: tuple[Dynamic, ...] = (
    Dynamic("ë", "fortissississimo", "ffff", 127),
    Dynamic("ì", "fortississimo", "fff", 114),
    Dynamic("Ä", "fortissimo", "ff", 101),
    Dynamic("f", "forte", "f", 88),
    Dynamic("F", "mezzo forte", "mf", 75),
    Dynamic("P", "mezzo piano", "mp", 62),
    Dynamic("p", "piano", "p", 49),
    Dynamic("¹", "pianissimo", "pp", 36),
    Dynamic("¸", "pianississimo", "ppp", 23),
    Dynamic("¯", "pianissississimo", "pppp", 10),
)
"""The ten levelled dynamics, loudest first, on an even ladder in steps of 13.

Each name is `descStr`; each velocity is the `value` in the same record, and
`descStr` states it too. Two of the glyphs are the letters themselves -- Maestro
writes *forte* as `f` and *piano* as `p` -- and they fall on the fourth and
seventh rungs, which is where forte and piano belong in a ten-step ladder.
"""

ACCENT_DYNAMICS: tuple[Dynamic, ...] = (
    Dynamic("ê", "forte piano", "fp", None),
    Dynamic("Z", "forzando", "fz", None),
    Dynamic("S", "sforzando", None, None),
    Dynamic("§", "sforzato", None, None),
    Dynamic("\x8d", "sforzato", None, None),
)
"""The five that shape an attack instead of setting a level, so the shipped
library gives them no `value`. A user can still set one -- one corpus document
gives its *sforzando* 88 with `playType='amplitude'` -- so `None` here means
"no default", not "never has one".

Three are left unabbreviated on purpose. Two glyphs -- `§` and `\\x8d` -- both
read `sforzato` in `descStr`, so the file does not say which is which, and
*sforzando* is written `sf` and `sfz` both. Naming them needs evidence this
project does not have; the glyphs and the file's own words are recorded so the
gap is visible rather than guessed.
"""

OTHER_DYNAMICS: tuple[Dynamic, ...] = (Dynamic("subito p", "subito piano", "subito p", 49),)
"""Spelled text with a dynamic on the end, sharing piano's 49 -- piano with a
word in front of it. The only library entry whose `glyph` is more than one
character."""

DYNAMICS: tuple[Dynamic, ...] = GRADED_DYNAMICS + ACCENT_DYNAMICS + OTHER_DYNAMICS
"""The whole shipped dynamics library, in the order the file numbers it."""

MAESTRO_DYNAMICS: dict[str, int] = {d.glyph: d.velocity for d in DYNAMICS if d.velocity is not None}
"""Maestro character to default playback velocity, loudest first.

The shipped default, not a promise about what any particular file says: a
document can have its playback levels edited, and two in this corpus have --
`P` at 58 in one and `¹` at 44 in another. Read the file's own `textExprDef` if
the exact level matters.
"""

_BY_GLYPH: dict[str, Dynamic] = {d.glyph: d for d in DYNAMICS}


def dynamic_for(glyph: str) -> Dynamic | None:
    """The library entry printed by this character, or None if it is not one."""
    return _BY_GLYPH.get(glyph)


def velocity_of(glyph: str) -> int | None:
    """The velocity Finale gives this dynamic, or None for a character this
    project has not seen used as one -- and also None for the accent dynamics,
    which carry no level. Use `dynamic_for` to tell those two cases apart."""
    entry = _BY_GLYPH.get(glyph)
    return entry.velocity if entry else None


def marking_of(glyph: str) -> str | None:
    """The conventional abbreviation for this character -- `'ff'` for `Ä`.

    None both for a character that is not a dynamic and for one the file does
    not name unambiguously; `dynamic_for` distinguishes them and always gives
    the file's own wording in `name`.
    """
    entry = _BY_GLYPH.get(glyph)
    return entry.marking if entry else None
