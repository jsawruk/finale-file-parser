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

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Score


def musx_paths() -> list[Path]:
    return corpus_paths(".musx")


def mus_paths() -> list[Path]:
    return corpus_paths(".mus")


def stem_pairs() -> list[tuple[Path, Path]]:
    """`.mus`/`.musx` sharing a filename stem, in stem order.

    **Deliberately left on the old walk**, case-sensitive glob and all, because
    which oracle a `.mus` is compared against is not well defined here and this
    is not the change to redefine it in. 401 `.musx` files share only 123 stems,
    so 278 of them are shadowed, and `{p.stem: p}` keeps whichever the walk
    yielded last. Making the walk case insensitive also reorders it, which
    silently swaps the oracle under a third of the pairs -- moving one sweep's
    agreement from 91 documents to 84 with no bug in sight. Widening this needs
    pairing that names one document, not a re-glob. See the note in
    `corpus_files.corpus_paths`.
    """
    mus = {p.stem: p for p in CORPUS.rglob("*.mus")}
    musx = {p.stem: p for p in CORPUS.rglob("*.musx")}
    return [(mus[s], musx[s]) for s in sorted(set(mus) & set(musx))]


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


@pytest.fixture(scope="session")
def paired_scores() -> PairedCorpus:
    """(`.mus`, `.musx`) for stem-matched pairs holding the **same music**.

    A shared filename stem is not enough: some pairs are different arrangements
    entirely. Matching the entry count is the filter every container comparison
    in this suite has used, and it belongs here rather than repeated in each.
    """
    out = PairedCorpus()
    for mus_path, musx_path in stem_pairs():
        try:
            document = parse_enigma(score_xml(musx_path))
            if len(read_mus_entries(mus_path)) != len(document.entries.records):
                continue
        except CorruptScoreError:
            continue
        try:
            out.pairs.append((build_score(read_mus_document(mus_path)), build_score(document)))
        except Exception:  # noqa: BLE001 - the point is to count them, not to diagnose
            out.unbuildable += 1
    return out
