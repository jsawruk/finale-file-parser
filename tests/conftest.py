"""Shared corpus fixtures.

Every corpus sweep needs the same thing: each document decoded, parsed and built
into a `Score`. Doing that per sweep is what makes the suite slow — parsing one
document costs 274 ms against 6 ms to decode it, and a single sweep file was
found walking the corpus twenty times over.

These fixtures walk it **once per worker process** and hand back the results, so
a file's tests share one walk instead of each paying for its own. Holding every
built `Score` costs about 173 MB, measured — an order of magnitude less than
holding the parsed documents, because a `Score` drops the raw records.

Session-scoped, so with `--dist loadfile` (see the Makefile) every sweep on a
worker shares the same walk.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import faulthandler
import os
import resource
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from corpus_files import corpus_paths, oracle_pairs

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Score

MEMORY_CAP_MB = int(os.environ.get("FFP_TEST_MEMORY_CAP_MB", "8192"))
"""How much a single test process may hold before it is killed.

**Why this exists.** A layout field once reported `sys.maxsize` as its end offset
and a test looped `for index in range(f.offset, f.end)`, filling a dict. Nothing
stopped it: it reached 28.8 GB, took the machine into swap and crashed it. The
bug was a one-line mistake and the blast radius was the whole computer.

`setrlimit` is not the guard -- macOS refuses `RLIMIT_AS` and `RLIMIT_DATA` here
with EINVAL -- so a thread polls this process's own high-water mark instead and
hard-exits over the cap, naming the test that did it.

**8 GB is measured, not guessed, and the first guess was wrong.** The cap started
at 3 GB, reasoned from the note above that holding every built `Score` costs
about 173 MB. That is the `musx_scores` fixture, and it is not the heaviest thing
here: `test_inspect_corpus_sweep.py` holds an `Inspection` for all 639 documents
and peaks at **3.37 GB**, measured on a clean single-process run of that file.
The 3 GB cap killed it -- a real sweep, not a runaway -- and took the xdist
worker down with it. So the cap is roughly 2.4x the true high-water mark: loose
enough that legitimate work never trips it, tight enough that a runaway dies in
seconds instead of taking the machine.

Raise it with `FFP_TEST_MEMORY_CAP_MB` if a sweep ever genuinely needs more --
and record the measured peak that justified it, as above.
"""

_POLL_SECONDS = 0.25

_current_test = "before any test"
_config: pytest.Config | None = None


def _held_bytes() -> int:
    """This process's peak resident size.

    `ru_maxrss` is bytes on macOS and kilobytes on Linux -- the same number
    would be off by 1024 on CI, which is the difference between a cap that
    fires and one that never does.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def _uncaptured_stderr() -> None:
    """Put the real stderr back on fd 2.

    pytest captures at the file-descriptor level, so a report written on the way
    out lands in a temp file it will never get to read -- the first version of
    this guard killed the process silently, which tells the next person nothing
    about what they did.
    """
    if _config is None:
        return
    capman = _config.pluginmanager.getplugin("capturemanager")
    if capman is not None:
        capman.suspend_global_capture(in_=False)


def _watch_memory() -> None:
    cap = MEMORY_CAP_MB * 1024 * 1024
    while True:
        held = _held_bytes()
        if held > cap:
            _uncaptured_stderr()
            # Written to the fd rather than through `print`: the interpreter is
            # about to stop without flushing anything.
            os.write(
                2,
                f"\nMEMORY CAP: {_current_test} reached {held / 1e9:.1f} GB, over the "
                f"{MEMORY_CAP_MB} MB cap (FFP_TEST_MEMORY_CAP_MB). "
                f"Killing this process; the stack below is where it was.\n".encode(),
            )
            faulthandler.dump_traceback()
            # _exit, not sys.exit: an exception here would be raised in this
            # thread and the test would carry on allocating.
            os._exit(9)
        time.sleep(_POLL_SECONDS)


def pytest_configure(config: pytest.Config) -> None:
    """Arm the memory guard. Runs in each xdist worker as well as the parent."""
    global _config
    _config = config
    threading.Thread(target=_watch_memory, daemon=True, name="memory-cap").start()


def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Record which test is running, so the guard can name it."""
    global _current_test
    _current_test = item.nodeid
    return None


def musx_paths() -> list[Path]:
    return corpus_paths(".musx")


def mus_paths() -> list[Path]:
    return corpus_paths(".mus")


def stem_pairs() -> list[tuple[Path, Path]]:
    """Each `.mus` with its same-music `.musx` oracle. See `corpus_files`."""
    return oracle_pairs()


@pytest.fixture(scope="session")
def musx_scores() -> list[tuple[Path, Score]]:
    """Every `.musx` that builds, with its `Score`. Undecodable ones are absent.

    The three corpus documents that fail to decode are pinned by the container
    sweeps; a sweep that needs an exact count asserts its own.
    """
    out: list[tuple[Path, Score]] = []
    for path in musx_paths():
        try:
            out.append((path, build_score(parse_enigma(score_xml(path)))))
        except CorruptScoreError:
            continue
    return out


@pytest.fixture(scope="session")
def mus_scores() -> list[tuple[Path, Score]]:
    """Every `.mus` that builds, with its `Score`.

    The legacy reader's own failures are counted by the `.mus` sweeps; here they
    are simply skipped, which is why this is a plain `Exception` — those
    failures are several distinct types and are pinned elsewhere.
    """
    out: list[tuple[Path, Score]] = []
    for path in mus_paths():
        try:
            out.append((path, build_score(read_mus_document(path))))
        except Exception:  # noqa: BLE001 - counted and pinned by the .mus sweeps
            continue
    return out


@dataclass
class PairedCorpus:
    """Same-music pairs, and a count of the ones that would not build.

    The failure count is carried rather than swallowed: a sweep pins it at 2,
    and a fixture that quietly skipped them would turn a known, named breakage
    into silence.
    """

    pairs: list[tuple[Score, Score]] = field(default_factory=list)
    unbuildable: int = 0
    reordered: int = 0
    """Pairs holding the same parts in a different order.

    Carried, not dropped quietly, for the same reason as `unbuildable`. Every
    comparison in this suite lines parts up by position, which is only meaningful
    while both sides agree on the order -- and for these the `.musx` lays its
    staves out in score order while the `.mus` reader emits them numerically
    (`mus_document.UNTRANSLATED`, the `instUsed` gap). Comparing them positionally
    measures one instrument against another: it produced 435 spurious beam
    differences before this filter existed. Excluded from `pairs`, counted here,
    and pinned by the sweeps.
    """


@pytest.fixture(scope="session")
def paired_scores() -> PairedCorpus:
    """(`.mus`, `.musx`) for stem-matched pairs holding the **same music**.

    A shared filename stem is not enough: some pairs are different arrangements
    entirely. Matching the entry count is the filter every container comparison
    in this suite has used, and it belongs here rather than repeated in each --
    `corpus_files.oracle_pairs` applies it when choosing the oracle.

    Pairs whose parts come out in a different order are held back in
    `reordered` rather than returned, because everything downstream compares
    parts by position. See that field.
    """
    out = PairedCorpus()
    for mus_path, musx_path in stem_pairs():
        try:
            document = parse_enigma(score_xml(musx_path))
        except CorruptScoreError:
            continue
        try:
            mine = build_score(read_mus_document(mus_path))
            theirs = build_score(document)
        except Exception:  # noqa: BLE001 - the point is to count them, not to diagnose
            out.unbuildable += 1
            continue
        if [part.id for part in mine.parts] != [part.id for part in theirs.parts]:
            out.reordered += 1
            continue
        out.pairs.append((mine, theirs))
    return out
