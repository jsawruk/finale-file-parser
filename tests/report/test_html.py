"""Tests for the HTML report renderer."""

from __future__ import annotations

import json
import re

from defusedxml import ElementTree as DET

from finale_file_parser.report.html import render_html
from finale_file_parser.report.ladder import OK, Stage
from finale_file_parser.report.model import Inspection


def _inspection(**kwargs: object) -> Inspection:
    base = Inspection(file={"name": "score.mus", "size": "10", "sha256": "ab"})
    base.stages = [Stage("detect version", OK, {"family": "mus"})]
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_a_title_containing_a_script_tag_cannot_break_out() -> None:
    """Document text goes into the page and the input is untrusted by
    definition. `</script>` inside the embedded JSON would end the block."""
    hostile = '</script><script>alert("x")</script>'
    html = render_html(_inspection(score={"parts": [{"id": "P1", "name": hostile}]}))
    assert "</script><script>alert" not in html
    assert "\\u003c/script" in html


def test_the_report_embeds_its_data_as_json() -> None:
    html = render_html(_inspection(score={"totals": {"parts": 3}}))
    match = re.search(r'<script id="inspection" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    assert payload["score"]["totals"]["parts"] == 3


def test_the_report_is_well_formed_markup() -> None:
    """Not a strict HTML requirement, but it catches unbalanced tags cheaply.

    The doctype is stripped first: defusedxml refuses a DTD by design, which is
    the whole reason to use it here."""
    html = render_html(_inspection())
    DET.fromstring(html[html.index("<html") :])


def test_the_report_names_the_stage_that_failed() -> None:
    inspection = _inspection()
    inspection.stages = [
        Stage("detect version", OK, {"family": "mus"}),
        Stage("build score", "refused", error="entry 39 placed by more than one frame"),
    ]
    html = render_html(inspection)
    assert "entry 39 placed by more than one frame" in html
    assert "build score" in html


def test_the_report_has_no_external_assets() -> None:
    """No CDN, no framework, no build step."""
    html = render_html(_inspection())
    assert "http://" not in html and "https://" not in html


def test_a_cdata_terminator_in_document_text_does_not_break_xml() -> None:
    """`]]>` is XML's CDATA section end marker; outside a CDATA section it is
    illegal in character data. `json.dumps` emits it verbatim inside a string
    value, so the embedded JSON must escape it. Exercised via two different
    routes onto the page: a part name (through `_embed`'s JSON payload) and a
    stage error (through `_ladder`'s own `html.escape`, which already handles
    this correctly and must not regress)."""
    inspection = _inspection(score={"parts": [{"id": "P1", "name": "]]>hi"}]})
    inspection.stages = [
        Stage("detect version", OK, {"family": "mus"}),
        Stage("build score", "refused", error="broken at offset ]]>boom"),
    ]
    html = render_html(inspection)
    DET.fromstring(html[html.index("<html") :])


def test_a_fully_degenerate_inspection_still_renders_well_formed_markup() -> None:
    """The ladder can stop at its very first rung: no stages ran at all, and
    every depth -- score, document, records, raw -- is at its empty default.
    Report generation must never fail, and what it produces must still parse."""
    inspection = Inspection(file={"name": "score.mus", "size": "0", "sha256": ""})
    html = render_html(inspection)
    assert html
    DET.fromstring(html[html.index("<html") :])
