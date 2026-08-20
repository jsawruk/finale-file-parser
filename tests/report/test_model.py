"""Tests for the inspection model.

The readers are stubbed, so these cover the ladder's shape rather than the
parser's behaviour.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from unittest import mock

import pytest

from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
)
from finale_file_parser.enigma.mus_details import (
    TAG_ARTIC_ASSIGN,
    TAG_LYRIC_VERSE,
    TAG_TUPLET_DEF,
    MusDetailRecord,
)
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.report import model
from finale_file_parser.report.ladder import CRASHED, OK, REFUSED, SKIPPED, Ladder

CORPUS = Path(__file__).parent.parent.parent / "corpus"


def _file(tmp_path: Path) -> Path:
    path = tmp_path / "score.mus"
    path.write_bytes(b"not really a mus file")
    return path


def test_the_ladder_stops_where_the_reader_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: the report says how far it got."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())

    def refuse(p: object) -> object:
        raise FinaleFileError(f"{p} has no frame holds")

    monkeypatch.setattr(model, "read_mus_pools", refuse)
    inspection = model.inspect_document(path)
    names = [(s.name, s.status) for s in inspection.stages]
    assert names[0] == ("read file", OK)
    assert names[1] == ("detect version", OK)
    assert names[2][1] == REFUSED
    assert {status for _, status in names[3:]} == {SKIPPED}


def test_the_error_does_not_carry_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A report is meant to be sendable. Reader messages embed the path."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())

    def refuse(p: object) -> object:
        raise FinaleFileError(f"{p} has no frame holds")

    monkeypatch.setattr(model, "read_mus_pools", refuse)
    inspection = model.inspect_document(path)
    error = next(s.error for s in inspection.stages if s.error)
    assert str(tmp_path) not in error
    assert "score.mus" in error


def test_file_identity_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Name and size. The sha256 that used to sit beside them is gone: it was
    read as saying something about how the file was decoded, when it was only
    ever a hash of the bytes on disk."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())
    monkeypatch.setattr(
        model, "read_mus_pools", lambda p: (_ for _ in ()).throw(FinaleFileError("x"))
    )
    inspection = model.inspect_document(path)
    assert inspection.file["name"] == "score.mus"
    assert inspection.file["size"] == str(len(b"not really a mus file"))
    assert "sha256" not in inspection.file


def test_a_reader_bug_is_reported_as_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())

    def crash(p: object) -> object:
        raise IndexError("index out of range")

    monkeypatch.setattr(model, "read_mus_pools", crash)
    inspection = model.inspect_document(path)
    stage = next(s for s in inspection.stages if s.error)
    assert stage.status == "crashed"
    assert "IndexError" in (stage.error or "")


def test_a_crash_in_the_records_depth_does_not_stop_the_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The records/raw depths are independent of the pipeline proper: a bug in
    one must show up as its own CRASHED stage, using the ladder's own
    OK/REFUSED/CRASHED vocabulary, without halting the stages after it -- so a
    corpus sweep scanning `stages` for CRASHED can actually see it, and the
    rest of the report (built from a separate call) still comes back."""
    from finale_file_parser.enigma.mus_payload import MusPool

    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())
    monkeypatch.setattr(model, "read_mus_pools", lambda p: (MusPool(data=b"abc"),))

    def crash(target: Path, details: object = None) -> dict[str, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr(model, "_mus_records", crash)
    monkeypatch.setattr(
        model,
        "read_mus_document",
        lambda p: (_ for _ in ()).throw(FinaleFileError("no document here")),
    )

    inspection = model.inspect_document(path)
    by_name = {s.name: s for s in inspection.stages}

    assert by_name["read records"].status == CRASHED
    assert "RuntimeError" in (by_name["read records"].error or "")
    assert "boom" in (by_name["read records"].error or "")
    # Non-halting: the ladder still attempted (did not SKIP) the stage after
    # the crash, and the one after that reports its own outcome too.
    assert by_name["build document"].status == REFUSED
    assert by_name["build score"].status == SKIPPED


def test_inspecting_a_file_that_is_not_finale_at_all_still_returns(
    tmp_path: Path,
) -> None:
    """Report generation never fails."""
    path = tmp_path / "notes.mus"
    path.write_bytes(b"\x00\x01\x02")
    inspection = model.inspect_document(path)
    assert inspection.stages
    assert inspection.stats is None


def test_inspecting_a_directory_still_returns() -> None:
    """`path.read_bytes()` raises `IsADirectoryError` on a directory. That must
    stop the ladder, not the function."""
    inspection = model.inspect_document(Path(__file__).parent)
    assert inspection.stages[0].name == "read file"
    assert inspection.stages[0].status == REFUSED
    assert {s.status for s in inspection.stages[1:]} == {SKIPPED}
    assert inspection.stats is None


def test_inspecting_a_nonexistent_path_still_returns(tmp_path: Path) -> None:
    """`path.read_bytes()` raises `FileNotFoundError`. Same requirement."""
    inspection = model.inspect_document(tmp_path / "does-not-exist.mus")
    assert inspection.stages[0].name == "read file"
    assert inspection.stages[0].status == REFUSED
    assert {s.status for s in inspection.stages[1:]} == {SKIPPED}
    assert inspection.stats is None


@pytest.mark.skipif(sys.platform == "win32", reason="chmod permission bits are POSIX-only")
def test_inspecting_an_unreadable_file_still_returns(tmp_path: Path) -> None:
    """`path.read_bytes()` raises `PermissionError` on a file with no read bit."""
    path = tmp_path / "locked.mus"
    path.write_bytes(b"not really a mus file")
    path.chmod(0o000)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("running as a user that bypasses file permissions")
        inspection = model.inspect_document(path)
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert inspection.stages[0].name == "read file"
    assert inspection.stages[0].status == REFUSED
    assert {s.status for s in inspection.stages[1:]} == {SKIPPED}
    assert inspection.stats is None


class _FakeVersion:
    class _Family:
        value = "mus"

    family = _Family()
    label = "Finale 2005"
    confidence = None
    detail = None


def test_record_fields_stop_nesting_at_the_cap() -> None:
    """A record's fields may contain records. Hostile input must not recurse
    without end."""
    from finale_file_parser.enigma.document import Record
    from finale_file_parser.report.model import MAX_FIELD_DEPTH, walk_fields

    deepest = Record(tag="leaf", attrs={}, text="", fields={})
    node = deepest
    for _ in range(MAX_FIELD_DEPTH + 5):
        node = Record(tag="branch", attrs={}, text="", fields={"child": node})

    walked = walk_fields(node.fields, depth=0)
    depth = 0
    cursor: object = walked
    while isinstance(cursor, dict) and "child" in cursor:
        cursor = cursor["child"]
        depth += 1
    assert depth <= MAX_FIELD_DEPTH


def test_raw_bytes_are_base64_not_hex() -> None:
    """Base64 is 4/3 of the payload where hex is 2x."""
    import base64

    from finale_file_parser.report.model import encode_raw

    assert base64.b64decode(encode_raw(b"\x00\xff\x10")) == b"\x00\xff\x10"


def test_the_budget_drops_records_before_the_music_tree() -> None:
    """Stats and document summaries are never truncated.

    Of the two payloads that can go, `records` goes first: it is far the
    largest, and the music tree is the view a reader most likely opened the
    report to see.
    """
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0", "sha256": ""})
    inspection.stats = {
        "parts": [],
        "totals": {"parts": 1, "measures": 0, "events": 0, "pitches": 0},
    }
    inspection.records = {"others": {"measSpec": [{"key": "A" * 2000}]}}
    inspection.music = {"parts": []}

    apply_budget(inspection, limit=500)
    assert inspection.records == {}
    assert inspection.stats is not None
    assert any("records" in note for note in inspection.notes)


def test_the_budget_takes_the_layouts_with_the_records() -> None:
    """A layout describes a record. With the records gone it describes nothing,
    and a renderer holding one would key a hex view to bytes that are not
    there."""
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0"})
    inspection.records = {"others": {"176": [{"key": "A" * 2000}]}}
    inspection.layouts = {"others": {"176": {"record": "measSpec", "fields": []}}}

    apply_budget(inspection, limit=500)
    assert inspection.records == {}
    assert inspection.layouts == {}


def test_the_options_sentinel_is_shown_as_what_it_means_not_as_a_key() -> None:
    """`0xFFFE` is not an address: it is what Enigma writes where a key would go
    on a record that has nothing to be keyed by.

    Shown as `cmper 65534` it reads like a very high measure number, and since a
    document carries one such record under each of ~99 tags, a tree of them
    reads as one row repeated when each is a different record.
    """
    from finale_file_parser.enigma.mus_others import OPTIONS_CMPER, MusOther

    options = MusOther(tag=109, cmper=OPTIONS_CMPER, part=0, payload=b"\x01", extra=b"")
    assert model._mus_other_entry(options)["key"] == "(document options, part 0)"

    ordinary = MusOther(tag=176, cmper=3, part=0, payload=b"\x01", extra=b"")
    assert model._mus_other_entry(ordinary)["key"] == "(cmper 3, part 0)"


def test_an_options_record_is_flagged_so_it_can_be_grouped() -> None:
    """Flagged per record, not per tag: 94 corpus tags hold a document-wide
    default alongside the numbered records it applies to, so grouping a whole
    tag would move ordinary records under a heading that does not describe
    them. The flag also spares a renderer parsing the key text back apart.
    """
    from finale_file_parser.enigma.mus_others import OPTIONS_CMPER, MusOther

    options = MusOther(tag=109, cmper=OPTIONS_CMPER, part=0, payload=b"\x01", extra=b"")
    assert model._mus_other_entry(options)["options"] is True

    # Absent rather than False: it costs nothing on the records that are the
    # overwhelming majority, and `rec.options` is falsy either way.
    ordinary = MusOther(tag=176, cmper=3, part=0, payload=b"\x01", extra=b"")
    assert "options" not in model._mus_other_entry(ordinary)


def test_a_tag_is_named_and_its_tier_travels_with_the_name() -> None:
    """`others / 176 / (cmper 1, part 0)` names a record only to someone holding
    the catalogue.

    The tier is carried but not rendered as prose on every record: the
    specification's tag tables state each tier in full, and a reader of this
    report as data must still not take a `matched` name for a decoded one.
    """
    named = model._tag_names({"others": {"176": [], "144": [], "213": []}})
    by_tag = named["others"]
    assert isinstance(by_tag, dict)

    # 213 is observed across the corpus but unidentified: no name is correct.
    assert set(by_tag) == {"176", "144"}

    decoded = by_tag["176"]
    assert isinstance(decoded, dict)
    assert decoded["name"] == "measSpec"
    assert decoded["tier"] == "decoded"
    assert "evidence" not in decoded

    matched = by_tag["144"]
    assert isinstance(matched, dict)
    assert matched["name"] == "fontName"
    assert matched["tier"] == "matched", "a lead must not be recorded as a decoding"


def test_the_budget_takes_the_names_with_the_records() -> None:
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0"})
    inspection.records = {"others": {"176": [{"key": "A" * 2000}]}}
    inspection.tags = {"others": {"176": {"name": "measSpec"}}}

    apply_budget(inspection, limit=500)
    assert inspection.records == {}
    assert inspection.tags == {}


def test_a_layout_is_offered_for_a_tag_whose_payload_is_decoded() -> None:
    records: dict[str, object] = {"others": {"176": [], "124": []}}
    layouts = model._layouts_present(records)

    assert set(layouts) == {"others"}
    by_tag = layouts["others"]
    assert isinstance(by_tag, dict)
    # 176 is measSpec, whose payload this project decodes; 124 is channelPlayData,
    # which it does not. A tag with no layout must be absent rather than empty:
    # the renderer distinguishes "no layout" from "a layout with no fields".
    assert set(by_tag) == {"176"}
    entry = by_tag["176"]
    assert isinstance(entry, dict)
    assert entry["record"] == "measSpec"
    assert [f["name"] for f in entry["fields"]] == [
        "width",
        "key",
        "beats",
        "divbeat",
        "flags",
    ]


def test_a_layout_carries_spans_and_not_values() -> None:
    """The bytes are already in the record. Writing decoded values here would
    state the payload a second time, in a report with a size budget."""
    layouts = model._layouts_present({"others": {"176": []}})
    by_tag = layouts["others"]
    assert isinstance(by_tag, dict)
    entry = by_tag["176"]
    assert isinstance(entry, dict)

    for span in entry["fields"]:
        assert set(span) == {"offset", "size", "name", "type", "note"}


def test_the_dcl_spelling_of_a_tag_finds_the_same_layout() -> None:
    """A 2001-2005 document keys its records by two characters, not a number."""
    numeric = model._layouts_present({"others": {"176": []}})["others"]
    dcl = model._layouts_present({"others": {"MS": []}})["others"]
    assert isinstance(numeric, dict)
    assert isinstance(dcl, dict)
    assert numeric["176"] == dcl["MS"]


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_the_byte_order_travels_with_the_report() -> None:
    """Not a constant, and not cosmetic: the corpus holds big-endian `.mus`
    documents, where reading a measSpec width little-endian turns 360 EVPU into
    26,625 -- a number, not an error. The renderer decodes with this, so it has
    to be the order the reader used.

    The order is found with the pool reader, which is what `inspect_document`
    itself reads it from, and only the two documents that prove the point go
    through the whole pipeline. Running all 40 through it cost 29 seconds to
    assert something two documents establish.
    """
    from finale_file_parser.enigma.mus_payload import read_mus_pools

    found: dict[str, Path] = {}
    for path in sorted(CORPUS.rglob("*.mus")):
        try:
            pools = read_mus_pools(path)
        except FinaleFileError:
            continue
        if pools:
            found.setdefault(pools[0].byte_order, path)
        if {"little", "big"} <= found.keys():
            break
    assert "big" in found, "a corpus that cannot exercise the order proves nothing"

    for order, path in found.items():
        assert model.inspect_document(path).byte_order == order


def test_no_layout_is_offered_where_the_reader_computes_the_offsets() -> None:
    """`frameSpec` keeps its entry pair in its last incidence and `gfhold` puts
    its frame slots at an era-dependent base, so neither has one fixed layout to
    lay over a record's bytes.

    Tinting them at their nominal offsets would decode entry numbers that look
    entirely plausible and are wrong. Plain hex says "not decoded", which is
    true; a wrong span says something false.
    """
    assert model._layouts_present({"others": {"146": [], "FR": []}}) == {}
    assert model._layouts_present({"details": {"1044": [], "GF": []}}) == {}


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_a_real_mus_file_gets_records() -> None:
    """End-to-end: the wiring populates the records depth from a real file, and
    what it produces is actually JSON -- the shape `apply_budget` and a renderer
    both depend on."""
    path = next(CORPUS.rglob("*.mus"))
    inspection = model.inspect_document(path)

    assert inspection.records
    for _pool_name, by_tag in inspection.records.items():
        assert isinstance(by_tag, dict)
        for tag, entries in by_tag.items():
            assert isinstance(tag, str)
            for entry in entries:
                # No `offset`: no reader records where a record began, so the
                # field the design asked for could only ever have been null.
                # A `.mus` binary record carries `fields` -- the decoding of
                # its bytes; a `.musx` record carries `xml` instead, which is
                # both its source and its decoding; a `.mus` text section
                # carries `text`.
                # `options` is optional and marks the 0xFFFE sentinel, so it is
                # dropped before the shape is checked. `entnum` is optional
                # too, and is present on any record the entry join runs on --
                # which is every entry-keyed details record, not only an
                # `entry`. What must hold is that a record which is not itself
                # the entry says so, so the facts the page shows underneath it
                # are not read as its own. Checked below rather than folded
                # into the allowed shapes, so this still catches a field added
                # to every record without anyone deciding to add it.
                if "entnum" in entry and tag != "entry":
                    assert entry["entry_facts_note"]
                shape = entry.keys() - {"options", "entnum", "entry_facts_note"}
                assert shape in (
                    {"key", "fields", "length"},
                    {"key", "xml", "length"},
                    # A `.mus` text section: ETF tagged text, neither bytes to
                    # decode nor XML. Listed rather than allowed by a wildcard,
                    # so this still catches a field added to every record
                    # without anyone deciding to add it.
                    {"key", "text", "length"},
                )
                assert isinstance(entry["key"], str)

    # Round-trips through JSON without error: no bytes, no dataclasses left over.
    json.dumps(inspection.records)


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_a_real_musx_file_gets_records() -> None:
    """EnigmaXML's own records are already the rawest view a `.musx` has."""
    path = next(CORPUS.rglob("*.musx"))
    inspection = model.inspect_document(path)

    assert inspection.records
    assert set(inspection.records) == {
        "header",
        "mappings",
        "options",
        "others",
        "details",
        "entries",
        "texts",
    }
    json.dumps(inspection.records)


def test_a_record_is_keyed_by_every_identity_attribute_it_carries() -> None:
    """A `gfhold` says which staff and measure it places music into, and it says
    it in `cmper1`/`cmper2` -- not `cmper`.

    Keying only on `cmper`/`inci`/`part` found nothing on such a record and fell
    back to its position in the array, so the report showed `frame1` without the
    staff and measure it belonged to. Worse, a record carrying `cmper1`, `cmper2`
    AND `inci` got a key of just the `inci`, which reads like an identity while
    naming the wrong thing. 2,263 of one corpus archive's 5,880 records were
    keyed this way. The `.mus` path never had the bug: `_mus_detail_entry` has
    always keyed on `cmper1/cmper2/inci`, and this brings `.musx` into line.
    """
    from finale_file_parser.enigma.document import Record
    from finale_file_parser.report.model import _musx_key

    gfhold = Record(tag="gfhold", attrs={"cmper1": "3", "cmper2": "12"}, text="", fields={})
    assert _musx_key(gfhold, 7) == "(cmper1 3, cmper2 12)"

    with_inci = Record(
        tag="crossChord", attrs={"cmper1": "3", "cmper2": "12", "inci": "1"}, text="", fields={}
    )
    assert _musx_key(with_inci, 7) == "(cmper1 3, cmper2 12, inci 1)"

    entry = Record(tag="entry", attrs={"entnum": "41", "next": "42"}, text="", fields={})
    assert _musx_key(entry, 7) == "(entnum 41)", "`next` is a link, not identity"

    text = Record(tag="expression", attrs={"number": "5"}, text="", fields={})
    assert _musx_key(text, 7) == "(number 5)"

    ordinary = Record(tag="measSpec", attrs={"cmper": "2", "inci": "0"}, text="", fields={})
    assert _musx_key(ordinary, 7) == "(cmper 2, inci 0)", "every number says which it is"

    anonymous = Record(tag="header", attrs={}, text="", fields={})
    assert _musx_key(anonymous, 7) == "(position 7)", (
        "position is still the fallback when nothing names it, and now says so"
    )


_MIRROR_XML = (
    b'<finale version="18.0" xmlns="http://www.makemusic.com/2012/finale">'
    b'<entries><entry entnum="1" prev="0" next="0"><numNotes>1</numNotes>'
    b'<dura>1024</dura><isNote/><note id="1"><harmLev>0</harmLev>'
    b"<harmAlt>0</harmAlt></note></entry></entries>"
    b'<others><frameSpec cmper="10" inci="0"><startEntry>1</startEntry>'
    b"<endEntry>1</endEntry></frameSpec>"
    b'<frameSpec cmper="20" inci="0"><startEntry>1</startEntry>'
    b"<endEntry>1</endEntry></frameSpec>"
    b'<measSpec cmper="1"><keySig><key>0</key></keySig><beats>4</beats>'
    b"<divbeat>1024</divbeat></measSpec>"
    b'<staffSpec cmper="1"><x>a</x></staffSpec><staffSpec cmper="2"><x>a</x></staffSpec></others>'
    b'<details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>'
    b'<gfhold cmper1="2" cmper2="1"><frame1>20</frame1></gfhold></details></finale>'
)


def test_a_mirrored_cell_names_the_other_staves_from_both_sides() -> None:
    """One entry span, two `gfhold` records naming it: a mirror.

    The annotation is symmetric on purpose. The file marks neither placement as
    the copy, so staff 1 is told about staff 2 and staff 2 about staff 1, and
    nothing anywhere calls one of them the original.
    """
    from finale_file_parser.enigma.document import parse_enigma
    from finale_file_parser.report.model import _mirrored_cells

    cells = _mirrored_cells(parse_enigma(_MIRROR_XML))
    assert cells == {(1, 1, 1): [2], (2, 1, 1): [1]}


def test_an_unmirrored_document_reports_no_cells() -> None:
    """The overwhelming majority: one corpus document in 639 has a mirror that
    reaches a score, so the empty result is the path that must stay cheap."""
    from finale_file_parser.enigma.document import parse_enigma
    from finale_file_parser.report.model import _mirrored_cells

    plain = _MIRROR_XML.replace(b'<gfhold cmper1="2" cmper2="1"><frame1>20</frame1></gfhold>', b"")
    assert _mirrored_cells(parse_enigma(plain)) == {}


def test_a_record_fragment_is_indented_however_the_file_wrote_it() -> None:
    """EnigmaXML is written both pretty-printed and compact. Left verbatim the
    same record would render as an indented block from one file and as a single
    unreadable line from another, so the whitespace between elements is this
    report's while the elements, attributes and values stay the file's.
    """
    from finale_file_parser.report.model import _record_source

    compact = (
        b'<finale xmlns="http://www.makemusic.com/2012/finale">'
        b'<others><frameSpec cmper="11" inci="0">'
        b"<startEntry>1</startEntry><endEntry>4</endEntry>"
        b"</frameSpec></others></finale>"
    )
    spaced = (
        b'<finale xmlns="http://www.makemusic.com/2012/finale">\n'
        b'  <others>\n        <frameSpec cmper="11" inci="0">\n'
        b"          <startEntry>1</startEntry>\n          <endEntry>4</endEntry>\n"
        b"        </frameSpec>\n  </others>\n</finale>"
    )
    expected = (
        '<frameSpec cmper="11" inci="0">\n'
        "  <startEntry>1</startEntry>\n"
        "  <endEntry>4</endEntry>\n"
        "</frameSpec>"
    )
    assert _record_source(compact)["others"][0] == expected
    assert _record_source(spaced)["others"][0] == expected, "the file's own depth is not carried"


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_the_mus_text_stream_reaches_the_records_tree() -> None:
    """The one major structure of a `.mus` the inspector could not see.

    It holds the staff names, the expression text and the font each is set in,
    and none of it appeared anywhere in the report: the records tree showed the
    two binary pools, and `read_mus_document` translates only the three lyric
    markers, so a document with several hundred sections reported one.
    """
    for path in sorted(CORPUS.rglob("*.mus"))[:12]:
        try:
            records = model._mus_records(path)
        except FinaleFileError:
            continue
        texts = records.get("texts")
        if not texts:
            continue
        assert isinstance(texts, dict)
        # Every marker, not the three that become lyrics.
        assert set(texts) - {"verse", "chorus", "section"}, "only the translated markers came back"
        for sections in texts.values():
            for entry in sections:
                assert set(entry) == {"key", "text", "length"}
                assert str(entry["text"]).startswith("^")
                assert str(entry["text"]).endswith("^end")
        return
    pytest.skip("no corpus .mus carried a text stream")


def test_a_text_section_keeps_its_markup() -> None:
    """`^font(Font0,8191)` is the half of an expression that says what its
    character means. A glyph shown without it is a glyph with no context."""
    from finale_file_parser.report.html import render_html

    page = render_html(model.Inspection(file={"name": "x", "size": "1"}))
    script = page[page.index("//<![CDATA[") :]
    assert "rec.text !== undefined" in script
    assert "box.textContent = rec.text" in script


def test_a_mus_report_collects_the_entry_pool() -> None:
    """The `.mus` container names four pools -- others (15), details (16),
    entries (17), text (18) -- and this depth used to collect three.

    Nothing about the format made entries the odd one out: the reader has
    always read them, and every note the Music tab draws comes from there. They
    were simply never added, and the Music tab made them look accounted for --
    which is why this asserts the pool is *present*, not merely that the file
    parses.
    """
    from finale_file_parser.enigma.document import Record

    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    model_path = Path("unused.mus")

    with (
        mock.patch.object(model, "read_mus_others", return_value=()),
        mock.patch.object(model, "read_mus_details", return_value=()),
        mock.patch.object(model, "read_mus_entry_records", return_value=(entry,)),
        mock.patch.object(model, "_mus_texts", return_value={}),
    ):
        records = model._mus_records(model_path)

    assert "entries" in records, "the entry pool is one of the four this container names"
    entries = records["entries"]
    assert isinstance(entries, dict) and "entry" in entries


def test_an_unreadable_entry_pool_does_not_cost_the_other_pools() -> None:
    """Same rule as the text stream: a document whose others and details read
    perfectly must not lose them to an entry pool that does not."""
    with (
        mock.patch.object(model, "read_mus_others", return_value=()),
        mock.patch.object(model, "read_mus_details", return_value=()),
        mock.patch.object(
            model, "read_mus_entry_records", side_effect=FinaleFileError("no entry pool")
        ),
        mock.patch.object(model, "_mus_texts", return_value={}),
    ):
        records = model._mus_records(Path("unused.mus"))

    assert "entries" not in records
    assert "others" in records and "details" in records


def test_an_inspection_carries_facts_for_each_entry() -> None:
    """Both containers reach this through `_finish`, so one test covers both."""
    from finale_file_parser.enigma.document import (
        DetailsPool,
        EnigmaDocument,
        EntriesPool,
        OptionsPool,
        OthersPool,
        Pool,
        Record,
        TextsPool,
    )
    from finale_file_parser.report.ladder import Ladder

    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    entry = Record(
        tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024", "numNotes": "0"}
    )
    doc = EnigmaDocument(
        version="test",
        header=Pool(records=()),
        mappings=Pool(records=()),
        options=OptionsPool(records=()),
        others=OthersPool(records=(frame,)),
        details=DetailsPool(records=(gfhold,)),
        entries=EntriesPool(records=(entry,)),
        texts=TextsPool(records=()),
    )
    inspection = model.Inspection(file={"name": "x.mus"})
    model._finish(Ladder(), doc, inspection, engrave_notation=False)

    assert "9" in inspection.entry_index


def _mus_document(details: tuple[Record, ...], entries: tuple[Record, ...]) -> EnigmaDocument:
    """An `EnigmaDocument` holding only the two pools these tests need.

    A `.mus` reaches `EnigmaDocument` through `mus_document`, which synthesises
    exactly these records -- so a document built by hand here stands in for one
    a real `.mus` produces, without a corpus.
    """
    return EnigmaDocument(
        version="test",
        header=Pool(records=()),
        mappings=Pool(records=()),
        options=OptionsPool(records=()),
        others=OthersPool(records=()),
        details=DetailsPool(records=details),
        entries=EntriesPool(records=entries),
        texts=TextsPool(records=()),
    )


def _an_entry(entnum: str) -> Record:
    return Record(
        tag="entry", attrs={"entnum": entnum}, text="", fields={"dura": "1024", "numNotes": "0"}
    )


def _named(tag: str, **attrs: str) -> Record:
    """One details record as `mus_document` synthesises it: named, and keyed by
    the entry it hangs off rather than by a cmper pair."""
    return Record(tag=tag, attrs=attrs, text="", fields={})


def _raw(tag: int, entnum: int, inci: int = 0) -> MusDetailRecord:
    """One raw details row for `entnum`, keyed the way `entry_key` reads it:
    cmper1 is the high word, cmper2 the low one."""
    return MusDetailRecord(
        tag=tag, cmper1=entnum >> 16, cmper2=entnum & 0xFFFF, inci=inci, payload=b"\x07\x00"
    )


def _retargeted(
    details: tuple[MusDetailRecord, ...] | None, *named: Record
) -> tuple[dict[str, object], ...]:
    """The `named_by` references for entry 501, after the `.mus` retargeting."""
    document = _mus_document(named, (_an_entry("501"),))
    inspection = model.Inspection(file={"name": "x.mus"})
    model._finish(Ladder(), document, inspection, engrave_notation=False)
    model._retarget_mus_references(inspection, document, details)
    facts = inspection.entry_index["501"]
    assert isinstance(facts, dict)
    references = facts["named_by"]
    assert isinstance(references, tuple)
    return references


def test_a_mus_reference_points_at_the_numeric_row_the_tree_rendered() -> None:
    """The join this whole fix exists for. A `.mus` Records tree is built from
    the raw pool, so its rows are numeric (`1009`) and keyed by cmper pair --
    while the reference comes from the document, where the same record is
    `articAssign` keyed by entnum. Untargeted, clicking the reference is a
    silent no-op on every `.mus` that has one.
    """
    references = _retargeted(
        (_raw(TAG_ARTIC_ASSIGN, 501),), _named("articAssign", entnum="501", inci="0")
    )

    assert references[0]["tag"] == "articAssign"
    assert references[0]["tree_tag"] == str(TAG_ARTIC_ASSIGN)
    assert references[0]["tree_key"] == "(cmper1 0, cmper2 501, inci 0)"


def test_a_tuplet_reference_carries_no_inci_and_still_finds_its_row() -> None:
    """`tupletDef` is emitted with no `inci` attribute at all, so it can only
    ever match on the entry."""
    references = _retargeted((_raw(TAG_TUPLET_DEF, 501),), _named("tupletDef", entnum="501"))

    assert references[0]["tree_tag"] == str(TAG_TUPLET_DEF)
    assert references[0]["tree_key"] == "(cmper1 0, cmper2 501, inci 0)"


def test_every_verse_of_a_lyric_reference_points_at_the_one_row_that_holds_them() -> None:
    """The trap. A `lyrDataVerse` record's `inci` is a per-entry assignment
    counter that `mus_document` invents, not the raw row's incidence: one raw
    row expands into a verse record per verse, numbered 0, 1, 2. Matching those
    against a raw `inci` would name a different record for every verse but the
    first, so they all fall back to the row for their entry.
    """
    references = _retargeted(
        (_raw(TAG_LYRIC_VERSE, 501),),
        _named("lyrDataVerse", entnum="501", inci="0"),
        _named("lyrDataVerse", entnum="501", inci="1"),
        _named("lyrDataVerse", entnum="501", inci="2"),
    )

    assert len(references) == 3
    for reference in references:
        assert reference["tree_tag"] == str(TAG_LYRIC_VERSE)
        assert reference["tree_key"] == "(cmper1 0, cmper2 501, inci 0)"


def test_a_reference_with_no_row_of_its_own_is_marked_unselectable() -> None:
    """No row means no target -- never the nearest row. Pointing at the wrong
    record is worse than pointing at nothing."""
    references = _retargeted((), _named("articAssign", entnum="501", inci="0"))

    assert references[0]["tree_tag"] is None
    assert references[0]["tree_key"] is None


def test_a_document_whose_details_pool_would_not_read_has_no_selectable_reference() -> None:
    """The 2001-2005 era: the tree is built from ETF rows instead, and no row
    in it corresponds to a detail record. Every reference is unselectable, and
    that is the correct answer rather than a gap."""
    references = _retargeted(None, _named("articAssign", entnum="501", inci="0"))

    assert references[0]["tree_tag"] is None
    assert references[0]["tree_key"] is None


def _synthetic_mus(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    details: tuple[MusDetailRecord, ...],
    document: EnigmaDocument,
) -> Path:
    """A path whose whole `.mus` pipeline is stubbed with records built here.

    The tests above call `_retarget_mus_references` directly, which pins the
    join but not the call site: with the call removed from the pipeline the
    entire non-corpus suite stayed green, and the only thing that noticed was a
    corpus sweep skipped wherever `corpus/` is absent -- CI included. These
    drive `inspect_document` instead, so the wiring is what is under test.
    """
    from finale_file_parser.enigma.mus_payload import MusPool

    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())
    monkeypatch.setattr(model, "read_mus_pools", lambda p: (MusPool(data=b"abc"),))
    monkeypatch.setattr(model, "read_mus_details", lambda p: details)
    monkeypatch.setattr(model, "read_mus_others", lambda p: ())
    monkeypatch.setattr(model, "read_mus_entry_records", lambda p: ())
    monkeypatch.setattr(model, "_mus_texts", lambda p: {})
    monkeypatch.setattr(model, "read_mus_document", lambda p: document)
    return path


def _one_reference(inspection: model.Inspection) -> dict[str, object]:
    """The single `named_by` reference of entry 501, as the page would get it."""
    facts = inspection.entry_index["501"]
    assert isinstance(facts, dict)
    references = facts["named_by"]
    assert isinstance(references, tuple) and len(references) == 1
    reference = references[0]
    assert isinstance(reference, dict)
    return reference


def _entry_501() -> tuple[tuple[MusDetailRecord, ...], EnigmaDocument]:
    """One raw row and the document record read from it, naming entry 501."""
    return (
        (_raw(TAG_ARTIC_ASSIGN, 501),),
        _mus_document((_named("articAssign", entnum="501", inci="0"),), (_an_entry("501"),)),
    )


def test_the_mus_pipeline_retargets_the_references_it_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end, because the join being right is worth nothing if nothing
    calls it: this fails if the retarget is dropped from `_mus_stages`.

    It also checks the target names a row the Records tree actually rendered,
    rather than only that the two fields changed -- a reference pointing at a
    row that is not there is the state the whole feature exists to remove.
    """
    details, document = _entry_501()
    path = _synthetic_mus(monkeypatch, tmp_path, details, document)

    inspection = model.inspect_document(path, engrave_notation=False)

    reference = _one_reference(inspection)
    assert reference["tree_tag"] == str(TAG_ARTIC_ASSIGN)
    assert reference["tree_key"] == "(cmper1 0, cmper2 501, inci 0)"

    rendered = inspection.records["details"]
    assert isinstance(rendered, dict)
    rows = rendered[str(TAG_ARTIC_ASSIGN)]
    assert isinstance(rows, list)
    assert [row["key"] for row in rows] == [reference["tree_key"]]


def test_a_pipeline_that_stops_at_the_score_has_still_retargeted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`build score` halts the ladder, and it fails on exactly the documents
    this report is for. The retarget runs before it for that reason: recorded
    as SKIPPED instead, it would leave every reference carrying the `.musx`
    identity, clickable and selecting nothing.
    """
    details, document = _entry_501()
    path = _synthetic_mus(monkeypatch, tmp_path, details, document)
    monkeypatch.setattr(
        model, "build_score", lambda d: (_ for _ in ()).throw(FinaleFileError("no staves"))
    )

    inspection = model.inspect_document(path, engrave_notation=False)

    by_name = {s.name: s for s in inspection.stages}
    assert by_name["build score"].status == REFUSED
    assert by_name["retarget references"].status == OK
    assert _one_reference(inspection)["tree_tag"] == str(TAG_ARTIC_ASSIGN)


def test_a_details_reader_bug_is_a_crashed_stage_and_not_a_lost_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `RuntimeError` out of `read_mus_details` is a bug in this reader, and
    a bug in this reader is what this tool is for finding. Read outside the
    ladder it escaped `inspect_document` and no report was written at all --
    which inverts the module's one promise.
    """
    details, document = _entry_501()
    path = _synthetic_mus(monkeypatch, tmp_path, details, document)
    monkeypatch.setattr(
        model, "read_mus_details", lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    inspection = model.inspect_document(path, engrave_notation=False)

    by_name = {s.name: s for s in inspection.stages}
    assert by_name["read details pool"].status == CRASHED
    assert "RuntimeError" in (by_name["read details pool"].error or "")
    assert "boom" in (by_name["read details pool"].error or "")
    # The records depth reads the pool for itself when the caller has none, so
    # it meets the same bug and reports it on its own account. Both are true.
    assert by_name["read records"].status == CRASHED
    # Non-halting, so the document was still built and the report still says
    # everything it could about it.
    assert by_name["build document"].status == OK
    assert inspection.entry_index


def test_a_musx_details_record_says_whose_entry_facts_it_is_showing() -> None:
    """`entnum` is the field the "named by" join runs on, so every entry-keyed
    details record carries one -- `articAssign`, `lyrDataVerse`, `tupletDef`.
    In a `.musx` those records are rendered by the same function the entries
    pool is, and the page shows entry facts for any record carrying an
    `entnum`. Selecting an articulation therefore rendered an *entry's* pitch
    and duration underneath it, unattributed, as though they were the
    articulation's own.

    The facts are worth showing there -- an articulation on a note whose pitch
    you cannot see is half an answer -- so the block is attributed rather than
    suppressed, and the wording is composed here rather than in the page.
    """
    document = _mus_document((_named("articAssign", entnum="501", inci="0"),), (_an_entry("501"),))

    records = model._musx_records(document)

    details = records["details"]
    assert isinstance(details, dict)
    (artic,) = details["articAssign"]
    assert artic["entnum"] == "501", "the join still needs the number"
    note = artic["entry_facts_note"]
    assert isinstance(note, str)
    assert "501" in note, "it names the entry the facts belong to"

    entries = records["entries"]
    assert isinstance(entries, dict)
    (entry,) = entries["entry"]
    assert entry["entnum"] == "501"
    assert "entry_facts_note" not in entry, "an entry's own facts need no attribution"


def test_a_bug_building_the_entry_index_is_a_crashed_stage_with_its_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`build_entry_index` does not raise by construction, so if it ever does,
    that is a bug in this reader -- which is the thing this tool exists to
    find. Caught by a bare `except` it became one fixed sentence in `notes`,
    with the exception's type and message thrown away and no stage to see: a
    reader would take it for a limitation rather than a crash, and a sweep
    scanning `stages` for CRASHED could not count it at all.

    `halt=False`, because the index is a depth beside the pipeline rather than
    a value the score stages consume: the report is still written and the
    stages after it still run.
    """
    details, document = _entry_501()
    path = _synthetic_mus(monkeypatch, tmp_path, details, document)
    monkeypatch.setattr(
        model, "build_entry_index", lambda d: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    inspection = model.inspect_document(path, engrave_notation=False)

    by_name = {s.name: s for s in inspection.stages}
    assert by_name["build entry facts"].status == CRASHED
    assert "RuntimeError" in (by_name["build entry facts"].error or "")
    assert "boom" in (by_name["build entry facts"].error or "")
    assert by_name["build score"].status in (OK, REFUSED), "the ladder was not halted"
    assert inspection.entry_index == {}


def test_a_crash_building_a_details_row_costs_the_targets_and_not_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_mus_detail_entry` walks a payload the file supplied, and the retarget
    runs it a second time over the same payloads. A `ValueError` there was
    recorded correctly by the records rung and then escaped from the retarget,
    which ran outside the ladder.

    The references it never reached are left unselectable rather than half
    targeted: the page must not offer a click that finds nothing.
    """
    details, document = _entry_501()
    path = _synthetic_mus(monkeypatch, tmp_path, details, document)
    monkeypatch.setattr(
        model, "_mus_detail_entry", lambda r: (_ for _ in ()).throw(ValueError("hostile payload"))
    )

    inspection = model.inspect_document(path, engrave_notation=False)

    by_name = {s.name: s for s in inspection.stages}
    assert by_name["read records"].status == CRASHED
    assert by_name["retarget references"].status == CRASHED
    assert "ValueError" in (by_name["retarget references"].error or "")
    reference = _one_reference(inspection)
    assert reference["tree_tag"] is None
    assert reference["tree_key"] is None


def test_the_budget_takes_the_reference_targets_with_the_records() -> None:
    """Dropping the Records tree does not drop the entry index -- but the rows
    its references name are gone, so the references stop naming them. Left
    alone, every reference on an over-budget report renders as a click that
    finds nothing.
    """
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0"})
    inspection.records = {"details": {"1009": [{"key": "A" * 2000}]}}
    inspection.entry_index = {
        "501": {
            "named_by": (
                {
                    "pool": "details",
                    "tag": "articAssign",
                    "key": "(entnum 501, inci 0)",
                    "tree_tag": "1009",
                    "tree_key": "(cmper1 0, cmper2 501, inci 0)",
                },
            )
        }
    }

    apply_budget(inspection, limit=500)

    assert inspection.records == {}
    assert inspection.entry_index, "the index is small, and it is not what went"
    reference = _one_reference(inspection)
    assert reference["tree_tag"] is None
    assert reference["tree_key"] is None
    assert any("shown as text" in note for note in inspection.notes)


def test_the_entry_index_is_dropped_last_rather_than_never() -> None:
    """The budget is a guarantee, and it can only be one if everything large is
    droppable. The index is not small by construction: its size is
    `64 placements x entries + details + unresolved messages`, and every one of
    those counts comes out of the file, so a document can make it exceed the
    budget on its own. Kept ahead of `records` and `music`, which is still
    right -- it is small next to them in the ordinary case -- but not exempt.
    """
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0"})
    inspection.records = {"others": {"measSpec": [{"key": "A" * 2000}]}}
    inspection.music = {"parts": []}
    inspection.entry_index = {"9": {"unresolved": ["C" * 2000]}}

    apply_budget(inspection, limit=500)

    assert inspection.records == {}
    assert inspection.music is None
    assert inspection.entry_index == {}, "nothing left to drop is not an answer"
    assert any("entry index" in note for note in inspection.notes)


def test_the_entry_index_survives_a_budget_the_other_two_depths_satisfy() -> None:
    """Dropping it first would empty the pane this feature exists for while the
    two depths that are far larger stayed."""
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0"})
    inspection.records = {"others": {"measSpec": [{"key": "A" * 2000}]}}
    inspection.entry_index = {"9": {"unresolved": ["short"]}}

    apply_budget(inspection, limit=500)

    assert inspection.records == {}
    assert inspection.entry_index, "the index is small here, and it is not what went"


def test_a_document_level_entry_failure_is_named_in_the_notes() -> None:
    """Failures belonging to no single entry are filed under a reserved key that
    is not an entry number, and no record row carries it -- so without this the
    most useful diagnostic the index produces had no surface anywhere in the
    report."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    document = _mus_document((gfhold,), (_an_entry("9"),))
    inspection = model.Inspection(file={"name": "x.mus"})
    model._finish(Ladder(), document, inspection, engrave_notation=False)

    assert any("frameSpec 12, which is absent" in note for note in inspection.notes)


def test_document_level_failures_stop_after_the_note_cap() -> None:
    """A hostile file can carry thousands of broken frames, and every one of
    them would otherwise be copied into the notes the page renders. The full
    list stays under the reserved document key in the index."""
    broken = tuple(
        Record(
            tag="gfhold",
            attrs={"cmper1": "1", "cmper2": str(measure)},
            text="",
            fields={"frame1": "12"},
        )
        for measure in range(model._MAX_ENTRY_FACT_NOTES + 5)
    )
    document = _mus_document(broken, (_an_entry("9"),))
    inspection = model.Inspection(file={"name": "x.mus"})
    model._finish(Ladder(), document, inspection, engrave_notation=False)

    assert len(inspection.notes) == model._MAX_ENTRY_FACT_NOTES + 1
    assert inspection.notes[-1].startswith("... and 5 further")
