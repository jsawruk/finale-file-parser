"""Resolve fingerings: the small numerals telling a player which finger to use.

Finale has no fingering object. A fingering is an ordinary articulation whose
character happens to be a numeral, which is why `enigma.articulations` cannot
simply pass it through -- it would have to call `1` an articulation named "1".

The character alone identifies one, and the reason is worth stating because the
obvious objection is that a music font also has glyphs at those code points:

* every numeral definition in the corpus -- 2,062 of them, `1` through `5` --
  carries an explicit `fontMain`. **Not one uses the document's music font.**
* those definitions occupy a font of their own. Across the corpus the numerals
  are assigned under exactly one font id, and no other character is ever
  assigned under it: 834 assignments, all numerals, nothing else.

So a numeral articulation in this corpus is always text, and always a fingering.
A music-font numeral would be some other glyph entirely, and none exists to be
confused with one.

That last point is what makes this readable from a `.mus`, which the project
previously recorded as blocked. `fontMain`'s offset in the `.mus` `articDef`
genuinely does move within the 2011 era -- the best single offset matches 363 of
373 paired records, so it cannot be read -- but the **character** is already
recovered, and the character is enough.

**The `.mus` side is unverified against a paired document.** Six paired
documents carry a fingering in their `.musx`; four have a `.mus` that does not
read, and the other two are a different arrangement of the same piece. So no
pair confirms a fingering directly.

What *is* verified is the mechanism it rests on: `articDef.charMain` is read
from a `.mus` across 72 paired documents and 25,000-odd articulation
assignments, with the two containers agreeing exactly. Fingerings add no new
field -- the same character, at the same offset, with different values. The risk
is that this corpus happens not to exercise those values on the legacy side, not
that the reading is unfounded.
"""

from __future__ import annotations

from finale_file_parser.enigma.document import EnigmaDocument

__all__ = ["FINGERING_CHARACTERS", "fingerings_by_entry"]

_ASSIGN = "articAssign"
_DEFINITION = "articDef"

FINGERING_CHARACTERS = {49: "1", 50: "2", 51: "3", 52: "4", 53: "5"}
"""Music-font character -> the fingering it prints.

ASCII `1`-`5`. The corpus assigns 3 most often (261), then 1 (219), 2 (174), 4
(126) and 5 (54) -- the order you would expect of keyboard and string music,
which corroborates the reading without proving it.

Deliberately no `0`: three definitions carry it and none is ever assigned, so
there is nothing to say whether it means an open string or an unused slot.
"""


def fingerings_by_entry(document: EnigmaDocument) -> dict[int, tuple[str, ...]]:
    """Fingerings, grouped by the entry they are attached to.

    An entry can carry several -- a chord fingered on three notes -- and order
    follows the document. Repeats are dropped the same way
    `enigma.articulations` drops them, since a `.mus` restates an assignment.
    """
    characters = _definitions(document)
    out: dict[int, list[str]] = {}
    seen: set[tuple[int, int]] = set()
    for record in document.details.of_tag(_ASSIGN):
        entnum = _int(record.attrs.get("entnum"))
        definition = _int(record.fields.get(_DEFINITION))
        if entnum is None or definition is None or (entnum, definition) in seen:
            continue
        digit = FINGERING_CHARACTERS.get(characters.get(definition, -1))
        if digit is None:
            continue
        seen.add((entnum, definition))
        out.setdefault(entnum, []).append(digit)
    return {entnum: tuple(digits) for entnum, digits in out.items()}


def _definitions(document: EnigmaDocument) -> dict[int, int]:
    """articDef cmper -> its main character. Score records only."""
    out: dict[int, int] = {}
    for record in document.others.of_tag(_DEFINITION):
        if "part" in record.attrs:
            continue
        cmper = _int(record.attrs.get("cmper"))
        character = _int(record.fields.get("charMain"))
        if cmper is not None and character is not None:
            out[cmper] = character
    return out


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
