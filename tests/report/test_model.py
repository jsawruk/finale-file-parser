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

import pytest

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.report import model
from finale_file_parser.report.ladder import CRASHED, OK, REFUSED, SKIPPED

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

    def crash(target: Path) -> dict[str, object]:
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
                # A `.mus` record carries `fields` -- the decoding of its bytes;
                # a `.musx` record carries `xml` instead, which is both its
                # source and its decoding.
                assert entry.keys() in ({"key", "fields", "length"}, {"key", "xml", "length"})
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
    assert _musx_key(gfhold, 7) == "3/12"

    with_inci = Record(
        tag="crossChord", attrs={"cmper1": "3", "cmper2": "12", "inci": "1"}, text="", fields={}
    )
    assert _musx_key(with_inci, 7) == "3/12/1"

    entry = Record(tag="entry", attrs={"entnum": "41", "next": "42"}, text="", fields={})
    assert _musx_key(entry, 7) == "41", "`next` is a link, not identity"

    text = Record(tag="expression", attrs={"number": "5"}, text="", fields={})
    assert _musx_key(text, 7) == "5"

    ordinary = Record(tag="measSpec", attrs={"cmper": "2", "inci": "0"}, text="", fields={})
    assert _musx_key(ordinary, 7) == "2/0", "unchanged for records that were already right"

    anonymous = Record(tag="header", attrs={}, text="", fields={})
    assert _musx_key(anonymous, 7) == "7", "position is still the fallback when nothing names it"


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
