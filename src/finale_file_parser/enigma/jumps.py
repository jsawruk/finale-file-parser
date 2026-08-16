"""Resolve a document's text repeats: "Fine", "D.C. al Coda" and their kin.

Three records, one of which is a trap:

    textRepeatAssign(measure)  -- a marking is placed here, naming a definition
    textRepeatDef(repnum)      -- how it is drawn
    textRepeatText(repnum)     -- what it says

**`textRepeatText` is a palette, not a list of what the score uses.** Every one
of the 401 corpus documents carries the same nine or so definitions -- "D.C. al
Fine", "D.S. al Coda", "Fine", "To Coda #" -- whether or not it uses any of
them, roughly 400 occurrences each. Reading the palette would put a D.S. in
every score in the corpus. Only an **assignment** puts a marking in the music,
and there are 17 of those, across 10 documents.

`repnum` names the definition, confirmed by what comes back: measure 5 of one
score resolves to "Fine" and measure 10 of another to "D.C. al Coda", which is
not what a wrong link produces. Five of the 17 name a `textRepeatDef` that
exists while its `textRepeatText` does not, so the file simply does not carry
their words.

## What this does not do, and why

**No playback semantics.** `action` is `stop`, `jumpAbsolute` or `noJump`, and
`target` gives a measure -- enough to guess at MusicXML's `<sound dacapo>`,
`<sound dalsegno>` and `<sound fine>`. The corpus holds one or two distinct
situations per action value, and a wrong guess sends a player to the wrong bar,
which is worse than a marking that only prints. The words are emitted; the
jump is not.

**No segno or coda signs.** Some markings are a single music-font character --
`%` for the segno -- rather than words, and printing that literally would put a
percent sign in the score. MusicXML has `<segno/>` and `<coda/>` for them, but
identifying the glyph needs the font, and the definitions carrying one have **no
`fontID` at all**. The same blocker as fingerings.

**`.musx` only.** Exactly one paired document carries a text repeat, with two
assignments, which is far too little to identify the `.mus` tag: a key set that
small matches several tags by chance. A `.mus` therefore exports no markings,
which is a gap rather than a disagreement -- see `mus_document.UNTRANSLATED`.
"""

from __future__ import annotations

from finale_file_parser.enigma.document import EnigmaDocument, field_int
from finale_file_parser.enigma.text import plain_text

__all__ = ["jumps_by_measure"]

_ASSIGN = "textRepeatAssign"
_TEXT = "textRepeatText"

_MAX_GLYPH = 2
"""A marking this short and not alphanumeric is a music-font character rather
than words -- `%` for the segno. See the module docstring."""


def jumps_by_measure(document: EnigmaDocument) -> dict[int, tuple[str, ...]]:
    """The words each measure carries, keyed by measure number.

    A measure can hold more than one, and order follows the document.
    """
    words = _definitions(document)
    out: dict[int, list[str]] = {}
    for record in document.others.of_tag(_ASSIGN):
        if "part" in record.attrs:
            continue
        measure = field_int(record.attrs.get("cmper"))
        repnum = field_int(record.fields.get("repnum"))
        if measure is None or repnum is None:
            continue
        text = words.get(repnum)
        if text:
            out.setdefault(measure, []).append(text)
    return {measure: tuple(items) for measure, items in out.items()}


def _definitions(document: EnigmaDocument) -> dict[int, str]:
    """repnum -> its words, skipping the ones that are a font glyph."""
    out: dict[int, str] = {}
    for record in document.others.of_tag(_TEXT):
        if "part" in record.attrs:
            continue
        cmper = field_int(record.attrs.get("cmper"))
        raw = record.fields.get("rptText")
        if cmper is None or not isinstance(raw, str):
            continue
        text = plain_text(raw).strip()
        if text and not _is_glyph(text):
            out[cmper] = text
    return out


def _is_glyph(text: str) -> bool:
    return len(text) <= _MAX_GLYPH and not any(character.isalnum() for character in text)
