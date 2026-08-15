"""Which expressions a score actually places, and where.

Three records, and the middle one is a library rather than a list of what is
used:

    measExprAssign(measure)  -- a marking is placed here, on this staff
    textExprDef(cmper)       -- what it is: category, playback level, description
    texts/expression(number) -- what it prints, usually one music-font character

**Only an assignment puts a marking in the music.** Every corpus document ships
the same expression library whether it uses any of it or not -- sixteen
dynamics, a shelf of tempo words -- so reading `textExprDef` alone would print a
fortissimo in every part of every file. The same trap as `textRepeatText`; see
`enigma.jumps`.

## The join

`measExprAssign.textExprID` names the definition, and it holds up: across the
401-document corpus **every** assignment that carries an id resolves --
5,663 through `textExprID` to a `textExprDef` and 91 through `shapeExprID` to a
`shapeExprDef`, with none left dangling. The remaining 7,488 carry no id at all
and place nothing.

Resolved, the corpus yields **6,672 assigned dynamics across 315 documents**,
distributed as real music is rather than as a library is: f 1,715, mf 1,501,
p 1,461, mp 777, ff 420, pp 161, ppp 45, fff 38, ffff 12. A palette read by
mistake would instead give a flat count of about 400 for every entry.

Definition to printed text pairs on **`cmper`**, not `textIDKey` -- see
`docs/formats/expressions-and-dynamics.md` for why, and for how the ten dynamics
came to be named.

## When a glyph counts as a dynamic

Five of the ten dynamic characters are **plain ASCII letters** -- Maestro writes
forte as `f` and mezzo piano as `P` -- so matching the character alone would read
a literal "f" label as a fortissimo. Two signals settle it, and the corpus says
which to trust:

| category | font | glyph in the table | count |
| --- | --- | --- | --- |
| `dynamics` | `^fontMus` | yes | 6,182 |
| `techniqueText` | `^fontMus` | yes | 1,191 |
| `dynamics` | none | yes | 114 |
| `misc` / `tempoMarks` / `expressiveText` | none | yes | 129 |
| anything | `^fontTxt` | **yes** | **0** |

The last row is the useful one: across 401 documents **nothing set in a text
font ever matches the table**, so the font markup never produces a false
dynamic. The 1,191 `techniqueText` rows are user copies of a dynamic glyph filed
in a custom category -- still a dynamic, since it is the Maestro character.

So `marking` is claimed when the glyph is in the table **and** either the text is
set in a music font or the document's own category is `dynamics`. The 129 rows
with neither signal are left unmarked: a bare `f` in `misc` with no font at all
is as likely to be a label as a dynamic, and this project does not guess. The
text is still carried, so nothing is lost.

## Not everything read reaches the IR

This module returns 11,543 markings. **10,630 of them reach a `Measure`**; 913,
in 267 documents, do not, because `build_score` keys them by staff and those
name a staff it built no `Part` for. Two causes, both measured, neither guessed:

* **596 are assigned to a staff *list*.** `staffAssign = -1` is the sentinel, and
  the file says so: all 746 corpus assignments carrying it also carry
  `staffGroup` *and* `staffList`, where a positive-staff assignment almost never
  does (138 of 11,687). `staffList` selects a `categoryStaffListScore`, whose
  repeated `inst` is `-1` in 6,215 of 6,419 incidences -- but the rest name real
  staves, and `-1` turns up *beside* them in tuples like `('-1', '9', '13')`. So
  `-1` cannot be read as "every staff" without risking a marking on a staff the
  list excludes. Unresolved on purpose.
* **317 are assigned to a staff that holds no notes at all.** One `Part` is built
  per staff with music, so a staff carrying only an expression has nowhere to put
  it. Whether it should become an empty part is a question about part
  construction, not about expressions.

`tests/enigma/test_expressions_ir_corpus_sweep.py` pins all three numbers in both
directions. It exists because the sweep beside it does not catch this: that one
asks `expressions_by_measure` what `expressions_by_measure` found, which is a
reader confirming itself. Measure the delivered object.

## What is not read

**Placement.** `horzEvpuOff` and `vertOff` carry the offsets Finale drew the
marking at. They are not converted: EVPU to tenths is a scaling this project has
not confirmed, and an exporter placing a dynamic at a wrong offset is worse than
one letting the consumer default it.

**Shape expressions.** `shapeExprID` names a drawn shape rather than text --
91 assignments in the corpus. There is nothing to print as text, and this module
carries text markings only.

**A 2001-2005 `.mus`.** The 2011 era is read -- `others` 241 is the definition
and 177 the assignment, see `mus_others` -- and yields 3,022 markings across 186
documents. The DCL era is not: it spells them `^DT` and `^DY`, and only one `DT`
field is decoded (the playback value at `+4`, confirmed 434/434 by the record's
own description). See `mus_document.UNTRANSLATED`.

**A `.mus` expression has no category and no layer.** `categoryID` is not
identified in the 241 record (best offset 20.3%, which is noise) and `layer`
collides with `staffAssign` at `+8`. Both are absent rather than invented, so
`category` is `""` and `layer` is None for every `.mus` expression -- and the
dynamics are still named, because the description does that on its own.
"""

from __future__ import annotations

import re

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.text import plain_text
from finale_file_parser.formats.dynamics import (
    DYNAMICS_CATEGORY,
    described_dynamic,
    dynamic_for,
)
from finale_file_parser.ir import Expression

__all__ = ["expressions_by_measure"]

_ASSIGN = "measExprAssign"
_DEF = "textExprDef"
_CATEGORY = "markingsCategory"
_TEXT = "expression"

_MUSIC_FONT = re.compile(r"\^fontMus\(")
"""EnigmaXML's marker for text set in a music font.

`fontName` cmper 0 is `Maestro` in every corpus document, so a character behind
this markup is a glyph rather than a letter to read.

A `.mus` has no equivalent: its dialect spells the command `^font(` without
saying whether the font is a music one, and it carries no `fontName` records to
resolve the id against. That is why the description is the primary signal -- a
`.mus` dynamic is named from `descStr` alone.
"""


def expressions_by_measure(
    document: EnigmaDocument,
) -> dict[tuple[int, int], tuple[Expression, ...]]:
    """The markings the score places, keyed by `(staff, measure)`.

    A staff and measure can carry more than one, and order follows the document.
    """
    categories = _categories(document)
    definitions = _definitions(document)
    texts = _texts(document)

    out: dict[tuple[int, int], list[Expression]] = {}
    for record in document.others.of_tag(_ASSIGN):
        # A linked part repeats every assignment. Counting those doubles each
        # marking: 20,606 of the corpus's 33,039 records carry a `part`.
        if "part" in record.attrs:
            continue
        measure = _int(record.attrs.get("cmper"))
        staff = _int(record.fields.get("staffAssign"))
        expr_id = _int(record.fields.get("textExprID"))
        if measure is None or staff is None or expr_id is None:
            continue
        definition = definitions.get(expr_id)
        found = texts.get(expr_id)
        # An expression with nothing to print is not a marking: 306 corpus
        # assignments resolve to a definition whose text record is absent.
        if definition is None or found is None or not found[0]:
            continue
        text, in_music_font = found
        category = categories.get(_int(definition.fields.get("categoryID")), "")
        out.setdefault((staff, measure), []).append(
            Expression(
                text=text,
                category=category,
                marking=_marking(
                    text,
                    category=category,
                    in_music_font=in_music_font,
                    description=str(definition.fields.get("descStr") or ""),
                ),
                velocity=_int(definition.fields.get("value")),
                layer=_int(record.fields.get("layer")),
            )
        )
    return {where: tuple(items) for where, items in out.items()}


def _categories(document: EnigmaDocument) -> dict[int | None, str]:
    """categoryID -> the type the document itself gives it.

    `dynamics`, `tempoMarks`, `techniqueText` and the rest are the file's own
    words. Nothing here is inferred from what a marking looks like.
    """
    out: dict[int | None, str] = {}
    for record in document.others.of_tag(_CATEGORY):
        kind = record.fields.get("categoryType")
        if isinstance(kind, str):
            out[_int(record.attrs.get("cmper"))] = kind
    return out


def _definitions(document: EnigmaDocument) -> dict[int, Record]:
    out: dict[int, Record] = {}
    for record in document.others.of_tag(_DEF):
        if "part" in record.attrs:
            continue
        cmper = _int(record.attrs.get("cmper"))
        if cmper is not None:
            out[cmper] = record
    return out


def _marking(text: str, *, category: str, in_music_font: bool, description: str) -> str | None:
    """The readable dynamic this expression is, or None if it is not one.

    Three signals, strongest first:

    1. **The description names it.** `'fortissimo (velocity = 101)'` is the file
       saying which dynamic this is, in words. No glyph or font reasoning can
       beat that, and it is what named the table in the first place. It is also
       the only signal a `.mus` document offers: that container has no
       `^fontMus` markup and its category is not decoded.
    2. **The glyph is in the table and set in a music font.** For a `.musx`,
       where the markup distinguishes.
    3. **The glyph is in the table and the document's own category is
       `dynamics`.**

    Anything else is left unnamed -- see "When a glyph counts as a dynamic" in
    the module docstring for the counts behind the rule.
    """
    described = described_dynamic(description)
    if described is not None:
        return described.marking
    entry = dynamic_for(text)
    if entry is None:
        return None
    if in_music_font or category == DYNAMICS_CATEGORY:
        return entry.marking
    return None


def _texts(document: EnigmaDocument) -> dict[int, tuple[str, bool]]:
    """Expression number -> (what it prints, is it set in a music font).

    The font matters because five dynamics are plain letters; the markup is kept
    long enough to answer that and then discarded.
    """
    out: dict[int, tuple[str, bool]] = {}
    for record in document.texts.records:
        if record.tag != _TEXT or "part" in record.attrs:
            continue
        number = _int(record.attrs.get("number"))
        if number is None:
            continue
        markup = record.text or ""
        out[number] = (plain_text(markup), bool(_MUSIC_FONT.search(markup)))
    return out


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
