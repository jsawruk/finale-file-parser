"""Engraving a score for the report's Music tab."""

from __future__ import annotations

import re
from fractions import Fraction

import pytest

from finale_file_parser.ir import Event, Measure, Part, Pitch, Score, TimeSignature, Voice
from finale_file_parser.report.notation import MAX_NOTATION_BYTES, Engraving, engrave


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
    return Score(
        parts=(
            Part(id="P1", name="Flute", measures=tuple(_measure(n + 1) for n in range(measures))),
        )
    )


def test_a_score_engraves_to_inline_svg() -> None:
    engraving = engrave(_score())
    assert engraving.pages, "a score with notes must produce at least one page"
    assert engraving.pages[0].lstrip().startswith("<svg")
    assert engraving.total >= 1
    assert engraving.omitted == 0


def test_the_svg_is_self_contained() -> None:
    """The report is one file that works offline. An SVG referencing a font or
    an image would break that quietly -- it renders on the machine that made it
    and shows empty boxes anywhere else."""
    page = engrave(_score()).pages[0]
    assert "<?xml" not in page, "an XML declaration mid-document would not parse"

    # Namespace declarations are URIs and fetch nothing, so they are removed
    # before looking for a real reference. Checking for "http" without this
    # finds `xmlns="http://www.w3.org/2000/svg"` on every SVG ever written.
    body = re.sub(r'xmlns(:\w+)?="[^"]*"', "", page)
    for external in ("http://", "https://", "url(", "<image", "@font-face"):
        assert external not in body, f"the SVG reaches outside itself via {external}"


def test_pages_stop_at_the_budget_and_say_how_many_were_left() -> None:
    """The largest corpus scores reach 5.2 MB across twenty pages. Silently
    truncating would read as "this is the whole score"."""
    long_score = _score(measures=200)
    full = engrave(long_score)
    if full.total < 2:  # pragma: no cover - depends on Verovio's page breaking
        pytest.skip("this score lays out on one page, so there is no budget to test")

    bounded = engrave(long_score, limit=1)
    assert len(bounded.pages) == 1, "the first page is kept even when it exceeds the budget"
    assert bounded.total == full.total
    assert bounded.omitted == full.total - 1


def test_data_verovio_rejects_raises_rather_than_returning_a_blank_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verovio reports failure by return value, not by raising, so a caller that
    ignores it renders a blank staff and presents it as this document's music.

    Driven by forcing the rejection rather than by finding a score that causes
    one: an empty score does not, Verovio lays it out as an empty page quite
    happily, and a guard only reached by malformed input still has to be known
    to work.
    """
    import verovio

    class _Rejecting(verovio.toolkit):
        def loadData(self, _data: str) -> bool:  # noqa: N802 - Verovio's own name
            return False

    monkeypatch.setattr(verovio, "toolkit", _Rejecting)
    with pytest.raises(ValueError, match="could not lay out"):
        engrave(_score())


def test_an_engraving_with_no_pages_reports_nothing_omitted() -> None:
    assert Engraving().omitted == 0
    assert Engraving(pages=["<svg/>"], total=1).omitted == 0


def test_the_budget_is_stated_in_bytes() -> None:
    assert MAX_NOTATION_BYTES == 2 * 1024 * 1024
