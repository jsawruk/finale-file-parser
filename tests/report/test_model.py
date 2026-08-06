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
    """So two people can confirm they are looking at the same file."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())
    monkeypatch.setattr(
        model, "read_mus_pools", lambda p: (_ for _ in ()).throw(FinaleFileError("x"))
    )
    inspection = model.inspect_document(path)
    assert inspection.file["name"] == "score.mus"
    assert inspection.file["size"] == str(len(b"not really a mus file"))
    assert len(inspection.file["sha256"]) == 64


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
    assert inspection.score is None


def test_inspecting_a_directory_still_returns() -> None:
    """`path.read_bytes()` raises `IsADirectoryError` on a directory. That must
    stop the ladder, not the function."""
    inspection = model.inspect_document(Path(__file__).parent)
    assert inspection.stages[0].name == "read file"
    assert inspection.stages[0].status == REFUSED
    assert {s.status for s in inspection.stages[1:]} == {SKIPPED}
    assert inspection.score is None


def test_inspecting_a_nonexistent_path_still_returns(tmp_path: Path) -> None:
    """`path.read_bytes()` raises `FileNotFoundError`. Same requirement."""
    inspection = model.inspect_document(tmp_path / "does-not-exist.mus")
    assert inspection.stages[0].name == "read file"
    assert inspection.stages[0].status == REFUSED
    assert {s.status for s in inspection.stages[1:]} == {SKIPPED}
    assert inspection.score is None


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
    assert inspection.score is None


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


def test_the_budget_drops_raw_before_records() -> None:
    """Score and document summaries are never truncated; raw goes first."""
    from finale_file_parser.report.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0", "sha256": ""})
    inspection.score = {
        "parts": [],
        "totals": {"parts": 1, "measures": 0, "events": 0, "pitches": 0},
    }
    inspection.raw = {"others": "A" * 2000}
    inspection.records = {"others": {"measSpec": [{"key": "1"}]}}

    apply_budget(inspection, limit=500)
    assert inspection.raw == {}
    assert inspection.score is not None
    assert any("raw" in note for note in inspection.notes)


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_a_real_mus_file_gets_raw_bytes_and_records() -> None:
    """End-to-end: the wiring populates both lower depths from a real file,
    and what it produces is actually JSON -- the shape `apply_budget` and a
    renderer both depend on."""
    path = next(CORPUS.rglob("*.mus"))
    inspection = model.inspect_document(path)

    assert inspection.raw
    assert inspection.records
    for _pool_name, by_tag in inspection.records.items():
        assert isinstance(by_tag, dict)
        for tag, entries in by_tag.items():
            assert isinstance(tag, str)
            for entry in entries:
                # No `offset`: no reader records where a record began, so the
                # field the design asked for could only ever have been null.
                assert entry.keys() == {"key", "fields", "length"}
                assert isinstance(entry["key"], str)

    # Round-trips through JSON without error: no bytes, no dataclasses left over.
    json.dumps(inspection.raw)
    json.dumps(inspection.records)


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_a_real_musx_file_gets_records_but_no_raw() -> None:
    """A `.musx` has no undecoded byte pools to embed -- only EnigmaXML's own
    records, which are already the rawest view there is."""
    path = next(CORPUS.rglob("*.musx"))
    inspection = model.inspect_document(path)

    assert inspection.raw == {}
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
