"""Engrave the pitch examples with Verovio.

The staff diagrams these produce are the one place in this document where a
picture beats a table: a harmonic value means a different pitch in every key,
and that is easier shown than described.

Verovio is a build-time tool, like the browser that prints the PDF. It is not a
dependency of the parser, and nothing it produces is linked into the library --
its output here is an SVG of our own notes, engraved. If it is absent the
document still builds; the examples are simply omitted.
"""

from __future__ import annotations

import re

_STEPS = "CDEFGAB"

# Real margins matter: at zero Verovio crowds the clef against the staff's
# left edge. adjustPage* then trims the page back to the content anyway.
_OPTIONS = {
    "scale": 30,
    "adjustPageHeight": True,
    "adjustPageWidth": True,
    "header": "none",
    "footer": "none",
    "breaks": "none",
    "pageMarginTop": 25,
    "pageMarginBottom": 25,
    "pageMarginLeft": 25,
    "pageMarginRight": 25,
    "svgViewBox": True,
    "svgRemoveXlink": True,
    # Verovio's default seed of 0 means "pick one at random", so every build
    # renames every SVG element and the committed document differs from itself.
    # Any fixed non-zero seed makes the build reproducible, so a rebuild shows a
    # diff only where the content actually changed.
    "xmlIdSeed": 1,
}


_ACCIDENTAL = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}


def grand_staff(fifths: int = 0) -> str:
    """The full diatonic octave either side of the tonic, on a grand staff.

    Ascending 0..10 on the treble and descending 0..-10 on the bass, both from
    the same note: the tonic in the octave from middle C. The two directions
    leaving one pitch is the point, and running past 7 shows that nothing
    special happens at the octave -- the count simply continues.
    """

    def _row(h: int, staff: int) -> str:
        step, octave = _pitch_of(h)
        lyr = f'<lyric number="1"><syllabic>single</syllabic><text>{h}</text></lyric>'
        return (
            f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
            f"<duration>2</duration><type>half</type><staff>{staff}</staff>"
            f"<voice>{staff}</voice>{lyr}</note>"
        )

    treble = "".join(_row(h, 1) for h in range(0, 11))
    bass = "".join(_row(h, 2) for h in range(0, -11, -1))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name/></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><divisions>2</divisions>'
        f"<staves>2</staves><key><fifths>{fifths}</fifths></key>"
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        f"{treble}<backup><duration>22</duration></backup>{bass}"
        "</measure></part></score-partwise>"
    )


def _pitch_of(h: int, tonic: str = "C", octave: int = 4) -> tuple[str, int]:
    """Step name and octave for harmonic value `h`, tonic in the middle-C octave."""
    i = _STEPS.index(tonic) + h
    return _STEPS[i % 7], octave + i // 7


def _note_xml(
    step: str, octave: int, alter: int, labels: tuple[str, ...], show_acc: bool = False
) -> str:
    """One whole note. `show_acc` forces the accidental to be printed even where
    the key already implies it -- the alteration examples turn on seeing it."""
    acc = f"<alter>{alter}</alter>" if alter else ""
    shown = f"<accidental>{_ACCIDENTAL[alter]}</accidental>" if show_acc else ""
    lyrics = "".join(
        f'<lyric number="{i + 1}"><syllabic>single</syllabic><text>{t}</text></lyric>'
        for i, t in enumerate(labels)
        if t
    )
    return (
        "<note><pitch>"
        f"<step>{step}</step>{acc}<octave>{octave}</octave>"
        "</pitch><duration>4</duration><type>whole</type>"
        f"{shown}{lyrics}</note>"
    )


_FIGURE_SPACE = "\u2007"
"""A space the width of a digit, so padding lines up under a centred number."""


def _align(labels: tuple[str, ...]) -> tuple[str, ...]:
    """Pad a note's labels to equal width, left, with digit-width spaces.

    Verovio centres each label under its note, so a wider string is centred over
    a narrower one and their digits come apart: over a bare 0, a -1 puts its 1 to
    the right of the 0 below. Padding the shorter to the same width first means
    the two centre identically.
    """
    if len(labels) < 2:
        return labels
    plain = [lab.replace("&#8722;", "-") for lab in labels]
    width = max(len(t) for t in plain)
    return tuple(
        _FIGURE_SPACE * (width - len(t)) + lab for lab, t in zip(labels, plain, strict=True)
    )


def musicxml(
    notes: list[tuple[str, int, int, tuple[str, ...]]], fifths: int, show_acc: bool = False
) -> str:
    """A one-measure part in the given key, one whole note per entry."""
    body = "".join(_note_xml(s, o, a, _align(lab), show_acc) for s, o, a, lab in notes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"'
        ' "http://www.musicxml.org/dtds/4.0/partwise.dtd">'
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name/></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><divisions>4</divisions>'
        f"<key><fifths>{fifths}</fifths></key>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        f"{body}</measure></part></score-partwise>"
    )


def engrave_xml(xml: str) -> str:
    """Render prepared MusicXML, or "" when Verovio is absent."""
    try:
        import verovio
    except ImportError:  # pragma: no cover
        return ""
    tk = verovio.toolkit()
    tk.setOptions(_OPTIONS)
    if not tk.loadData(xml):
        return ""
    return _restyle(tk.renderToSVG(1))


def engrave(
    notes: list[tuple[str, int, int, tuple[str, ...]]], fifths: int, show_acc: bool = False
) -> str:
    """Render `notes` to an inline SVG, or return "" if Verovio is not installed."""
    try:
        import verovio
    except ImportError:  # pragma: no cover - the document still builds without it
        return ""
    tk = verovio.toolkit()
    tk.setOptions(_OPTIONS)
    if not tk.loadData(musicxml(notes, fifths, show_acc)):
        return ""
    return _restyle(tk.renderToSVG(1))


_LYRIC_STYLE = (
    "<style>.syl text, .syl tspan {"
    " font-family: Charter, Georgia, 'Times New Roman', serif;"
    " font-size: 265px; }</style>"
)

_LYRIC_NUDGE = 105
"""Internal units to shift a lyric right, to centre it under the notehead.

Verovio sets a syllable from the note's left edge, which is where a word of
lyrics belongs. A bare number reads as belonging to the note above it, so it
wants the notehead's centre instead -- about half a notehead across.
"""


def _restyle(svg: str) -> str:
    """Set the lyric numbers in the document's own face, at a chosen size.

    Verovio engraves lyrics in its text font at staff scale, which lands far
    larger than the body text and cannot be brought down past its lyricSize
    floor. Its *positioning* is right, though -- each number centred under its
    note -- so the numbers stay where Verovio put them and only their typography
    is overridden, by a stylesheet inside the SVG.
    """

    def _shift(match: re.Match[str]) -> str:
        return f'{match.group(1)}{float(match.group(2)) + _LYRIC_NUDGE:.0f}"'

    svg = re.sub(r'(<g[^>]*class="syl"[^>]*>\s*<text x=")([\d.]+)"', _shift, svg)
    at = svg.find(">", svg.find("<svg"))
    if at < 0:
        return svg
    return svg[: at + 1] + _LYRIC_STYLE + svg[at + 1 :]
