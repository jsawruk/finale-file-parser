"""Read the style of each measure's right barline.

`measSpec.barline` names it outright in a `.musx` -- `normal`, `double` or
`final`, and nothing else in 21,855 corpus measures. Only the two that are not
ordinary are worth an element:

    double -> light-light      228 measures, 87 documents
    final  -> light-heavy      110 measures, 23 documents

A `.mus` keeps the same thing in the **high nibble of the flags byte at
`measSpec` +10**, whose low bits are the repeat flags `enigma.repeats` already
reads. Nibble 1 is an ordinary barline and 2 is a double bar: paired documents
agree on 3,960 ordinary measures and all 11 double bars, with no counterexample.

**A `.mus` never reports a final barline.** Nibble 3 would be the obvious
reading, and it does not occur once in 4,427 measures across 99 `.mus`
documents -- so there is nothing to check a guess against. Either no `.mus` here
carries a final bar, or it is not stored in this nibble at all, and the corpus
cannot say which. Guessing would put a double bar at the end of pieces that end
plainly. See `mus_document.UNTRANSLATED`.
"""

from __future__ import annotations

from finale_file_parser.enigma.document import EnigmaDocument

__all__ = ["BARLINE_STYLES", "barline_styles"]

_MEASURE = "measSpec"

BARLINE_STYLES = {"double": "light-light", "final": "light-heavy"}
"""Finale barline name -> MusicXML `bar-style`.

`normal` is deliberately absent: it is the default barline, and writing
`<bar-style>regular</bar-style>` on 21,517 measures says nothing.
"""


def barline_styles(document: EnigmaDocument) -> dict[int, str]:
    """MusicXML `bar-style` per measure, for the measures that need one."""
    out: dict[int, str] = {}
    for record in document.others.of_tag(_MEASURE):
        # Score records only: a part can override a barline, and honouring that
        # would give the score a double bar it does not have.
        if "part" in record.attrs:
            continue
        measure = _int(record.attrs.get("cmper"))
        name = record.fields.get("barline")
        if measure is None or not isinstance(name, str):
            continue
        style = BARLINE_STYLES.get(name)
        if style is not None:
            out[measure] = style
    return out


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
