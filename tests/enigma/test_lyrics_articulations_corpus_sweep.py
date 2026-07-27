"""Validate lyric, articulation and beam export, and the containers against each other.

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

ARTICULATION_DOCUMENTS = 273
ARTICULATIONS = 22821
"""Articulations exported across the corpus.

Only the five characters `enigma.articulations` has evidence for are emitted, so
this counts what is understood rather than what is present -- the corpus assigns
29 distinct characters.
"""

PAIRED_WITH_ARTICULATIONS = 72

BEAM_DOCUMENTS = 366
BEAMS = 84620

PAIRED_WITH_BEAMS = 81
BEAM_EVENT_DIFFERENCES = 2
"""Two events whose beams differ between containers.

One corpus entry disagrees about Enigma's beam bit -- the same `.mus`/`.musx`
revision the entry-pool sweep already pins -- and a bit that opens a group
changes the beams of the note on each side of the break.
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


def all_beams(score: Score) -> list[tuple[object, ...]]:
    return [
        event.beams
        for part in score.parts
        for measure in part.measures
        for voice in measure.voices
        for event in voice.events
    ]


def all_articulations(score: Score) -> list[tuple[str, ...]]:
    return [
        event.articulations
        for part in score.parts
        for measure in part.measures
        for voice in measure.voices
        for event in voice.events
    ]


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


@pytest.fixture(scope="module")
def articulation_coverage() -> tuple[int, int]:
    documents = marks = 0
    for path in musx_files():
        try:
            score = build_score(parse_enigma(score_xml(path)))
        except CorruptScoreError:
            continue
        total = sum(len(item) for item in all_articulations(score))
        if total:
            documents += 1
            marks += total
    return documents, marks


@pytest.fixture(scope="module")
def articulation_agreement() -> tuple[int, int, int]:
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
        except Exception:  # noqa: BLE001 - counted, not diagnosed
            continue
        if not any(all_articulations(theirs)):
            continue
        documents += 1
        for ours, expected in zip(all_articulations(mine), all_articulations(theirs), strict=False):
            if ours == expected:
                identical += 1
            else:
                different += 1
    return documents, identical, different


@pytest.fixture(scope="module")
def beam_coverage() -> tuple[int, int]:
    documents = beams = 0
    for path in musx_files():
        try:
            score = build_score(parse_enigma(score_xml(path)))
        except CorruptScoreError:
            continue
        total = sum(len(item) for item in all_beams(score))
        if total:
            documents += 1
            beams += total
    return documents, beams


@pytest.fixture(scope="module")
def beam_agreement() -> tuple[int, int, int]:
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
        except Exception:  # noqa: BLE001 - counted, not diagnosed
            continue
        if not any(all_beams(theirs)):
            continue
        documents += 1
        for ours, expected in zip(all_beams(mine), all_beams(theirs), strict=False):
            if ours == expected:
                identical += 1
            else:
                different += 1
    return documents, identical, different


def test_the_corpus_exports_beams(beam_coverage: tuple[int, int]) -> None:
    documents, beams = beam_coverage
    assert documents == BEAM_DOCUMENTS
    assert beams == BEAMS


def test_both_containers_produce_the_same_beams(
    beam_agreement: tuple[int, int, int],
) -> None:
    """Beams are computed, not stored, so agreement shows both containers feed
    the same bit and durations into the same rule."""
    documents, identical, different = beam_agreement
    assert documents == PAIRED_WITH_BEAMS
    assert different == BEAM_EVENT_DIFFERENCES
    assert identical > 30_000


def test_the_corpus_exports_articulations(articulation_coverage: tuple[int, int]) -> None:
    documents, marks = articulation_coverage
    assert documents == ARTICULATION_DOCUMENTS
    assert marks == ARTICULATIONS


def test_both_containers_produce_the_same_articulations(
    articulation_agreement: tuple[int, int, int],
) -> None:
    """A `.musx` stores one assignment per mark; a `.mus` sometimes repeats one.
    Identical output is what shows the repeat is handled."""
    documents, identical, different = articulation_agreement
    assert documents == PAIRED_WITH_ARTICULATIONS
    assert different == 0
    assert identical > 25_000


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
