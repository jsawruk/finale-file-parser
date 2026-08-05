"""Tests for the `finale-parser` command.

The readers are stubbed, so these cover the CLI's own decisions: which files it
finds, where output goes, what it refuses to overwrite, and what a batch does
when one document will not build. Those are the parts a user meets first and the
parts no corpus sweep exercises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser import cli
from finale_file_parser.ir import Part, Score

_SCORE = Score(parts=(Part(id="P1", name="Flute"),))


class _Family:
    value = "musx"


class _Version:
    label = "Finale 2011"
    family = _Family()


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every document detect, build, and export to the same trivial XML."""
    monkeypatch.setattr(cli, "detect_version", lambda path: _Version())
    monkeypatch.setattr(cli, "load_document", lambda path: object())
    monkeypatch.setattr(cli, "build_score", lambda document: _SCORE)
    monkeypatch.setattr(cli, "to_musicxml", lambda score: b"<score/>")


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_the_walk_finds_both_spellings_of_mus(tmp_path: Path) -> None:
    """`rglob("*.mus")` is case sensitive on a POSIX path and would skip every
    `.MUS` -- the Windows spelling, and 101 of the 238 in this project's corpus.
    A converter that silently ignored half an archive would be worse than one
    that refused to run."""
    touch(tmp_path / "a.mus")
    touch(tmp_path / "b.MUS")
    touch(tmp_path / "c.musx")
    touch(tmp_path / "d.MUSX")
    touch(tmp_path / "notes.txt")
    assert [p.name for p in cli.source_paths(tmp_path)] == ["a.mus", "b.MUS", "c.musx", "d.MUSX"]


def test_a_single_file_is_its_own_source_list(tmp_path: Path) -> None:
    path = touch(tmp_path / "a.mus")
    assert cli.source_paths(path) == [path]


def test_output_lands_beside_the_input_by_default(tmp_path: Path) -> None:
    source = touch(tmp_path / "a.mus")
    assert cli.output_path(source, source, None) == tmp_path / "a.musicxml"


def test_output_directory_preserves_the_input_layout(tmp_path: Path) -> None:
    """Flattening a tree into one folder loses how an archive is catalogued."""
    root = tmp_path / "in"
    source = touch(root / "nested" / "deep" / "a.mus")
    out = tmp_path / "out"
    assert cli.output_path(source, root, out) == out / "nested" / "deep" / "a.musicxml"


def test_output_names_the_file_when_the_input_is_one(tmp_path: Path) -> None:
    source = touch(tmp_path / "a.mus")
    named = tmp_path / "somewhere" / "renamed.musicxml"
    assert cli.output_path(source, source, named) == named


def test_converts_a_single_file(tmp_path: Path, stub: None) -> None:
    source = touch(tmp_path / "a.mus")
    assert cli.main(["convert", str(source)]) == cli.EXIT_OK
    assert (tmp_path / "a.musicxml").read_bytes() == b"<score/>"


def test_refuses_to_overwrite_without_force(tmp_path: Path, stub: None) -> None:
    """Conversion is cheap to repeat; a clobbered file is not."""
    source = touch(tmp_path / "a.mus")
    existing = tmp_path / "a.musicxml"
    existing.write_bytes(b"MINE")
    assert cli.main(["convert", str(source)]) == cli.EXIT_FAILURES
    assert existing.read_bytes() == b"MINE"


def test_force_overwrites(tmp_path: Path, stub: None) -> None:
    source = touch(tmp_path / "a.mus")
    existing = tmp_path / "a.musicxml"
    existing.write_bytes(b"MINE")
    assert cli.main(["convert", str(source), "--force"]) == cli.EXIT_OK
    assert existing.read_bytes() == b"<score/>"


def test_a_batch_continues_past_a_document_that_will_not_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole reason this tool exists is collections. Someone converting 300
    scores needs the 292 that work, so one failure reports and is skipped."""
    from finale_file_parser.errors import FinaleFileError

    root = tmp_path / "in"
    touch(root / "bad.mus")
    touch(root / "good.mus")

    def load(path: Path) -> object:
        if path.name == "bad.mus":
            raise FinaleFileError("no music the frames reach")
        return object()

    monkeypatch.setattr(cli, "load_document", load)
    monkeypatch.setattr(cli, "build_score", lambda document: _SCORE)
    monkeypatch.setattr(cli, "to_musicxml", lambda score: b"<score/>")

    out = tmp_path / "out"
    assert cli.main(["convert", str(root), "-o", str(out)]) == cli.EXIT_FAILURES
    assert (out / "good.musicxml").exists()
    assert not (out / "bad.musicxml").exists()


def test_a_missing_path_is_a_usage_error(tmp_path: Path) -> None:
    assert cli.main(["convert", str(tmp_path / "nope")]) == cli.EXIT_USAGE


def test_a_directory_holding_no_finale_files_is_a_usage_error(tmp_path: Path) -> None:
    """Distinct from "converted 0 of 0", which reads like success."""
    (tmp_path / "empty").mkdir()
    assert cli.main(["convert", str(tmp_path / "empty")]) == cli.EXIT_USAGE


def test_inspect_reports_a_score_that_builds(
    tmp_path: Path, stub: None, capsys: pytest.CaptureFixture[str]
) -> None:
    source = touch(tmp_path / "a.musx")
    assert cli.main(["inspect", str(source)]) == cli.EXIT_OK
    assert "score" in capsys.readouterr().out


def test_inspect_reports_a_score_that_does_not_build(
    tmp_path: Path, stub: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finale_file_parser.errors import FinaleFileError

    def load(path: Path) -> object:
        raise FinaleFileError("entry 402 placed by more than one frame")

    monkeypatch.setattr(cli, "load_document", load)
    source = touch(tmp_path / "a.musx")
    assert cli.main(["inspect", str(source)]) == cli.EXIT_FAILURES


def test_inspect_writes_a_report(tmp_path: Path, stub: None) -> None:
    """The report is the whole point of the flag; the terminal output stays."""
    source = touch(tmp_path / "a.mus")
    report = tmp_path / "out.html"
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_OK
    assert report.read_text().startswith("<!doctype html>")


def test_a_report_is_refused_rather_than_clobbered(tmp_path: Path, stub: None) -> None:
    """Same rule as convert: nothing is overwritten without being asked."""
    source = touch(tmp_path / "a.mus")
    report = tmp_path / "out.html"
    report.write_text("MINE")
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_USAGE
    assert report.read_text() == "MINE"


def test_report_with_directory_is_a_usage_error(tmp_path: Path, stub: None) -> None:
    """The --report flag takes exactly one file, not a directory."""
    root = tmp_path / "in"
    touch(root / "a.mus")
    touch(root / "b.mus")
    report = tmp_path / "out.html"
    assert cli.main(["inspect", str(root), "--report", str(report)]) == cli.EXIT_USAGE
    assert not report.exists()
