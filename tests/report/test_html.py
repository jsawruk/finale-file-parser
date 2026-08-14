"""Tests for the HTML report renderer."""

from __future__ import annotations

import json
import re

from defusedxml import ElementTree as DET

from finale_file_parser.report.html import render_html
from finale_file_parser.report.ladder import OK, Stage
from finale_file_parser.report.model import Inspection, encode_raw


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
        Stage(
            "build score", "refused", error="entry 39 placed twice at staff 3 measure 12 layer 1"
        ),
    ]
    html = render_html(inspection)
    assert "entry 39 placed twice at staff 3 measure 12 layer 1" in html
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


def test_the_bytes_pane_can_reach_every_byte_of_a_pool() -> None:
    """The whole pool is embedded -- 269 KB of `others` in one corpus document
    -- but the pane used to render its first 4096 bytes and say nothing about
    the remaining 98%. The hex window is still one page; the page now moves, and
    names where in the pool it is."""
    pool = bytes(range(256)) * 40  # 10,240 bytes: more than two 4 KB pages
    html = render_html(_inspection(raw={"others": encode_raw(pool)}))
    script = html[html.index("//<![CDATA[") :]

    assert "Math.min(bin.length, 4096)" not in script, "the silent 4 KB cut is back"
    assert "PAGE_BYTES = 4096" in script
    assert "'previous'" in script and "'next'" in script
    assert "'bytes ' + group(start)" in script
    assert "' of ' + group(bin.length)" in script
    # Base64 carries none of `<`, `>` or `&`, so `_embed` leaves it untouched:
    # the page holds the entire pool, not only the bytes first shown.
    assert encode_raw(pool) in html
    DET.fromstring(html[html.index("<html") :])


def test_a_filename_that_is_not_valid_utf8_can_still_be_written_out() -> None:
    """POSIX permits any byte but NUL and `/` in a filename, so `os.fsdecode`
    hands back a lone surrogate for an invalid UTF-8 one. It reaches the title
    and the heading as raw text -- `html.escape` does not touch it, and unlike
    the JSON island it is not `ensure_ascii`-escaped either -- and a page holding
    a lone surrogate cannot be encoded as UTF-8 at all."""
    inspection = _inspection(file={"name": "bad\udcff.mus", "size": "1", "sha256": "ab"})
    html = render_html(inspection)
    html.encode("utf-8")  # UnicodeEncodeError before the surrogate was replaced
    DET.fromstring(html[html.index("<html") :])
    assert "\udcff" not in html


def test_control_characters_on_the_page_keep_it_well_formed() -> None:
    """XML 1.0 forbids a C0 control in character data even as a character
    reference, and `html.escape` does not strip one. macOS accepts such a
    filename, so this is not hypothetical -- and the three routes onto the page
    that carry text from outside are all covered: the file name, a stage error,
    and a note."""
    inspection = _inspection(file={"name": "ctl\x01x.mus", "size": "1", "sha256": "ab"})
    inspection.stages = [Stage("build score", "refused", error="bad byte \x02 here")]
    inspection.notes = ["dropped \x1f something"]
    html = render_html(inspection)
    DET.fromstring(html[html.index("<html") :])
    assert "\x01" not in html and "\x02" not in html and "\x1f" not in html


def test_a_fully_degenerate_inspection_still_renders_well_formed_markup() -> None:
    """The ladder can stop at its very first rung: no stages ran at all, and
    every depth -- score, document, records, raw -- is at its empty default.
    Report generation must never fail, and what it produces must still parse."""
    inspection = Inspection(file={"name": "score.mus", "size": "0", "sha256": ""})
    html = render_html(inspection)
    assert html
    DET.fromstring(html[html.index("<html") :])


def test_the_records_pane_is_a_tree_not_a_wall_of_json() -> None:
    """A 979 KB report rendered as one `<pre>` of JSON is technically complete
    and practically unreadable. Pools, tags and records nest, so a reader opens
    what they want rather than scrolling past everything they do not."""
    records = {"details": {"gfhold": [{"key": "3/12", "fields": {"frame1": "11"}, "length": None}]}}
    html = render_html(_inspection(records=records))
    assert "JSON.stringify(data.records" not in html, "the flat dump is gone"
    assert "function tree(" in html, "and a nesting renderer replaced it"


def test_the_music_pane_exists_beside_the_storage_one() -> None:
    """The file has two hierarchies and they are different shapes: pool ->
    record -> field is what is stored, staff -> measure -> layer -> event is
    what it means. The report shows both rather than making one stand in."""
    html = render_html(_inspection())
    panes = re.findall(r'data-pane="(\w+)"', html)
    assert panes == ["score", "music", "document", "records", "bytes"]
    assert '<section id="music">' in html


def test_the_music_pane_says_so_when_no_score_was_built() -> None:
    """`music` is None whenever the ladder stopped before `build score`, and the
    pane must explain that rather than render an empty tree that reads like a
    document with no notes in it."""
    html = render_html(_inspection(music=None))
    assert "stopped before a score was built" in html


def test_a_hostile_field_name_cannot_break_out_of_the_tree() -> None:
    """The tree is built from DOM nodes with textContent, not innerHTML, so a
    record whose field name came out of a hostile file is inert."""
    hostile = "<img src=x onerror=alert(1)>"
    records = {"others": {"x": [{"key": "1", "fields": {hostile: hostile}, "length": None}]}}
    html = render_html(_inspection(records=records))
    assert "<img src=x" not in html, "escaped inside the JSON island"
    assert "innerHTML = '<pre>'" not in html
