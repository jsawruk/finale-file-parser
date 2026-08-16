"""Unit tests for `test_inspect_corpus_sweep`'s summarising helpers and its
`_guarded` wrapper -- run independently of the corpus, and never skipped.

`test_inspect_corpus_sweep.py` skips entirely when `corpus/` is absent, and
`corpus/` is gitignored, so CI never has one: every claim that file's own
docstring makes about never leaking corpus content, across three rounds of
review, was previously provable only by hand on a machine with the corpus
present. This file builds synthetic `Inspection` objects in process -- no
corpus, no `skipif` -- so the same guarantee is something CI checks on every
push.

Report counts only -- never a corpus filename, title, or record value. This
file has no *real* corpus content to leak, but it tests the mechanism that
protects it, so the synthetic stand-in (`LEAK_CANARY`) is deliberately
distinctive: if it ever appears in a failure message this suite prints, that
is not a coincidence.
"""

from __future__ import annotations

import pytest

from finale_file_parser.report import Inspection
from finale_file_parser.report.ladder import CRASHED, OK, REFUSED, Stage
from report.test_inspect_corpus_sweep import (
    CorpusDigest,
    _all_have_ladders,
    _count_built,
    _count_crashed,
    _count_documents,
    _guarded,
    _is_failing,
    _render_check,
    _rungs,
)


def _digest(*inspections: Inspection) -> CorpusDigest:
    """A digest built the way the corpus fixture builds one.

    Goes through `_rungs` and `_is_failing` rather than hand-writing the tuples,
    so these tests exercise the same reduction the sweep runs and cannot drift
    from it.
    """
    first_failing = next((i for i in inspections if _is_failing(i)), None)
    return CorpusDigest(
        ladders=tuple(_rungs(i) for i in inspections),
        first_failing=first_failing,
    )


LEAK_CANARY = "LEAK_CANARY.mus"
"""Distinctive enough that its presence anywhere is never a coincidence."""

_CANARY_SHA = "deadbeefcanary0123456789abcdef"
_CANARY_RECORD_VALUE = "CANARY_RECORD_VALUE_DO_NOT_LEAK"


def _built() -> Inspection:
    return Inspection(
        file={"name": LEAK_CANARY, "size": "1", "sha256": _CANARY_SHA},
        stages=[Stage("build score", OK, {"parts": "1"})],
        records={"others": {"canary": [{"fields": _CANARY_RECORD_VALUE}]}},
    )


def _refused() -> Inspection:
    return Inspection(
        file={"name": LEAK_CANARY, "size": "1", "sha256": _CANARY_SHA},
        stages=[Stage("build document", REFUSED, {}, error="refused for test")],
    )


def _crashed() -> Inspection:
    return Inspection(
        file={"name": LEAK_CANARY, "size": "1", "sha256": _CANARY_SHA},
        stages=[Stage("build document", CRASHED, {}, error="crashed for test")],
    )


def _no_ladder() -> Inspection:
    return Inspection(file={"name": LEAK_CANARY})


def test_count_documents_counts_every_ladder() -> None:
    assert _count_documents(_digest(_built(), _refused(), _crashed())) == 3
    assert _count_documents(_digest()) == 0


def test_count_built_counts_only_ok_build_score_stages() -> None:
    assert _count_built(_digest(_built(), _refused(), _crashed())) == 1
    assert _count_built(_digest(_refused(), _crashed())) == 0
    assert _count_built(_digest()) == 0


def test_count_crashed_counts_only_crashed_stages() -> None:
    assert _count_crashed(_digest(_built(), _refused(), _crashed())) == 1
    assert _count_crashed(_digest(_built(), _refused())) == 0
    assert _count_crashed(_digest()) == 0


def test_all_have_ladders_is_false_only_when_one_has_no_stages() -> None:
    assert _all_have_ladders(_digest(_built(), _refused())) is True
    assert _all_have_ladders(_digest(_built(), _no_ladder())) is False
    assert _all_have_ladders(_digest()) is True


def test_render_check_finds_the_first_refused_or_crashed_document() -> None:
    found, renders = _render_check(_digest(_built(), _refused()))
    assert found is True
    assert renders is True

    found, renders = _render_check(_digest(_built(), _crashed()))
    assert found is True
    assert renders is True

    found, renders = _render_check(_digest(_built()))
    assert found is False
    assert renders is False


def test_a_ladder_reduces_to_names_and_statuses_and_nothing_else() -> None:
    """The reduction is what keeps 639 documents out of memory, and it is also
    what keeps corpus text out of `ladders`. Both halves are worth pinning: an
    `Inspection` carries the document's filename, its record values and its
    whole music tree, and none of that may survive into the digest.
    """
    rungs = _rungs(_built())
    assert rungs == (("build score", OK),)
    # Nothing corpus-derived came along for the ride.
    flattened = " ".join(name + status for name, status in rungs)
    assert LEAK_CANARY not in flattened
    assert _CANARY_RECORD_VALUE not in flattened
    assert _CANARY_SHA not in flattened


def test_only_a_failing_document_is_kept_whole() -> None:
    """`first_failing` is the one `Inspection` a digest holds -- the render
    check needs a real one -- so it must be the *first* failing document and
    must stay absent when every document built."""
    assert _digest(_built(), _built()).first_failing is None

    refused, crashed = _refused(), _crashed()
    assert _digest(_built(), refused, crashed).first_failing is refused
    assert _digest(_built(), crashed).first_failing is crashed


@pytest.fixture
def digest() -> CorpusDigest:
    """Shadows `test_inspect_corpus_sweep`'s fixture of the same name, scoped
    to this module only: `_guarded` calls
    `request.getfixturevalue("digest")`, and this lets the guard test
    below use the real `pytest.FixtureRequest` machinery -- the same code path
    the corpus sweep uses -- without needing a corpus or a hand-rolled fake.

    Holds a *failing* document, so `first_failing` is populated: that is the
    one corpus-derived thing a digest still carries, and so the only thing the
    guard below can meaningfully be tested against."""
    return _digest(_refused())


def test_guarded_converts_a_raise_into_a_path_free_assertion_error(
    request: pytest.FixtureRequest,
) -> None:
    """The point of `_guarded`: prove what pytest would actually print, using
    pytest's own machinery (`pytest.raises` plus `ExceptionInfo.getrepr`),
    rather than asserting on a hand-picked message and hoping it matches.
    """

    def _raises(digest: CorpusDigest) -> int:
        # A genuine parameter of this frame, exactly like `_count_built` and
        # its siblings -- the leak this guards against is a crash frame's own
        # parameter list, so the canary must actually be bound as one here.
        # Read from `digest` at runtime rather than closing over
        # `LEAK_CANARY` as a literal: a literal would appear in pytest's
        # source-code excerpt regardless of what `_guarded` does, which would
        # test this file's own source listing, not the real risk -- a bug
        # whose exception message embeds a real, runtime-only corpus filename.
        #
        # It reaches through `first_failing` because that is now the only
        # corpus-derived thing a digest holds. If that field is ever removed,
        # this line stops compiling rather than silently testing nothing.
        assert digest.first_failing is not None
        raise RuntimeError(f"synthetic failure holding {digest.first_failing.file['name']}")

    with pytest.raises(AssertionError) as excinfo:
        _guarded(request, _raises)

    assert "corpus content withheld" in str(excinfo.value)

    # funcargs=True matches what pytest actually prints for a failing test
    # (_pytest.nodes.Node._repr_failure_py hard-codes it), independent of
    # --showlocals -- so this is what the terminal would show, not a guess.
    # `compute.__name__` ("_raises") and the f-string's own template text are
    # fine to show -- they are source code, not corpus content, and pytest's
    # source-code excerpt shows them regardless of what `_guarded` does. What
    # must not survive `from None` is `LEAK_CANARY` itself, which only ever
    # reaches the message through `inspections[0].file['name']` at runtime.
    formatted = str(excinfo.getrepr(funcargs=True))
    assert LEAK_CANARY not in formatted
