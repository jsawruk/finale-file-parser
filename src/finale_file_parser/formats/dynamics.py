"""Which Maestro character a dynamic marking is written with.

A dynamic is not stored as text. `"ff"` appears nowhere in a Finale file --
searching the whole corpus for it finds the `ff` inside *Staff* and nothing
else. What is stored is a single character in the Maestro music font, and
Maestro draws one glyph per marking rather than one per letter.

This table is the ten characters the corpus uses for dynamics, each with the
playback velocity the file gives it. Both halves come out of the same record:
a `textExprDef` in the category the document itself types as `dynamics` carries
a `value`, and its `cmper` selects the expression text holding the character.

**Velocity, not a name.** The ladder is the document default and is unanimous
across the corpus but for one edit: `P` is 62 in 80 documents and 58 in one,
which is a user changing a playback level rather than a different table. The
*order* is therefore certain -- 127 down to 10 in steps of 13. Naming
each one `fff`, `ff` and so on is a further step this project has not taken:
that needs Maestro's own character chart, and Finale's manual renders it as
images. Two anchors do fall where they should, which is why the ordering can be
trusted: Maestro writes *forte* as `f` and *piano* as `p`, and those sit at 88
and 49 -- exactly forte's and piano's places in a ten-step ladder.
"""

from __future__ import annotations

__all__ = ["DYNAMICS_CATEGORY", "MAESTRO_DYNAMICS", "velocity_of"]

DYNAMICS_CATEGORY = "dynamics"
"""The `categoryType` a `markingsCategory` gives its dynamics.

The file classifies its own expressions -- `dynamics`, `tempoMarks`,
`tempoAlts`, `expressiveText`, `techniqueText`, `rehearsalMarks`, `misc` -- and
`markingsCategoryName` gives the display name. Nothing here is inferred from
what an expression looks like.
"""

MAESTRO_DYNAMICS: dict[str, int] = {
    "ë": 127,  # ë
    "ì": 114,  # ì
    "Ä": 101,  # Ä
    "f": 88,  # forte, in Maestro's own spelling
    "F": 75,
    "P": 62,
    "p": 49,  # piano
    "¹": 36,  # ¹
    "¸": 23,  # ¸
    "¯": 10,  # ¯
}
"""Maestro character to playback velocity, loudest first.

Measured across 80 corpus `.musx` documents. Nine of the ten are unanimous;
`P` is 62 in 80 and 58 in one, a document whose playback level was edited. The
value here is the default every document ships with, not a promise about what
any particular file says -- read the file's own `textExprDef` if the exact
level matters.

`subito p` shares piano's 49, being piano with a word in front of it.
"""


def velocity_of(glyph: str) -> int | None:
    """The velocity Finale gives this dynamic, or None for a character this
    project has not seen used as one."""
    return MAESTRO_DYNAMICS.get(glyph)
