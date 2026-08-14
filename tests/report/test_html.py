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
    html = render_html(_inspection(stats={"parts": [{"id": "P1", "name": hostile}]}))
    assert "</script><script>alert" not in html
    assert "\\u003c/script" in html


def test_the_report_embeds_its_data_as_json() -> None:
    html = render_html(_inspection(stats={"totals": {"parts": 3}}))
    match = re.search(r'<script id="inspection" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    assert payload["stats"]["totals"]["parts"] == 3


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
    inspection = _inspection(stats={"parts": [{"id": "P1", "name": "]]>hi"}]})
    inspection.stages = [
        Stage("detect version", OK, {"family": "mus"}),
        Stage("build score", "refused", error="broken at offset ]]>boom"),
    ]
    html = render_html(inspection)
    DET.fromstring(html[html.index("<html") :])


def test_there_is_no_byte_pane_and_no_raw_payload() -> None:
    """The pool hex viewer is gone, and so is the `raw` payload behind it.

    Measured before removing it, across all 639 corpus documents: there is not
    one where the byte pane is the only content. All 7 documents that fail still
    carry a records tree, 401 `.musx` documents never had a byte pane at all,
    and for a `.mus` the same bytes are already in the records tree attached to
    the record they belong to -- which the undifferentiated pool dump could not
    tell you. Dropping it took 33% off one report's payload.

    Pinned so the pane cannot come back without that evidence being revisited.
    """
    html = render_html(_inspection())
    assert "hexDump" not in html and "bytePool" not in html
    assert '"raw"' not in html, "the payload no longer carries undecoded pools"


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
    assert panes == ["music", "records", "debug"]
    assert '<section id="music">' in html


def test_the_music_pane_says_so_when_no_score_was_built() -> None:
    """`music` is None whenever the ladder stopped before `build score`.

    The ladder used to sit above every pane, so an empty pane explained itself.
    It is behind the Debug tab now, so a pane with nothing to show has to name
    the stage that stopped and point at where the detail lives -- otherwise a
    file that failed to parse opens on a blank Music tab and reads like a
    document with no notes in it.
    """
    html = render_html(_inspection(music=None))
    assert "See the Debug tab for the full ladder" in html, "and says where to look"
    assert "function stopped(" in html


def test_a_hostile_field_name_cannot_break_out_of_the_tree() -> None:
    """The tree is built from DOM nodes with textContent, not innerHTML, so a
    record whose field name came out of a hostile file is inert."""
    hostile = "<img src=x onerror=alert(1)>"
    records = {"others": {"x": [{"key": "1", "fields": {hostile: hostile}, "length": None}]}}
    html = render_html(_inspection(records=records))
    assert "<img src=x" not in html, "escaped inside the JSON island"
    assert "innerHTML = '<pre>'" not in html


def test_the_debug_tab_reads_file_then_pipeline_then_stats() -> None:
    """File first because it says which file this is, pipeline next because it
    says whether reading it worked, then the detail."""
    html = render_html(_inspection())
    headings = re.findall(r"<h2>([^<]+)</h2>", html)
    assert headings == ["File", "Pipeline", "Stats", "Not translated"]


def test_a_stage_carries_a_mark_for_how_it_went() -> None:
    """Reading a ladder for the one row that failed is faster with a mark than
    with a class name. Refused and crashed share the cross -- both mean no
    result -- and the row styling still distinguishes whose fault it was."""
    from finale_file_parser.report.ladder import CRASHED, REFUSED, SKIPPED

    inspection = _inspection()
    inspection.stages = [
        Stage("read file", OK, {}),
        Stage("decode payload", REFUSED, {}, "no frame holds"),
        Stage("read records", CRASHED, {}, "IndexError"),
        Stage("build score", SKIPPED, {}),
    ]
    html = render_html(inspection)
    assert '<li class="ok">✅ read file' in html
    assert '<li class="refused">❌ decode payload' in html
    assert '<li class="crashed">❌ read records' in html
    assert '<li class="skipped">· build score' in html


def test_the_document_dump_is_replaced_by_the_gaps_it_carried() -> None:
    """The old Document pane held three things. Its per-pool counts were
    identical to the ones the Records tree already shows -- measured across 40
    `.musx` documents, identical in all 40 -- and its `version` was the family
    string the ladder reports a line above. Only the untranslated list was
    unique, so only it survived.
    """
    html = render_html(
        _inspection(document={"version": "18.0", "pools": {}, "untranslated": ["x"]})
    )
    assert "renderUntranslated" in html
    assert "JSON.stringify(value, null, 2)" not in html, "the document dump is gone"
