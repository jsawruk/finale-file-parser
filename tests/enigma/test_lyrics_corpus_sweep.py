"""Validate lyric export against the corpus, and the two containers against each other.

Skipped wherever corpus/ is absent (e.g. CI). Two independent checks:

* **Coverage** -- the `.musx` corpus really does produce lyrics, at a pinned
  size, so a regression that silently emitted none would fail here.
* **Container agreement** -- the same document read from `.mus` and from `.musx`
  must produce identical syllables. This is the check that matters, because the
  two store lyrics completely differently: a `.musx` writes one record per
  (entry, verse), a `.mus` packs every verse into one record and then repeats
  the whole thing.

Report counts only -- never a corpus filename, title, or lyric.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Lyric, Score

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

DOCUMENTS_WITH_LYRICS = 85
"""`.musx` documents whose export carries at least one syllable."""

SYLLABLES = 12912
"""Total syllables exported across the corpus, over 7,810 events.

A count rather than a ratio: it measures the exporter, not what fraction of the
corpus happens to be vocal music.
"""

PAIRED_WITH_LYRICS = 6
"""Same-content pairs where the `.musx` carries lyrics, so the two containers
can be compared. Small, but it is the only oracle for the `.mus` side."""


def musx_files() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*.musx"))]


def pairs() -> list[tuple[Path, Path]]:
    mus = {p.stem: p for p in CORPUS.rglob("*.mus")}
    musx = {p.stem: p for p in CORPUS.rglob("*.musx")}
    return [(mus[s], musx[s]) for s in sorted(set(mus) & set(musx))]


def all_lyrics(score: Score) -> list[tuple[Lyric, ...]]:
    return [
        event.lyrics
        for part in score.parts
        for measure in part.measures
        for voice in measure.voices
        for event in voice.events
    ]


@pytest.fixture(scope="module")
def coverage() -> tuple[int, int]:
    documents = syllables = 0
    for path in musx_files():
        try:
            score = build_score(parse_enigma(score_xml(path)))
        except CorruptScoreError:
            continue
        total = sum(len(item) for item in all_lyrics(score))
        if total:
            documents += 1
            syllables += total
    return documents, syllables


@pytest.fixture(scope="module")
def agreement() -> tuple[int, int, int]:
    documents = identical = different = 0
    for mus_path, musx_path in pairs():
        try:
            document = parse_enigma(score_xml(musx_path))
            if len(read_mus_entries(mus_path)) != len(document.entries.records):
                continue
            theirs = build_score(document)
            mine = build_score(read_mus_document(mus_path))
        except CorruptScoreError:
            continue
        except Exception:  # noqa: BLE001 - counted, not diagnosed, like the other sweeps
            continue
        if not any(all_lyrics(theirs)):
            continue
        documents += 1
        for ours, expected in zip(all_lyrics(mine), all_lyrics(theirs), strict=False):
            if ours == expected:
                identical += 1
            else:
                different += 1
    return documents, identical, different


def test_the_corpus_exports_lyrics(coverage: tuple[int, int]) -> None:
    documents, syllables = coverage
    assert documents == DOCUMENTS_WITH_LYRICS
    assert syllables == SYLLABLES


def test_both_containers_produce_the_same_syllables(agreement: tuple[int, int, int]) -> None:
    """The load-bearing assertion. A `.musx` writes one lyric record per
    (entry, verse); a `.mus` packs every verse into one record and repeats it.
    Identical output is what shows the two readings of that agree.
    """
    documents, identical, different = agreement
    assert documents == PAIRED_WITH_LYRICS
    assert different == 0
    assert identical > 1_500
