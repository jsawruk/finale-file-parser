"""Tests for the `finale-parser` command.

The stable score reader is stubbed, so these cover the CLI's own decisions: which files it
finds, where output goes, what it refuses to overwrite, and what a batch does
when one document will not build. Those are the parts a user meets first and the
parts no corpus sweep exercises.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from defusedxml import ElementTree as DET

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
    monkeypatch.setattr(cli, "read_score", lambda path: _SCORE)
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


def test_convert_writes_pdf_when_asked(tmp_path: Path, stub: None, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`--format` picks the writer *and* the suffix. Those two travelling apart
    is how you get MusicXML in a file called `.pdf`."""
    monkeypatch.setattr(cli, "to_pdf", lambda score: b"%PDF-stub")
    source = touch(tmp_path / "a.mus")
    assert cli.main(["convert", str(source), "--format", "pdf"]) == cli.EXIT_OK
    assert (tmp_path / "a.pdf").read_bytes() == b"%PDF-stub"
    assert not (tmp_path / "a.musicxml").exists(), "wrote MusicXML as well as PDF"


def test_convert_still_writes_musicxml_by_default(tmp_path: Path, stub: None) -> None:
    """Adding a format must not change what the command already did."""
    source = touch(tmp_path / "a.mus")
    assert cli.main(["convert", str(source)]) == cli.EXIT_OK
    assert (tmp_path / "a.musicxml").exists()
    assert not (tmp_path / "a.pdf").exists()


def test_a_pdf_batch_keeps_the_tree_and_the_suffix(tmp_path: Path, stub: None, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A directory of scores keeps its layout, as MusicXML batches already do --
    an archive's folders are usually part of how it is catalogued."""
    monkeypatch.setattr(cli, "to_pdf", lambda score: b"%PDF-stub")
    root = tmp_path / "in"
    touch(root / "book" / "a.mus")
    out = tmp_path / "out"
    assert cli.main(["convert", str(root), "-o", str(out), "--format", "pdf"]) == cli.EXIT_OK
    assert (out / "book" / "a.pdf").exists()


def test_an_unknown_format_is_refused(tmp_path: Path, stub: None) -> None:
    source = touch(tmp_path / "a.mus")
    with pytest.raises(SystemExit):
        cli.main(["convert", str(source), "--format", "postscript"])


def test_convert_uses_the_stable_score_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = touch(tmp_path / "a.mus")
    monkeypatch.setattr(cli, "read_score", lambda path: _SCORE)
    monkeypatch.setattr(cli, "to_musicxml", lambda score: b"<score/>")

    assert cli.main(["convert", str(source)]) == cli.EXIT_OK


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

    def load(path: Path) -> Score:
        if path.name == "bad.mus":
            raise FinaleFileError("no music the frames reach")
        return _SCORE

    monkeypatch.setattr(cli, "read_score", load)
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


def test_terminal_inspect_uses_the_stable_score_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = touch(tmp_path / "a.musx")
    monkeypatch.setattr(cli, "detect_version", lambda path: _Version())
    monkeypatch.setattr(cli, "read_score", lambda path: _SCORE)

    assert cli.main(["inspect", str(source)]) == cli.EXIT_OK


def test_inspect_reports_a_score_that_does_not_build(
    tmp_path: Path, stub: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finale_file_parser.errors import FinaleFileError

    def load(path: Path) -> Score:
        raise FinaleFileError("entry 402 placed twice at staff 3 measure 12 layer 1")

    monkeypatch.setattr(cli, "read_score", load)
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


def test_force_overwrites_a_report(tmp_path: Path, stub: None) -> None:
    """Pass --force to overwrite an existing report."""
    source = touch(tmp_path / "a.mus")
    report = tmp_path / "out.html"
    report.write_text("MINE")
    assert cli.main(["inspect", str(source), "--report", str(report), "--force"]) == cli.EXIT_OK
    assert report.read_text().startswith("<!doctype html>")


def test_a_control_character_in_a_filename_still_writes_a_parseable_report(
    tmp_path: Path, stub: None
) -> None:
    """A filename POSIX allows and macOS accepts. XML 1.0 forbids a C0 control
    in character data even as a character reference, and `html.escape` leaves it
    alone, so the report used to be written and then refuse to parse."""
    source = touch(tmp_path / "ctl\x01x.mus")
    report = tmp_path / "out.html"
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_OK
    html = report.read_text(encoding="utf-8")
    DET.fromstring(html[html.index("<html") :])


def test_a_filename_that_is_not_utf8_still_writes_a_parseable_report(
    tmp_path: Path, stub: None
) -> None:
    """`os.fsdecode` turns a filename byte that is not valid UTF-8 into a lone
    surrogate, which cannot be encoded back out as UTF-8 -- so writing the page
    raised `UnicodeEncodeError`, a `ValueError` the `except OSError` guard does
    not catch, and the CLI exited with a traceback. Linux accepts such a name and
    is what CI runs; APFS rejects it, so locally this skips rather than lies (see
    `test_a_filename_that_is_not_valid_utf8_can_still_be_written_out` in
    `tests/report/test_html.py`, which covers the same fix without a
    filesystem)."""
    try:
        source = touch(tmp_path / os.fsdecode(b"bad\xff.mus"))
    except (OSError, UnicodeEncodeError):
        pytest.skip("this filesystem refuses a name that is not valid UTF-8")
    report = tmp_path / "out.html"
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_OK
    html = report.read_text(encoding="utf-8")
    DET.fromstring(html[html.index("<html") :])


def test_inspect_write_failure_is_reported(
    tmp_path: Path, stub: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Write failures produce a clean error, not a traceback."""
    source = touch(tmp_path / "a.mus")
    # Create a file where the parent directory should be
    report_dir = tmp_path / "afile"
    report_dir.write_bytes(b"")
    # Try to write a report with afile/out.html as parent is not a directory
    report = report_dir / "out.html"
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_USAGE
    assert not report.exists()
    stderr = capsys.readouterr().err
    assert "cannot write" in stderr
    assert "afile" in stderr


def test_convert_write_failure_is_skipped(
    tmp_path: Path, stub: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Convert write failures skip the file but continue the batch."""
    source = touch(tmp_path / "a.mus")
    # Create a file where the parent directory should be
    out_dir = tmp_path / "afile"
    out_dir.write_bytes(b"")
    assert cli.main(["convert", str(source), "-o", str(out_dir), "-v"]) == cli.EXIT_FAILURES
    output = capsys.readouterr()
    assert "0/1 converted" in output.out
    assert "skipped" in output.err
