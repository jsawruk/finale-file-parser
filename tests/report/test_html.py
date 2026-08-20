"""Tests for the HTML report renderer."""

from __future__ import annotations

import json
import re
from dataclasses import asdict

from defusedxml import ElementTree as DET

from finale_file_parser.enigma.document import Record
from finale_file_parser.report.entry_facts import EntryFacts, decode_entry
from finale_file_parser.report.html import render_html
from finale_file_parser.report.ladder import OK, Stage
from finale_file_parser.report.model import Inspection


def _script(html: str) -> str:
    """The page's own JavaScript, without the JSON island it renders.

    The island carries values Python composed and the script must not, so a
    test that searched the whole page for a composed word could never tell the
    two apart.
    """
    match = re.search(r"//<!\[CDATA\[\n(.*?)\n//\]\]>", html, re.S)
    assert match is not None
    return match.group(1)


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
    assert headings == ["File", "Pipeline", "Stats"]


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


def test_the_document_summary_is_not_embedded_in_the_page() -> None:
    """All three of its parts had stopped saying anything here.

    Its per-pool counts were identical to the ones the Records tree shows --
    measured across 40 `.musx` documents, identical in all 40 -- and its
    `version` was the family string the ladder reports a line above. The
    untranslated list outlived both, and it is a module constant: 941 words of
    the same text in every report, describing the reader rather than the file
    in front of you. A caller holding an `Inspection` can still read it.
    """
    html = render_html(
        _inspection(document={"version": "18.0", "pools": {}, "untranslated": ["x"]})
    )
    assert "renderUntranslated" not in html
    assert "JSON.stringify(value, null, 2)" not in html, "the document dump is gone"
    assert '"document"' not in html, "and the payload no longer carries it"


def test_a_record_row_is_a_leaf_that_selects_rather_than_a_third_expander() -> None:
    """Clicking a record used to open one more level of nesting, which read as
    doing very little. A record is a leaf now, and clicking it fills the panel
    beside the tree."""
    records = {"others": {"measSpec": [{"key": "1", "fields": {"beats": "4"}, "length": 12}]}}
    html = render_html(_inspection(records=records))
    assert "class = 'rec'" in html or "className = 'rec'" in html
    assert "function showRecord(" in html
    assert 'class="split"' in html or "className = 'split'" in html


def test_the_bytes_a_record_carries_are_shown_as_hex_and_not_repeated_as_fields() -> None:
    """`payload` and `extra` are the bytes in the hex block, so listing them
    again underneath would just repeat the same bytes in base64."""
    html = render_html(_inspection())
    assert "function hexBlock(" in html and "function hexRows(" in html
    assert "BYTE_FIELDS = ['payload', 'extra']" in html
    assert "atob(value)" in html


def test_a_record_with_no_bytes_shows_its_xml_instead() -> None:
    """A `.musx` record has no undecoded form -- EnigmaXML arrives as XML -- so
    the panel shows the record's own XML where a `.mus` shows hex.

    It is the fragment the file holds, serialised from the source element, not
    rebuilt from the parsed fields: a rebuild matches in content but is not what
    the file says, and the point of the pane is to show what the file says.
    """
    records = {
        "others": {"frameSpec": [{"key": "13/0", "length": None, "xml": '<frameSpec cmper="13"/>'}]}
    }
    html = render_html(_inspection(records=records))
    assert "rec.xml" in html, "the panel renders the carried fragment verbatim"
    assert "xmlOf(" not in html, "and does not rebuild one from fields"


def test_a_musx_record_carries_xml_instead_of_walked_fields() -> None:
    """Both would be the same information -- same names, same values, same
    nesting -- and carrying both put the largest corpus document's payload over
    the report's 16 MB budget, which dropped the records entirely. So the pane
    that gained the XML would have lost everything.
    """
    from finale_file_parser.enigma.document import Record
    from finale_file_parser.report.model import _pool_record_entry

    record = Record(tag="gfhold", attrs={"cmper1": "1"}, text="", fields={"frame1": "2"})
    with_source = _pool_record_entry(record, 0, '<gfhold cmper1="1"><frame1>2</frame1></gfhold>')
    assert "fields" not in with_source
    fragment = with_source["xml"]
    assert isinstance(fragment, str) and fragment.startswith("<gfhold")

    # A .mus record keeps its fields: there they decode bytes that are
    # otherwise opaque, which is not a restatement of anything on screen.
    # This is the path a .mus entry-pool record actually takes -- the
    # formatter is shared because both containers model an entry as a Record.
    without_source = _pool_record_entry(record, 0, "")
    assert "fields" in without_source


def test_the_hex_view_tints_a_byte_at_a_time() -> None:
    """A field is tinted where it sits. Emitting one span per row -- the shape
    before this -- cannot colour a field that straddles a row boundary."""
    html = render_html(_inspection())
    assert "function tintMap(" in html
    assert "function tinted(" in html
    assert "function hexBlock(bin, map)" in html


def test_the_report_and_the_specification_tint_from_one_palette() -> None:
    """A field is the same colour in the document as in the tool, because both
    read the palette out of the library rather than restating it."""
    from finale_file_parser.formats.layouts import PALETTE

    html = render_html(_inspection())
    assert f"const PALETTE = {json.dumps(list(PALETTE))};" in html


def test_a_decoded_value_is_read_with_the_document_s_own_byte_order() -> None:
    """A `.mus` states its byte order and the 2001-2005 era does occur
    big-endian. Reading a measure width the wrong way round yields a number
    rather than an error, so the order travels with the report.
    """
    html = render_html(_inspection(byte_order="big"))
    assert '"byteOrder": "big"' in html
    assert "function decode(bin, offset, field, order)" in html
    assert "(order === 'big')" in html


def test_a_decoded_number_keeps_its_hex_visibly_apart_from_its_decimal() -> None:
    """`6  0x06` was written with two spaces and reached the page as `6 0x6`.

    HTML collapses runs of whitespace, so a separator made of spaces is not a
    separator at all -- the two numbers ran together into something that reads
    as one. The gap now comes from a span with a margin and a pair of
    parentheses, neither of which collapses, and the parentheses are what
    survives printing and greyscale where the colour does not.
    """
    html = render_html(_inspection())
    # The whole old expression, not the fragment `'  0x'`: these comments
    # explain what was wrong by quoting it, and an absence check on a fragment
    # a comment legitimately contains fails the moment the fix is documented.
    assert "(field.size > 1) ? value + '  0x'" not in html
    assert "hex.className = 'hexval';" in html
    assert "hex.textContent = '(' + text.hex + ')';" in html
    assert ".hexval { color: #777; margin-left: 0.7rem; }" in html


def test_hex_is_the_width_of_the_field_not_of_a_javascript_integer() -> None:
    """`(value >>> 0)` renders an int16 -1 as `0xffffffff`.

    That claims four bytes for a two-byte field and hides the sign bit the hex
    column exists to show. Padding to `size * 2` digits also keeps `0x0006` and
    `0x06` distinguishable, which matters because they are different fields.
    """
    html = render_html(_inspection())
    # As above: the comment quotes the old cast, so the check is on the code
    # that used it rather than on the cast appearing anywhere in the page.
    assert "value + '  0x' + (value >>> 0).toString(16)" not in html
    assert "const unsigned = (value < 0) ? value + Math.pow(2, field.size * 8) : value;" in html
    assert "unsigned.toString(16).padStart(field.size * 2, '0')" in html


def test_a_single_byte_gets_hex_too() -> None:
    """Hex used to be suppressed for `size === 1`, which hid it from `flags` --
    the field whose own note reads "0x20 marks a shape assignment", and the one
    where the decimal 32 says least."""
    html = render_html(_inspection())
    assert "(field.size > 1) ?" not in html


def test_the_tint_stops_where_the_payload_does() -> None:
    """A layout describes the payload; `extra` follows it in the same dump and
    the layout says nothing about it. `length` is their sum, so the boundary is
    taken from the payload field itself."""
    html = render_html(_inspection())
    assert "payloadLength" in html
    assert "tintMap(layout, payloadLength)" in html


def test_a_variable_length_tail_is_tinted_and_read_to_the_record_s_end() -> None:
    """A field of size 0 runs to the end of the payload -- a `textExprDef`
    description does, and it is the field a reader most wants to see.

    Multiplying by `f.size` would tint nothing and decode nothing for exactly
    that field, and the untinted bytes would say "not decoded", which is the one
    thing they are not. The payload length is what bounds the span, since it is
    the only thing that can.
    """
    html = render_html(_inspection())
    assert "const width = f.size || Math.max(0, limit - (base + f.offset));" in html
    assert "const width = field.size || (bin.length - offset);" in html
    # And the table says "0x24–end" rather than a span ending before it starts.
    assert "'–end'" in html


def test_a_tag_with_no_layout_says_so_rather_than_showing_nothing() -> None:
    """Nine payloads are decoded against a document's ~180 tags, so most records
    land here. A guessed layout would say something false -- but an empty space
    below the hex reads as a table that failed to render, not as the honest
    answer, so the honest answer is written out."""
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "if (layout) {" in script, "the table is drawn only where a layout exists"
    assert "if (!layout) {" in script, "and its absence is stated where one is not"
    assert "No field layout is known for this record" in script


def test_a_record_that_carries_a_name_decodes_it() -> None:
    """The `labelled` tags were identified by the words in their payloads, so
    those words are the one field worth showing. The catalogue says where the
    name starts; how far it runs is a property of the bytes, so the field is
    built in the renderer rather than carried in the payload."""
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "typeof named.textAt === 'number'" in script
    assert "type: 'char[]'" in script
    assert "field.type === 'char[]'" in script, "and char[] decodes as text, not as hex"


def test_a_description_reads_as_a_definition_not_a_sentence() -> None:
    """The tag on its own line, its meaning indented beneath.

    Run together as "fg tag - 'Simple Major Triad', ..." the two halves wrap
    into each other and the tag stops being findable, which is the one thing on
    that line a reader scans for.
    """
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "createElement('dl')" in script
    assert "term.textContent = displayTag(tag)" in script
    assert "meaning.textContent = named.description" in script
    assert ".tagdef dt { font-weight: bold; }" in html, "the term is distinguished"


def test_a_dcl_row_carries_only_its_bytes() -> None:
    """`incidences` used to sit under the hex. It is derivable from what is
    already on screen -- exactly `len(payload) / 12` for an `others` row and
    `/ 10` for a details one, across all 107,652 corpus records -- so it earned
    no line of its own."""
    from finale_file_parser.enigma.mus_rows import MusRowRecord
    from finale_file_parser.report.model import _mus_row_entry

    entry = _mus_row_entry(
        MusRowRecord(tag="DL", cmper=1, cmper2=0, payload=b"\x00" * 24, incidences=2)
    )
    fields = entry["fields"]
    assert isinstance(fields, dict)
    assert set(fields) == {"payload"}


def test_document_options_are_grouped_out_of_the_tag_list() -> None:
    """A document carries one option record under each of ~98 tags. Left in
    place they read as the same row repeated down the whole tree; gathered
    under one heading they read as what they are.

    The tag is the row, because 4,743 of 4,790 such tags across the corpus hold
    exactly one -- a child row under it would say nothing the tag did not.
    """
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "tree('document options'" in script
    assert "records.filter(r => r.options)" in script
    assert "records.filter(r => !r.options)" in script, "ordinary records stay in the tag list"
    assert "if (records.length === 1)" in script, "a single option record needs no row of its own"


def test_the_script_uses_no_regex_literal_for_the_sentinel() -> None:
    """This script is a Python string literal, where a backslash is Python's
    escape before it is ever JavaScript's. `/^\\(|\\)$/` raised a SyntaxWarning
    and would have shipped a regex Python had already rewritten."""
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "function withoutSentinel(key)" in script
    assert "key.slice(1, -1)" in script


def test_an_unprintable_tag_is_shown_as_its_code_point() -> None:
    """A DCL tag is two characters decoded from a u16 as latin-1, and the era
    uses bytes that are not letters. `0x80` arrives as a C1 control, which a
    browser draws as a blank or a box -- unreadable, untypeable, unsearchable.

    Printable tags must pass through untouched, which is every numeric 2011 tag
    and every ordinary two-letter one.
    """
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "function displayTag(tag)" in script
    assert "codes.every(printable)" in script, "a printable tag is returned as it is"
    assert "'U+' + codes[i].toString(16)" in script
    # Shown, not stored: the raw tag stays the key every lookup uses.
    assert "displayTag(tag)" in script


def test_a_named_tag_leads_with_its_name() -> None:
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "named.name + '  —  ' + pool" in script
    assert "named.description" in script


def test_a_records_key_is_not_restated_underneath_it() -> None:
    """An "addressed by" block used to sit below the hex restating the cmper and
    part. Those *are* the key, shown once in the heading, and could never differ
    from it. What is not the key -- a DCL row's `incidences` -- still shows."""
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    # The quoted string, not the words: a comment still explains why it went.
    assert "'addressed by'" not in script
    assert "Object.keys(rest).length !== 0" in script, "and nothing renders when none is left"


def test_the_hex_view_builds_its_newline_rather_than_escaping_one() -> None:
    """The script is a Python string literal, so a backslash-n would become a
    real newline inside a JS string literal and fail to parse. The old byte
    pane hit this; the per-record one must not reintroduce it."""
    html = render_html(_inspection())
    script = html[html.index("//<![CDATA[") :]
    assert "String.fromCharCode(10)" in script


def test_the_xml_pane_is_absent_entirely_for_a_document_that_has_no_source() -> None:
    """A `.mus` holds binary records and reconstructs its document model, so it
    has no source text. The pane is not rendered empty -- it is not rendered.

    Absent rather than empty because an empty pane reads as a failure: it
    invites the reader to ask what went wrong when nothing did.
    """
    html = render_html(_inspection())
    assert 'data-pane="xml"' not in html
    assert '<section id="xml">' not in html
    # The panes that do not depend on the container are still there.
    assert 'data-pane="music"' in html
    assert 'data-pane="records"' in html


def test_the_xml_tree_is_built_lazily_from_the_source() -> None:
    """A 2.5 MB source is tens of thousands of elements. Building them all on
    load would stall the Music pane, which is the one that opens by default, for
    a pane the reader may never look at -- so the tree is drawn when the tab is
    first opened, and each element's children when that element is opened.
    """
    html = render_html(_inspection(xml="<finale><a><b>1</b></a></finale>"))
    assert "function renderXml()" in html
    assert "if (b.dataset.pane === 'xml') { renderXml(); }" in html
    # The fold itself, and the guard that fills it only once.
    assert "node.addEventListener('toggle'" in html
    assert "if (node.open && !node.dataset.filled)" in html
    # Not drawn at load, unlike the three panes that are.
    assert "renderXml();\nshow('music')" not in html


def test_the_raw_source_is_hidden_but_kept_as_the_parse_input_and_fallback() -> None:
    """Hidden so the browser lays out no megabytes of text, present because the
    tree is parsed from it -- and unhidden if it will not parse, since a
    document that cannot be folded still has to be readable."""
    html = render_html(_inspection(xml="<finale/>"))
    assert 'id="xml-source" hidden="hidden"' in html
    assert "src.textContent" in html
    assert "src.hidden = false;" in html


def test_the_xml_pane_carries_the_source_entire_and_escaped() -> None:
    """The whole document, never a prefix: a truncated XML reads as a complete
    one right up to where it stops."""
    source = '<?xml version="1.0"?><finale><measure n="1"/></finale>'
    html = render_html(_inspection(xml=source))
    assert 'data-pane="xml"' in html
    assert '<section id="xml">' in html
    # Escaped, so the source's own tags are shown rather than parsed as this
    # page's markup -- which is also what keeps the page well-formed.
    assert "&lt;finale&gt;&lt;measure n=&quot;1&quot;/&gt;" in html
    assert "<finale>" not in html


def test_the_source_is_embedded_once_not_twice() -> None:
    """The other panes are built from the JSON island, which is both embedded
    and rendered. At a corpus median of 2.77 MB the source is far the largest
    thing in the report, so it goes in the page body only.
    """
    marker = "UNIQUE_XML_MARKER_9137"
    html = render_html(_inspection(xml=f"<finale>{marker}</finale>"))
    assert html.count(marker) == 1


def test_a_hostile_source_cannot_break_out_of_the_xml_pane() -> None:
    """The source is untrusted input like everything else the file supplies."""
    html = render_html(_inspection(xml='</pre></section><script>alert("x")</script>'))
    assert "</pre></section><script>" not in html
    assert "&lt;/pre&gt;&lt;/section&gt;" in html


def test_the_record_pane_shows_entry_facts_when_one_is_selected() -> None:
    """The page renders `entryIndex[entnum]` and does nothing else -- no
    decoding, no joining. That line is what keeps a second decoder out of the
    page, which is why the index is built in Python."""
    html = render_html(
        _inspection(
            entry_index={"9": {"placements": [], "named_by": [], "decode": None, "unresolved": []}}
        )
    )
    assert '"entryIndex"' in html
    assert "function renderEntryFacts(" in html
    assert "Decodes as" in html
    assert "Pointed to by" in html


def test_entry_facts_render_the_dotted_duration_name_not_the_base_alone() -> None:
    """Regression test for the report showing "dura 1536 -> quarter": 1536 EDU
    is a dotted quarter (1024 + 512), and the pane must say so, not drop the
    dot. `duration_name` arrives from Python already composed as "dotted
    quarter" -- this pins that the embedded page carries that composed string,
    and that the renderer references the base and dot count too rather than
    folding everything into one opaque phrase."""
    html = render_html(
        _inspection(
            entry_index={
                "9": {
                    "placements": [],
                    "named_by": [],
                    "decode": {
                        "duration_edu": 1536,
                        "duration_base": "quarter",
                        "dots": 1,
                        "duration_name": "dotted quarter",
                        "is_rest": False,
                        "notes": [],
                    },
                    "unresolved": [],
                }
            }
        )
    )
    assert '"dotted quarter"' in html
    assert "d.duration_name" in html
    assert "d.duration_base" in html
    assert "d.dots" in html


def test_the_page_never_composes_a_duration_name_of_its_own() -> None:
    """A guard that can actually fail.

    What it replaced forbade three strings (`"harmLev +"`, `"decodeKey("`,
    `"spellNote("`) that no plausible implementation would have contained, so
    it passed by construction. The rule it was meant to defend is that the page
    renders and does not compute -- and the nearest that rule has come to being
    broken is the duration name, whose one-line JavaScript version ("dotted " +
    base) is the obvious way to write it. Every word only the composition
    produces is forbidden here, so moving it back into the browser fails this.
    """
    script = _script(render_html(_inspection()))
    for forbidden in ("dotted", "-dot", "double dot", "thirty-second", "128th"):
        assert forbidden not in script


def test_an_entry_facts_payload_carries_the_name_python_composed() -> None:
    """The seam end to end: a real `decode_entry` result, serialised the way
    `report.model` serialises it, reaching the page.

    The test that came before this one asserted `"dotted quarter"` was in the
    HTML while supplying that string itself from a hand-written dict, so the
    only thing it proved was that `json.dumps` works. Here 1536 EDU goes in and
    the phrase comes out, through the code that composes it.
    """
    entry = Record(
        tag="entry",
        attrs={"entnum": "9"},
        text="",
        fields={"dura": "1536", "numNotes": "0"},
    )
    decode = decode_entry(entry, key_raw=None, transposition=None)
    assert decode is not None
    facts = EntryFacts(decode=decode)

    html = render_html(_inspection(entry_index={"9": asdict(facts)}))

    assert '"dotted quarter"' in html
    assert '"duration_base": "quarter"' in html or '"duration_base":"quarter"' in html


def test_a_named_by_reference_selects_the_row_python_targeted() -> None:
    """`tag`/`key` name the record as the document calls it; `tree_tag`/
    `tree_key` name the row the Records tree actually rendered. On a `.mus`
    those differ -- the tree is built from the raw numeric pool -- so selecting
    on the first pair matched nothing on the corpus's primary format."""
    script = _script(render_html(_inspection()))

    assert "selectRecord(r.pool, r.tree_tag, r.tree_key)" in script
    assert "selectRecord(r.pool, r.tag, r.key)" not in script


def test_a_reference_with_no_row_is_rendered_without_a_click_affordance() -> None:
    """Python decides whether a reference has a row; the page must not work one
    out for itself, and must not offer a click that does nothing."""
    script = _script(render_html(_inspection()))

    assert "if (r.tree_tag && r.tree_key)" in script
    # The class that says "clickable" is applied inside that guard, so a
    # reference without a target looks like the plain text it is.
    assert "'leaf rec'" not in script


def test_named_by_lines_are_not_records_tree_rows() -> None:
    """`selectRecord` scans `.rec`, so a "named by" line carrying that class put
    it in the set of rows being searched. One class, one meaning."""
    script = _script(render_html(_inspection()))

    assert ".rec" in script
    assert "'leaf ref'" in script


def test_selecting_a_row_opens_the_section_it_is_folded_inside() -> None:
    """A row inside a collapsed `<details>` is selected and never seen, which is
    why a manual check of this feature looked like it did nothing. Opening the
    ancestors and scrolling to the row is rendering, not deciding."""
    script = _script(render_html(_inspection()))

    assert "DETAILS" in script
    assert "node.open = true" in script
    assert "scrollIntoView" in script
