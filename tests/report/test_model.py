"""Tests for the inspection model.

The readers are stubbed, so these cover the ladder's shape rather than the
parser's behaviour.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.report import model
from finale_file_parser.report.ladder import OK, REFUSED, SKIPPED


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
