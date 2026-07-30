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
from corpus_files import corpus_paths, oracle_pairs

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Score


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
