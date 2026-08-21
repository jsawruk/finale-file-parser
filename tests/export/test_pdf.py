"""Writing a score as a PDF.

Verovio cannot write PDF, so a page goes score -> MusicXML -> SVG -> PDF. These
tests pin the two things that route can get quietly wrong: pages that are not
the paper size they claim, and pages that are blank because the SVG's glyphs
did not survive the conversion. A blank page is the dangerous failure -- it is
a valid PDF of the right size with nothing on it, and every other assertion
passes.
"""

from __future__ import annotations

import base64
import re
import zlib
from fractions import Fraction

import pytest

from finale_file_parser.export.musicxml import ExportError
from finale_file_parser.export.pdf import PAGE_SIZES, _engrave_pages, to_pdf
from finale_file_parser.ir import Event, Measure, Part, Pitch, Score, TimeSignature, Voice

POINTS_PER_INCH = 72
LETTER_POINTS = (8.5 * POINTS_PER_INCH, 11 * POINTS_PER_INCH)
A4_POINTS = (210 / 25.4 * POINTS_PER_INCH, 297 / 25.4 * POINTS_PER_INCH)


def _measure(number: int) -> Measure:
    event = Event(
        duration=Fraction(1, 4),
        written_duration=Fraction(1, 4),
        pitches=(Pitch("C", 4, 0),),
    )
    return Measure(
        number=number,
        voices=(Voice(number=1, events=(event,) * 4),),
        time=TimeSignature(beats=4, beat_type=4) if number == 1 else None,
        clef_sign="G" if number == 1 else None,
    )


def _score(measures: int = 1) -> Score:
    """`measures` is always a constant at the call site: a count taken from a
    file would be an allocation sized by the file, which this project treats as
    a defect."""
    return Score(
        parts=(
            Part(id="P1", name="Flute", measures=tuple(_measure(n + 1) for n in range(measures))),
        )
    )


def _page_count(pdf: bytes) -> int:
    """Page objects, not the page *tree* node -- `/Type /Pages` would match a
    naive search for `/Type /Page` and inflate every count by one."""
    return len(re.findall(rb"/Type\s*/Page(?![s])", pdf))


def _media_boxes(pdf: bytes) -> list[tuple[float, float]]:
    out = []
    for box in re.findall(rb"/MediaBox\s*\[([^\]]*)\]", pdf):
        x0, y0, x1, y1 = (float(v) for v in box.split())
        out.append((round(x1 - x0, 1), round(y1 - y0, 1)))
    return out


def _drawing_operators(pdf: bytes) -> int:
    """How many path-painting operators the content streams hold.

    A page that rendered nothing still has a content stream -- it just has no
    `f`, `S` or `B` in it, which is what distinguishes a blank page from a
    drawn one.

    ReportLab's default filter chain is ASCII85 *then* Flate, so both come off
    before the operators are visible. Inflating alone finds nothing and would
    make this test report zero for every page, blank or not.
    """
    total = 0
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        body = stream.strip(b"\r\n")
        try:
            body = base64.a85decode(body, adobe=True)
        except ValueError:
            pass
        try:
            body = zlib.decompress(body)
        except zlib.error:
            pass
        total += len(re.findall(rb"(?:^|\s)(?:f|f\*|S|s|B|B\*|b)(?=\s|$)", body))
    return total


def test_a_score_becomes_a_pdf() -> None:
    pdf = to_pdf(_score())
    assert pdf.startswith(b"%PDF-"), "not a PDF at all"
    assert _page_count(pdf) == 1


def test_the_page_is_us_letter_by_default() -> None:
    """The report engraves with `adjustPageHeight`, which crops each page to its
    content -- one corpus score comes out 8.8 x 3.0 inches, a strip rather than
    a page. A PDF is for printing, so it gets a real paper size."""
    boxes = _media_boxes(to_pdf(_score()))
    assert boxes, "no MediaBox: the page has no declared size"
    width, height = boxes[0]
    assert (width, height) == pytest.approx(LETTER_POINTS, abs=1.0)


def test_a4_is_available_and_is_a_different_size() -> None:
    width, height = _media_boxes(to_pdf(_score(), page_size="a4"))[0]
    assert (width, height) == pytest.approx(A4_POINTS, abs=1.0)


def test_an_unknown_paper_size_is_refused_by_name() -> None:
    with pytest.raises(ExportError) as caught:
        to_pdf(_score(), page_size="foolscap")
    assert "foolscap" in str(caught.value)
    assert all(name in str(caught.value) for name in PAGE_SIZES), "does not say what is available"


def test_the_music_reaches_the_page() -> None:
    """The failure this guards is a valid, correctly sized, empty PDF. Verovio
    draws its glyphs as `<use>` references into `<defs>`, and a converter that
    silently drops them produces exactly that -- and nothing else in this file
    would notice."""
    assert _drawing_operators(to_pdf(_score(measures=4))) > 20


def test_a_longer_score_draws_more_than_a_shorter_one() -> None:
    """Pins the previous test to the *score* rather than to page furniture: if
    both counts came from the frame around the music, they would be equal."""
    assert _drawing_operators(to_pdf(_score(measures=8))) > _drawing_operators(
        to_pdf(_score(measures=1))
    )


def test_every_page_lands_in_one_document() -> None:
    """Verovio paginates, and the pages must arrive as one file. Writing a PDF
    per page would be a different feature and a worse one."""
    pdf = to_pdf(_score(measures=240))
    assert _page_count(pdf) > 1, "240 measures should not fit on a single page"
    assert len(set(_media_boxes(pdf))) == 1, "pages differ in size, so the music differs in scale"


def test_a_score_with_no_music_is_refused_rather_than_written_blank() -> None:
    """An empty PDF is a lie that opens cleanly."""
    with pytest.raises(ExportError):
        to_pdf(Score(parts=()))


def test_without_the_extra_it_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `pdf` extra is installed for development, so the only way to see what
    a user without it sees is to hide the import."""
    import builtins

    real_import = builtins.__import__

    def refuse(name: str, *args: object, **kwargs: object) -> object:
        if name.split(".")[0] in {"svglib", "reportlab"}:
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(ExportError) as caught:
        to_pdf(_score())
    message = str(caught.value)
    assert "finale-file-parser[pdf]" in message, "does not say how to fix it"
    assert "svglib" not in message.split("finale-file-parser[pdf]")[0], (
        "leads with the internal module name rather than the thing to install"
    )


def test_the_printed_page_carries_no_engraver_branding() -> None:
    """Verovio's default footer prints "engraved with Verovio" on every page.
    What a user prints is their score, not an advertisement for the tool that
    set it -- and the inspection report already suppresses the same footer.

    **Searching the page for the word "Verovio" does not test this**, at either
    the SVG or the PDF layer, and the obvious version of this test passed with
    the suppression deleted. Two reasons: the engraver draws the footer as glyph
    outlines rather than as text, so the word is never in the PDF's content
    stream either way; and the word *is* in every SVG regardless, because the
    `<desc>` metadata names the engraver whether or not a footer is drawn.

    What actually distinguishes the two is the `pgFoot` element, and dropping
    the footer halves the page: 34,780 bytes of SVG against 15,961.
    """
    page = _engrave_pages(_score(measures=4), PAGE_SIZES["letter"])[0]
    assert "pgFoot" not in page, "the engraver's footer is being printed"
