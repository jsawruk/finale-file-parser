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

_STEPS = "CDEFGAB"


_ACCIDENTAL = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}


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


def musicxml(
    notes: list[tuple[str, int, int, tuple[str, ...]]], fifths: int, show_acc: bool = False
) -> str:
    """A one-measure part in the given key, one whole note per entry."""
    body = "".join(_note_xml(s, o, a, lab, show_acc) for s, o, a, lab in notes)
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


def engrave(
    notes: list[tuple[str, int, int, tuple[str, ...]]], fifths: int, show_acc: bool = False
) -> str:
    """Render `notes` to an inline SVG, or return "" if Verovio is not installed."""
    try:
        import verovio
    except ImportError:  # pragma: no cover - the document still builds without it
        return ""
    tk = verovio.toolkit()
    # Real margins matter: with them at zero Verovio crowds the clef against the
    # staff's left edge. adjustPage* then trims the page back to the content.
    tk.setOptions(
        {
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
        }
    )
    if not tk.loadData(musicxml(notes, fifths, show_acc)):
        return ""
    return tk.renderToSVG(1)
