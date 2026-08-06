"""Inspecting every corpus document, and agreeing with the sweeps that already
pin what builds.

The corpus is walked **once**, into a module-scoped fixture. Three tests each
inspecting all 639 documents would run the whole pipeline three times over; this
project cut its suite from 34 minutes to about 5 by removing exactly that
pattern, and reintroducing it here would undo a chunk of it.

Report counts only -- never a corpus filename, title, or record value. **Not
even in a failure message**: no test below takes `inspections` or
`corpus_document_paths` as a parameter, and no `assert` operand is derived from
one in the same statement that asserts. Both are load-bearing. pytest prints a
failing test's own fixture *parameters* verbatim ahead of the traceback, and it
expands any function call inside a failing `assert` to show the value passed
in -- either path puts an `Inspection`'s filename, sha256 and record fields
into the failure output, which is exactly the corpus content this file must
never surface. Fetching a fixture with `request.getfixturevalue` inside the
test body avoids the first; reducing to a plain int or bool in its own
statement before the `assert`, and `del`-ing the reference, avoids the second.
"""

from __future__ import annotations

from pathlib import Path

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
def corpus_document_paths() -> list[Path]:
    """Every corpus document's path, walked once and shared: `inspections`
    inspects each one, and the count below is a slice of this list rather than
    a second directory walk."""
    return corpus_paths(".mus") + corpus_paths(".musx")


@pytest.fixture(scope="module")
def inspections(corpus_document_paths: list[Path]) -> list[Inspection]:
    """Every corpus document, inspected once."""
    return [inspect_document(path) for path in corpus_document_paths]


def test_every_corpus_document_inspects_without_raising(request: pytest.FixtureRequest) -> None:
    """Report generation never fails -- including on the documents that do not
    build, which are the ones it exists for."""
    paths = request.getfixturevalue("corpus_document_paths")
    walked = request.getfixturevalue("inspections")
    path_count = len(paths)
    inspection_count = len(walked)
    every_document_has_a_ladder = all(inspection.stages for inspection in walked)
    del paths, walked
    assert inspection_count == path_count
    assert every_document_has_a_ladder, "a document produced no ladder at all"


def test_the_report_agrees_with_the_sweeps_about_what_builds(
    request: pytest.FixtureRequest,
) -> None:
    walked = request.getfixturevalue("inspections")
    built = 0
    for inspection in walked:
        stages = {stage.name: stage.status for stage in inspection.stages}
        built += stages.get("build score") == OK
    del walked
    assert built == DOCUMENTS_THAT_BUILD


def test_no_corpus_document_crashes_a_reader(request: pytest.FixtureRequest) -> None:
    """See `CRASHES`."""
    walked = request.getfixturevalue("inspections")
    crashed = sum(
        any(stage.status == CRASHED for stage in inspection.stages) for inspection in walked
    )
    del walked
    assert crashed == CRASHES


def test_a_report_renders_for_a_document_that_does_not_build(
    request: pytest.FixtureRequest,
) -> None:
    """The tool is most informative when the file is most broken."""
    walked = request.getfixturevalue("inspections")
    found_a_failing_document = False
    renders_as_html = False
    for inspection in walked:
        if any(stage.status in {REFUSED, CRASHED} for stage in inspection.stages):
            found_a_failing_document = True
            rendered = render_html(inspection)
            renders_as_html = rendered.startswith("<!doctype html>")
            del rendered
            break
    del walked
    assert found_a_failing_document, "no failing corpus document found to render"
    assert renders_as_html, "a report for a non-building document did not render"
