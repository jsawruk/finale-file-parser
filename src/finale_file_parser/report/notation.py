"""Engraving a `Score` as inline SVG, for the report's Music tab.

The report shows what the parser *found* -- a tree of parts, measures and
events. This shows what that means as notation, which is the form the question
"did this file read correctly?" is actually asked in. A wrong clef, a measure a
step sharp, or a rhythm that does not add up is visible in one glance at a
staff and invisible in a list of pitch names.

**Verovio does the engraving.** Writing a notation renderer is a project in
itself, and a rough one would answer the question badly: notation that is
subtly wrong because the *renderer* is wrong is worse than none, since a reader
cannot tell which half to distrust. The route is the one the library already
supports -- `Score` to MusicXML to Verovio -- so nothing is reimplemented here
either.

The SVG is self-contained: Verovio draws every glyph as a path and references
no external font, image or stylesheet, which is what lets the report stay one
file that works offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.ir import Score

__all__ = ["MAX_NOTATION_BYTES", "Engraving", "engrave"]

MAX_NOTATION_BYTES = 2 * 1024 * 1024
"""How much SVG one report will carry.

A page is 208 KB at the corpus median, so most documents fit whole. The largest
run to 5.2 MB across twenty pages, which would make the report bigger than
every other part of it put together for a diagnostic nobody reads to the end.
Pages are taken in order until the next one would cross this, and the count of
what was left out is reported rather than dropped silently.
"""

_OPTIONS = {
    "scale": 40,
    "adjustPageHeight": True,
    "header": "none",
    "footer": "none",
    "svgViewBox": True,
    "svgRemoveXlink": True,
    # Verovio's default seed of 0 means "pick one at random", so the same
    # document would render with different element ids every time and two
    # reports of one file would differ for no reason. Any fixed non-zero seed
    # makes a report reproducible.
    "xmlIdSeed": 1,
}


@dataclass
class Engraving:
    """The engraved pages, and what was left out."""

    pages: list[str] = field(default_factory=list)
    total: int = 0
    """How many pages Verovio laid out, whether or not they are all here."""

    @property
    def omitted(self) -> int:
        return max(0, self.total - len(self.pages))


def engrave(score: Score, limit: int = MAX_NOTATION_BYTES) -> Engraving:
    """`score` as inline SVG pages, bounded by `limit` bytes.

    Raises `ImportError` if Verovio is not installed, and whatever Verovio
    raises on input it cannot lay out. Both are the caller's to catch -- in the
    report this runs as a ladder stage, so a failure becomes a recorded stage
    and never stops the rest of the page being written.
    """
    import verovio

    toolkit = verovio.toolkit()
    toolkit.setOptions(_OPTIONS)
    xml = to_musicxml(score)
    if not toolkit.loadData(xml if isinstance(xml, str) else xml.decode("utf-8")):
        # Verovio reports failure by return value rather than by raising, and a
        # page rendered from data it rejected would be a blank staff presented
        # as this document's music.
        raise ValueError("Verovio could not lay out this score")

    out = Engraving(total=toolkit.getPageCount())
    budget = limit
    for number in range(1, out.total + 1):
        page = toolkit.renderToSVG(number)
        if len(page) > budget and out.pages:
            break
        budget -= len(page)
        out.pages.append(page)
    return out
