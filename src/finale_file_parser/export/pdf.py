"""Write a `Score` as a printable PDF.

**Verovio cannot write PDF.** Its toolkit renders SVG, MIDI, PAE and a timemap,
and nothing else, so a page goes `Score` -> MusicXML -> SVG -> PDF. Only the
last step is new here: the first two are the same functions the inspection
report's Music tab uses, so the notation in a PDF is the notation the report
shows, not a second engraving that could disagree with it.

**Why svglib and not a smaller converter.** The obvious shortcut is to write
the PDF directly, since Verovio's SVG is self-contained. It is self-contained
but it is not simple: one page of a corpus score carries 70 `<use>` elements
resolving into `<defs>`, `<text>` with a `font-family`, a `<style>` block and
eight `<ellipse>`s. Converting that faithfully means implementing `use`
resolution, CSS and font embedding -- an SVG renderer, not a helper. The
alternatives were measured rather than assumed: CairoSVG and WeasyPrint both
fail to import without system libraries a wheel cannot supply.

**Why the report's engraving options are not reused.** The report sets
`adjustPageHeight`, which crops each page to its content -- a one-system score
comes out 8.8 x 3.0 inches. That is right for a web page that scrolls and wrong
for paper. Printing sets a real page size instead, which also makes every page
share one viewBox, so a three-page score prints at one scale rather than three.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from finale_file_parser.export.musicxml import ExportError, to_musicxml
from finale_file_parser.ir import Score

if TYPE_CHECKING:
    from collections.abc import Callable

    RenderPages = Callable[[list[str], float, float], bytes]
    """Draw engraved pages onto a PDF of the given point size."""

__all__ = ["DEFAULT_PAGE_SIZE", "PAGE_SIZES", "SCALE", "to_pdf"]

PAGE_SIZES: dict[str, tuple[int, int]] = {
    "letter": (2159, 2794),
    "a4": (2100, 2970),
}
"""Paper sizes, in **tenths of a millimetre** -- Verovio's page unit.

US Letter is 215.9 x 279.4 mm and A4 is 210 x 297 mm. Verified rather than
assumed: at these values the rendered viewBox comes back at each paper's own
aspect ratio, and passing hundredths instead silently fits a whole score onto
one page because the music then occupies a hundredth of the sheet.
"""

DEFAULT_PAGE_SIZE = "letter"

SCALE = 40
"""Verovio's zoom, as a percentage.

The same value the inspection report uses, so a printed page and the report's
Music tab show the music at the same size. It is what decides how many systems
fit on a sheet.
"""

_MM_PER_INCH = 25.4
_POINTS_PER_INCH = 72.0


def _points(tenths_of_mm: int) -> float:
    """A Verovio page dimension as PDF points, which are 1/72 inch."""
    return tenths_of_mm / 10.0 / _MM_PER_INCH * _POINTS_PER_INCH


def _options(width: int, height: int) -> dict[str, object]:
    return {
        "scale": SCALE,
        # The difference from the report, and the reason this module does not
        # call `report.notation`: a fixed page rather than one cropped to its
        # content.
        "adjustPageHeight": False,
        "pageWidth": width,
        "pageHeight": height,
        "svgViewBox": True,
        "svgRemoveXlink": True,
        # Verovio's default footer prints "engraved with Verovio" on every
        # page. The report suppresses it and so does this: what a user prints
        # is their score, not an advertisement for the tool that set it. The
        # *header* is left at its default, unlike the report's, because it is
        # what numbers the pages -- a multi-page printout wants that and a
        # scrolling web page does not.
        "footer": "none",
        # A fixed seed for the same reason the report fixes one: Verovio's
        # default of 0 means "choose at random", so two PDFs of one score would
        # differ byte for byte with no musical difference between them.
        "xmlIdSeed": 1,
    }


def to_pdf(score: Score, *, page_size: str = DEFAULT_PAGE_SIZE) -> bytes:
    """Render `score` as a multi-page PDF, one PDF page per engraved page.

    Args:
        score: the score to engrave.
        page_size: a key of `PAGE_SIZES`.

    Raises:
        ExportError: the `pdf` extra is not installed, `page_size` is not a
            known paper size, the score has no music to engrave, or Verovio
            rejects the MusicXML.
    """
    if page_size not in PAGE_SIZES:
        known = ", ".join(sorted(PAGE_SIZES))
        raise ExportError(f"unknown page size {page_size!r}; available sizes are {known}")

    if not any(part.measures for part in score.parts):
        # Verovio lays out a blank sheet for a score with nothing in it, and a
        # blank PDF is a lie that opens cleanly: it is the right size, it has
        # the right page count, and it reports no error. Refuse it here, where
        # the reason is still known.
        raise ExportError("this score has no measures, so there is no music to engrave")

    renderer = _renderer()
    pages = _engrave_pages(score, PAGE_SIZES[page_size])
    if not pages:
        raise ExportError("the score engraves to no pages, so there is nothing to write")

    width, height = (_points(v) for v in PAGE_SIZES[page_size])
    return renderer(pages, width, height)


def _renderer() -> RenderPages:
    """The SVG-to-PDF step, imported on demand.

    The extra is optional, so its absence is an ordinary, explainable outcome
    rather than a crash: it names the thing to install, not the module that was
    missing, because the module name is not what a reader has to act on.
    """
    try:
        from reportlab.graphics import renderPDF
        from reportlab.pdfgen.canvas import Canvas
        from svglib.svglib import svg2rlg
    except ImportError as error:
        raise ExportError(
            "writing PDF needs the optional 'pdf' extra: "
            "install finale-file-parser[pdf] (it adds svglib and reportlab)"
        ) from error

    def render(pages: list[str], width: float, height: float) -> bytes:
        buffer = io.BytesIO()
        canvas = Canvas(buffer, pagesize=(width, height))
        for page in pages:
            drawing = svg2rlg(io.StringIO(page))
            if drawing is None:
                raise ExportError("the engraved page could not be converted to PDF")
            # Every page shares one viewBox, because the page size is fixed
            # above, so this factor is the same on each -- which is what keeps
            # a multi-page score at a single scale.
            if drawing.width:
                factor = width / drawing.width
                drawing.scale(factor, factor)
                drawing.width, drawing.height = width, height
            renderPDF.draw(drawing, canvas, 0, 0)
            canvas.showPage()
        canvas.save()
        return buffer.getvalue()

    return render


def _engrave_pages(score: Score, page: tuple[int, int]) -> list[str]:
    """Every page Verovio lays out, as SVG.

    Unlike the report's engraving there is no byte budget here. The report
    embeds its SVG in a single HTML file a browser has to hold; a PDF is
    written to disk, and truncating a printed score would lose music without
    the page saying so.
    """
    import verovio

    toolkit = verovio.toolkit()
    toolkit.setOptions(_options(*page))
    xml = to_musicxml(score)
    if not toolkit.loadData(xml if isinstance(xml, str) else xml.decode("utf-8")):
        # Verovio reports refusal by return value rather than by raising, and a
        # PDF built from data it rejected would be blank staves presented as
        # this score's music.
        raise ExportError("the engraver rejected this score's MusicXML")
    return [toolkit.renderToSVG(number) for number in range(1, toolkit.getPageCount() + 1)]
