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

## Score expressions, and what still does not reach the IR

This module returns 11,462 markings and **11,145 reach a `Measure`**.

**596 of them name no staff at all.** `staffAssign = -1` means the marking belongs
to a **staff list**, and the file says so: all 746 corpus assignments carrying it
also carry `staffGroup` *and* `staffList`, where a positive-staff assignment
almost never does (138 of 11,687). 81 are a second copy of a marking the same
measure already places on a real staff, and this module drops those as redundant;
the remaining **515 are placed on the topmost part** by
`to_ir._place_score_wide`, which explains why that is a convention rather than a
reading. `Expression.score_wide` records the fact so it is not lost in the move.

**317 remain dropped**, all one cause: they are assigned to a staff that holds no
notes anywhere in the document, and one `Part` is built per staff *with music*, so
there is nowhere to put them. Whether such a staff should become an empty part is
a question about part construction, not about expressions.

`tests/enigma/test_expressions_ir_corpus_sweep.py` pins every number here, in
both directions. It exists because the sweep beside it does not catch this: that
one asks `expressions_by_measure` what `expressions_by_measure` found, which is a
reader confirming itself. Measure the delivered object.

## Rehearsal marks

Their label is not in the file: the expression text is the bare `^rehearsal()`
insert, so `plain_text` yields nothing and all 113 corpus assignments were
dropped for having nothing to print. `rehearsalMarkStyle` says how to work it out
-- `measNum` for 99 of them, where the label is the measure number and no
convention is involved, `letters` for 12, numbered by position. See
`_rehearsal_labels`. 90 marks are placed across 10 documents.

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
from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.text import plain_text
from finale_file_parser.formats.dynamics import (
    DYNAMICS_CATEGORY,
    described_dynamic,
    dynamic_for,
)
from finale_file_parser.ir import Expression

__all__ = ["SCORE_WIDE_STAFF", "expressions_by_measure"]

SCORE_WIDE_STAFF = -1
"""The `staffAssign` a score expression carries instead of a staff number.

It means "this belongs to a **staff list**", and the file says so: all 746 corpus
assignments carrying it also carry `staffGroup` *and* `staffList`, where a
positive-staff assignment almost never does (138 of 11,687). Kept as the key so
`to_ir` can decide where a score-wide marking goes; nothing downstream should
treat it as a staff.
"""

_ASSIGN = "measExprAssign"
_DEF = "textExprDef"
_CATEGORY = "markingsCategory"
_TEXT = "expression"

_REHEARSAL = re.compile(r"\^rehearsal\(\)")
"""The insert that stands where a rehearsal mark's label would be.

The label is not in the file. The expression text is this command and nothing
else, so `plain_text` yields `""` -- correctly, since it has no literal text --
and every one of the corpus's 113 marks was dropped for having nothing to print.
What the file gives instead is `rehearsalMarkStyle`, which says how to work the
label out. See `_rehearsal_labels`.
"""

_MEASURE_NUMBER_STYLE = "measNum"
_LETTER_STYLE = "letters"
_NUMBER_STYLE = "numbers"

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

    on_a_staff = _staffed(document)
    labels = _rehearsal_labels(document, definitions, texts)

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
        if definition is None or found is None:
            continue
        if staff == SCORE_WIDE_STAFF and (measure, expr_id) in on_a_staff:
            # The same expression is already placed on a real staff in this
            # measure, so the score-wide copy would print it twice. 102 of the
            # corpus's 746 list assignments are this shape.
            continue
        # A rehearsal mark prints a label the file does not store, so it is the
        # one expression kept despite having no literal text of its own.
        label = labels.get(measure) if found.is_rehearsal else None
        text = label if label is not None else found.printed
        # An expression with nothing to print is not a marking: 306 corpus
        # assignments resolve to a definition whose text record is absent, and a
        # rehearsal mark whose style is unreadable has no label to print.
        if not text:
            continue
        category = categories.get(_int(definition.fields.get("categoryID")), "")
        out.setdefault((staff, measure), []).append(
            Expression(
                text=text,
                category=category,
                marking=_marking(
                    found.printed,
                    category=category,
                    in_music_font=found.in_music_font,
                    description=str(definition.fields.get("descStr") or ""),
                ),
                velocity=_int(definition.fields.get("value")),
                score_wide=staff == SCORE_WIDE_STAFF,
                is_rehearsal=label is not None,
                layer=_int(record.fields.get("layer")),
            )
        )
    return {where: tuple(items) for where, items in out.items()}


def _rehearsal_labels(
    document: EnigmaDocument, definitions: dict[int, Record], texts: dict[int, _Text]
) -> dict[int, str]:
    """Measure -> the label its rehearsal mark prints.

    A mark placed on several staves of one measure is **one** mark, so the label
    is keyed by measure: numbering per assignment would give the same bar two
    different letters.

    Three styles, and only one of them needs a convention:

    * `measNum` -- the label *is* the measure number. 99 of the corpus's 113
      marks, and nothing is guessed.
    * `numbers` -- the mark's position, counting from 1.
    * `letters` -- A, B, C in measure order. 12 corpus marks. This is the
      convention, and it is Finale's own; past Z it continues AA, AB.

    A mark whose definition gives no style is left out rather than defaulted:
    two corpus marks are that shape, and inventing a label for them would put a
    letter in the score that the file does not ask for.
    """
    styles: dict[int, str] = {}
    for record in document.others.of_tag(_ASSIGN):
        if "part" in record.attrs:
            continue
        measure = _int(record.attrs.get("cmper"))
        expr_id = _int(record.fields.get("textExprID"))
        if measure is None or expr_id is None or expr_id not in texts:
            continue
        if not texts[expr_id].is_rehearsal:
            continue
        definition = definitions.get(expr_id)
        style = str(definition.fields.get("rehearsalMarkStyle")) if definition else ""
        if style in (_MEASURE_NUMBER_STYLE, _LETTER_STYLE, _NUMBER_STYLE):
            styles.setdefault(measure, style)

    out: dict[int, str] = {}
    for position, measure in enumerate(sorted(styles)):
        style = styles[measure]
        if style == _MEASURE_NUMBER_STYLE:
            out[measure] = str(measure)
        elif style == _NUMBER_STYLE:
            out[measure] = str(position + 1)
        else:
            out[measure] = _letter(position)
    return out


def _letter(position: int) -> str:
    """A, B, ... Z, AA, AB -- the spreadsheet-column sequence Finale uses."""
    letters = ""
    position += 1
    while position:
        position, remainder = divmod(position - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _staffed(document: EnigmaDocument) -> set[tuple[int, int]]:
    """(measure, expression id) pairs already assigned to a real staff.

    A score expression is drawn once; where the document also assigns the same
    expression to a staff in that measure, the score-wide copy is redundant.
    """
    out: set[tuple[int, int]] = set()
    for record in document.others.of_tag(_ASSIGN):
        if "part" in record.attrs:
            continue
        staff = _int(record.fields.get("staffAssign"))
        measure = _int(record.attrs.get("cmper"))
        expr_id = _int(record.fields.get("textExprID"))
        if staff is None or staff < 0 or measure is None or expr_id is None:
            continue
        out.add((measure, expr_id))
    return out


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


@dataclass(frozen=True)
class _Text:
    """What one expression text record says, once its markup has been read."""

    printed: str
    """The literal characters, markup stripped. Empty for a rehearsal mark,
    whose text is only an insert command."""

    in_music_font: bool
    """The font matters because five dynamics are plain letters."""

    is_rehearsal: bool
    """The text is the `^rehearsal()` insert, so the label has to be worked out."""


def _texts(document: EnigmaDocument) -> dict[int, _Text]:
    """Expression number -> what its text record says.

    The markup is kept long enough to answer both questions it decides -- which
    font, and whether the label is an insert -- and then discarded.
    """
    out: dict[int, _Text] = {}
    for record in document.texts.records:
        if record.tag != _TEXT or "part" in record.attrs:
            continue
        number = _int(record.attrs.get("number"))
        if number is None:
            continue
        markup = record.text or ""
        out[number] = _Text(
            printed=plain_text(markup),
            in_music_font=bool(_MUSIC_FONT.search(markup)),
            is_rehearsal=bool(_REHEARSAL.search(markup)),
        )
    return out


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
