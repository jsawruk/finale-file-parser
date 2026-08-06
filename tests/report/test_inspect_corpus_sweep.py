"""Inspecting every corpus document, and agreeing with the sweeps that already
pin what builds.

The corpus is walked **once**, into a module-scoped fixture. Three tests each
inspecting all 639 documents would run the whole pipeline three times over; this
project cut its suite from 34 minutes to about 5 by removing exactly that
pattern, and reintroducing it here would undo a chunk of it.

Report counts only -- never a corpus filename, title, or record value. **Not
even in a failure message, under any pytest flag.** Two rules make that hold,
and both were found necessary the hard way, by deliberately breaking an
assertion and reading what pytest actually printed rather than reasoning about
it in the abstract:

* **Every aggregation is a module-level helper** (`_count_built`,
  `_count_crashed`, `_all_have_ladders`, `_render_check`) that takes
  `list[Inspection]` and returns a plain `int`, `bool`, or tuple of those. A
  test body calls one, binds the *result* to a name, and only then asserts on
  that name. The helper has already returned by the time the assert runs, so
  its own frame and its `for inspection in ...` loop variable are gone from the
  traceback -- there is nothing left to print, with or without
  `--showlocals`. Do not inline these loops back into a test function: a bare
  `for inspection in inspections:` inside a test leaves `inspection` bound
  after the loop ends, and a raising assert later in the same test prints it.

* **No fixture takes another fixture as a parameter.** `inspections` computes
  its own paths in its body via `corpus_paths(...)` directly, rather than
  depending on a `corpus_document_paths` fixture. pytest prints a fixture's own
  parameter values, unconditionally, if that fixture raises during
  construction -- no flag required -- and a walk that could plausibly fail
  (unlike the pure computation here) must not carry a parameter worth printing.

`test_every_corpus_document_inspects_without_raising` also recomputes the
document count from a fresh, independent `corpus_paths` call rather than
comparing the `inspections` fixture against itself: the earlier version
compared a list to the very count derived from building that list, which is
true by construction and can never fail.
"""

from __future__ import annotations

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.report import Inspection, inspect_document
from finale_file_parser.report.html import render_html
from finale_file_parser.report.ladder import CRASHED, OK, REFUSED

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

DOCUMENTS_THAT_BUILD = 631
"""What the report thinks builds.

Deliberately the same total the `.mus` and `.musx` sweeps pin between them:

* **401 `.musx`** -- `tests/export/test_export_audit_corpus_sweep.py::EXPORTED`.
* **131 of 139 2001-2005 (DCL) `.mus`** --
  `tests/enigma/test_mus_dcl_score_corpus_sweep.py::EXPECTED_SCORES`.
* **99 2011-era `.mus`** -- `tests/export/test_export_audit_corpus_sweep.py`'s
  `MUS_EXPORTED` (230, every `.mus` that exports) minus the 131 DCL documents
  above; that sweep does not split the two cohorts apart itself.

401 + 131 + 99 = 631. This asserts the two **agree**: the report must not
develop its own opinion of what builds, because two independent counts of one
thing drift. **If this fails, the fix is to find which side is wrong and say
so -- never to move this constant to match whatever the report produced.** A
mismatch means the report's ladder and one of the two sweeps above disagree
about a real document, and re-pinning the number would erase exactly the
disagreement this test exists to catch.
"""

CRASHES = 0
"""Documents where a reader raised something other than a FinaleFileError.

A crash is a reader bug rather than a bad file. Zero today, pinned so the next
one is a regression rather than a statistic.
"""


@pytest.fixture(scope="module")
def inspections() -> list[Inspection]:
    """Every corpus document, inspected once.

    Takes no fixture of its own: see the module docstring on why a fixture that
    depends on another fixture is worth avoiding here specifically.

    Each call is wrapped rather than left as a bare comprehension.
    `inspect_document` is built never to raise -- `Ladder.run` catches every
    reader exception and records it as a `CRASHED` stage instead -- but if a
    bug ever let one through anyway, its traceback would carry the real corpus
    path as `inspect_document`'s own argument, and pytest prints a frame's
    arguments on any exception, not only on a failing fixture parameter. `from
    None` drops that original traceback rather than chaining it in, so no path
    reaches the report even for a failure mode this file did not anticipate.
    """
    paths = corpus_paths(".mus") + corpus_paths(".musx")
    built: list[Inspection] = []
    for path in paths:
        try:
            built.append(inspect_document(path))
        except Exception as error:  # noqa: BLE001 -- deliberately broad, see docstring
            raise AssertionError(
                f"inspect_document raised {type(error).__name__} unexpectedly for a "
                "corpus document -- this should never happen, since Ladder.run "
                "catches every reader exception; corpus path withheld"
            ) from None
    return built


def _count_built(inspections: list[Inspection]) -> int:
    """Documents whose ladder reached an `OK` "build score" stage."""
    built = 0
    for inspection in inspections:
        stages = {stage.name: stage.status for stage in inspection.stages}
        built += stages.get("build score") == OK
    return built


def _count_crashed(inspections: list[Inspection]) -> int:
    """Documents where any stage's status is `CRASHED`. See `CRASHES`."""
    crashed = 0
    for inspection in inspections:
        crashed += any(stage.status == CRASHED for stage in inspection.stages)
    return crashed


def _all_have_ladders(inspections: list[Inspection]) -> bool:
    """False only if some document produced no ladder at all."""
    return all(inspection.stages for inspection in inspections)


def _render_check(inspections: list[Inspection]) -> tuple[bool, bool]:
    """`(found_a_failing_document, renders_as_html)` for the first document
    whose ladder shows `REFUSED` or `CRASHED` -- `(False, False)` if none is
    found."""
    for inspection in inspections:
        if any(stage.status in {REFUSED, CRASHED} for stage in inspection.stages):
            rendered = render_html(inspection)
            return True, rendered.startswith("<!doctype html>")
    return False, False


def test_every_corpus_document_inspects_without_raising(request: pytest.FixtureRequest) -> None:
    """Report generation never fails -- including on the documents that do not
    build, which are the ones it exists for."""
    document_count = len(corpus_paths(".mus")) + len(corpus_paths(".musx"))
    inspection_count = len(request.getfixturevalue("inspections"))
    every_document_has_a_ladder = _all_have_ladders(request.getfixturevalue("inspections"))
    assert inspection_count == document_count
    assert every_document_has_a_ladder, "a document produced no ladder at all"


def test_the_report_agrees_with_the_sweeps_about_what_builds(
    request: pytest.FixtureRequest,
) -> None:
    built = _count_built(request.getfixturevalue("inspections"))
    assert built == DOCUMENTS_THAT_BUILD


def test_no_corpus_document_crashes_a_reader(request: pytest.FixtureRequest) -> None:
    """See `CRASHES`."""
    crashed = _count_crashed(request.getfixturevalue("inspections"))
    assert crashed == CRASHES


def test_a_report_renders_for_a_document_that_does_not_build(
    request: pytest.FixtureRequest,
) -> None:
    """The tool is most informative when the file is most broken."""
    found_a_failing_document, renders_as_html = _render_check(
        request.getfixturevalue("inspections")
    )
    assert found_a_failing_document, "no failing corpus document found to render"
    assert renders_as_html, "a report for a non-building document did not render"
