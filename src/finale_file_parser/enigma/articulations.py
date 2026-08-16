"""Resolve a document's articulations: which marks sit on which entry.

Two records, as usual. An `articAssign` entry detail names an `articDef`, and
the definition says what the mark *is* -- not by name, but as a **character in a
music font**:

    articAssign(entnum) -> articDef -> charMain

So the meaning has to come from the character, the way `clef.py` reads a clef
from `clefChar`. The characters below sit at the same ASCII positions in every
music font the corpus uses -- Maestro, Engraver Font Set and Broadway Copyist
each write staccato as `.`, accent as `>`, tenuto as `-` and marcato as `^` --
which is what makes reading them without resolving the font defensible.

**Anything not in that table produces nothing.** The corpus assigns 29 distinct
characters, and the rest are either marks with no MusicXML equivalent or
symbols this project has no evidence for. Emitting a guess would put a wrong
articulation on a note, which is worse than leaving the note bare.

Not handled, and deliberately: **fingerings**. The corpus carries numerals 1-5
in a text font (Arial), which are fingerings rather than articulations -- but
telling them apart from a music-font numeral needs the font, and a `.mus` does
not reliably give one. Reading them would make the two containers disagree.
"""

from __future__ import annotations

from finale_file_parser.enigma.document import EnigmaDocument, field_int

__all__ = ["ARTICULATION_CHARACTERS", "articulations_by_entry"]

_ASSIGN = "articAssign"
_DEFINITION = "articDef"

ARTICULATION_CHARACTERS = {
    46: "staccato",  # .
    62: "accent",  # >
    45: "tenuto",  # -
    94: "strong-accent",  # ^  (marcato)
    44: "breath-mark",  # ,
}
"""Music-font character -> MusicXML articulation element.

Ordered by how often the corpus uses them: staccato 6,594, accent 3,123, tenuto
845, marcato 138, breath mark 54 in a 150-document sample. That ranking is what
you would expect of this repertoire, which corroborates the reading without
proving it -- the characters' meaning comes from the fonts' shared layout, not
from the corpus.

`breath-mark` is the least certain of the five and the rarest; it is included
because a comma is the breath mark in every music font here.
"""


def articulations_by_entry(document: EnigmaDocument) -> dict[int, tuple[str, ...]]:
    """MusicXML articulation names, grouped by the entry they are attached to.

    An entry can carry several -- a staccato and an accent, say -- and order
    follows the document. It never carries the *same* mark twice: no `.musx` in
    the corpus does that in 11,404 assignments. A `.mus` repeats one 23 times,
    which its reader drops as a storage artifact rather than this layer
    collapsing marks it cannot distinguish from deliberate ones.
    """
    characters = _definitions(document)
    out: dict[int, list[str]] = {}
    for record in document.details.of_tag(_ASSIGN):
        entnum = field_int(record.attrs.get("entnum"))
        definition = field_int(record.fields.get(_DEFINITION))
        if entnum is None or definition is None:
            continue
        name = ARTICULATION_CHARACTERS.get(characters.get(definition, -1))
        if name is None:
            continue
        out.setdefault(entnum, []).append(name)
    return {entnum: tuple(names) for entnum, names in out.items()}


def _definitions(document: EnigmaDocument) -> dict[int, int]:
    """articDef cmper -> its main character."""
    out: dict[int, int] = {}
    for record in document.others.of_tag(_DEFINITION):
        if "part" in record.attrs:
            continue
        cmper = field_int(record.attrs.get("cmper"))
        character = field_int(record.fields.get("charMain"))
        if cmper is not None and character is not None:
            out[cmper] = character
    return out
