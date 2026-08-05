"""Tests for the stage ladder."""

from __future__ import annotations

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.inspect.ladder import CRASHED, OK, REFUSED, SKIPPED, Ladder


def test_a_stage_that_succeeds_records_its_detail() -> None:
    ladder = Ladder()
    value = ladder.run("read", lambda: 7, lambda v: {"count": str(v)})
    assert value == 7
    assert [(s.name, s.status) for s in ladder.stages] == [("read", OK)]
    assert ladder.stages[0].detail == {"count": "7"}


def test_a_reader_that_refuses_is_recorded_as_refused() -> None:
    """A FinaleFileError means the reader deliberately declined the file."""
    ladder = Ladder()

    def refuse() -> int:
        raise FinaleFileError("no frame holds; the document carries no music")

    assert ladder.run("read", refuse) is None
    assert ladder.stages[0].status == REFUSED
    assert "no frame holds" in (ladder.stages[0].error or "")


def test_any_other_exception_is_recorded_as_a_crash() -> None:
    """Not a bad file -- a reader bug, and the report must say which."""
    ladder = Ladder()

    def crash() -> int:
        raise IndexError("index out of range")

    assert ladder.run("read", crash) is None
    assert ladder.stages[0].status == CRASHED
    assert "IndexError" in (ladder.stages[0].error or "")


def test_stages_after_a_failure_are_skipped_not_attempted() -> None:
    """The ladder stops. A later stage must not run against a value that was
    never produced, and must not look like it passed."""
    ladder = Ladder()
    ladder.run("first", lambda: (_ for _ in ()).throw(FinaleFileError("nope")))
    ran = []
    ladder.run("second", lambda: ran.append(1))
    assert ran == []
    assert [s.status for s in ladder.stages] == [REFUSED, SKIPPED]
