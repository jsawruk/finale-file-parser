"""Inspecting every corpus document, and agreeing with the sweeps that already
pin what builds.

The corpus is walked **once**, into a module-scoped fixture. Three tests each
inspecting all 639 documents would run the whole pipeline three times over; this
project cut its suite from 34 minutes to about 5 by removing exactly that
pattern, and reintroducing it here would undo a chunk of it.

Report counts only -- never a corpus filename, title, or record value.
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

Deliberately the same number the `.mus` and `.musx` sweeps pin between them: 401
`.musx` (`test_document_corpus_sweep.py`), 99 2011-era `.mus`
(`test_mus_rows_corpus_sweep.py`), and 131 of 139 2001-2005 `.mus`
(`test_mus_dcl_score_corpus_sweep.py`). This asserts the two **agree**: the
report must not develop its own opinion of what builds, because two independent
counts of one thing drift.
"""

CRASHES = 0
"""Documents where a reader raised something other than a FinaleFileError.

A crash is a reader bug rather than a bad file. Zero today, pinned so the next
one is a regression rather than a statistic.
"""


@pytest.fixture(scope="module")
def inspections() -> list[Inspection]:
    """Every corpus document, inspected once."""
    return [inspect_document(path) for path in corpus_paths(".mus") + corpus_paths(".musx")]


def test_every_corpus_document_inspects_without_raising(
    inspections: list[Inspection],
) -> None:
    """Report generation never fails -- including on the documents that do not
    build, which are the ones it exists for."""
    assert len(inspections) == len(corpus_paths(".mus")) + len(corpus_paths(".musx"))
    for inspection in inspections:
        assert inspection.stages, "a document produced no ladder at all"


def test_the_report_agrees_with_the_sweeps_about_what_builds(
    inspections: list[Inspection],
) -> None:
    built = 0
    for inspection in inspections:
        stages = {stage.name: stage.status for stage in inspection.stages}
        built += stages.get("build score") == OK
    assert built == DOCUMENTS_THAT_BUILD


def test_no_corpus_document_crashes_a_reader(inspections: list[Inspection]) -> None:
    """See `CRASHES`."""
    crashed = sum(
        any(stage.status == CRASHED for stage in inspection.stages) for inspection in inspections
    )
    assert crashed == CRASHES


def test_a_report_renders_for_a_document_that_does_not_build(
    inspections: list[Inspection],
) -> None:
    """The tool is most informative when the file is most broken."""
    for inspection in inspections:
        if any(stage.status in {REFUSED, CRASHED} for stage in inspection.stages):
            assert render_html(inspection).startswith("<!doctype html>")
            return
    pytest.fail("no failing corpus document found to render")
