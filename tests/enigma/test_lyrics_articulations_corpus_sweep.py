"""Validate lyric, articulation, beam, repeat and group export, and the containers.

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

import collections
from pathlib import Path
from typing import NamedTuple

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

GROUP_DOCUMENTS = 155
GROUPS = 201
"""Staff groups reaching the IR, of 209 in the pool.

The 8 that do not are groups whose staves are not contiguous once parts are
ordered by staff number; see `to_ir._groups`. `staff_groups` itself returns
exactly one per pool record -- that equality is the check that no part-variant
record is being counted twice.
"""

GROUP_SYMBOLS = {"brace": 129, "bracket": 65, None: 7}
"""Only bracket ids with evidence get a symbol; id 8's 7 groups are emitted
without one rather than guessed at."""

PAIRED_WITH_GROUPS = 15
GROUP_NAME_ONLY_DIFFERENCES = 4
"""Pairs differing from their `.musx` in the group name and nothing else.

A `.mus` recovers the name's text-block id but carries no text blocks to
resolve it against -- the same missing chain as staff names.
"""

REPEAT_DOCUMENTS = 109
FORWARD_REPEATS = 109
BACKWARD_REPEATS = 121
ENDING_BRACKETS = 142
"""Repeat barlines and ending brackets exported across the corpus.

Measures rather than parts: every part of a score carries the same barline, so
counting rows would measure how many staves the repertoire uses.

All three match the raw element counts in the `.musx` pool -- 109 `forRepBar`,
121 `bacRepBar`, 142 `repeatEndingStart` -- which is the check that nothing is
invented or lost between the pool and the IR.
"""

PAIRED_WITH_REPEATS = 19
"""Same-content pairs where either container carries a repeat."""

PAIRED_WITH_LYRICS = 6
"""Same-content pairs where the `.musx` carries lyrics, so the two containers
can be compared. Small, but it is the only oracle for the `.mus` side."""


def musx_files() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*.musx"))]


def pairs() -> list[tuple[Path, Path]]:
    mus = {p.stem: p for p in CORPUS.rglob("*.mus")}
    musx = {p.stem: p for p in CORPUS.rglob("*.musx")}
    return [(mus[s], musx[s]) for s in sorted(set(mus) & set(musx))]


class MeasureRepeat(NamedTuple):
    forward: bool
    backward: bool
    passes: int | None
    endings: tuple[tuple[tuple[int, ...], str], ...]


def all_groups(score: Score) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (group.part_ids, group.symbol, group.barline, group.name) for group in score.groups
    )


def group_shape(score: Score) -> tuple[tuple[object, ...], ...]:
    """Everything about a group except its name."""
    return tuple(row[:3] for row in all_groups(score))


def all_repeats(score: Score) -> dict[int, MeasureRepeat]:
    """One entry per measure carrying a repeat, keyed by measure number.

    Keyed by measure, not accumulated per part, so the comparison is not
    inflated by scores that happen to have many staves.
    """
    return {
        measure.number: MeasureRepeat(
            measure.repeat_forward,
            measure.repeat_backward,
            measure.repeat_passes if measure.repeat_backward else None,
            tuple((ending.numbers, ending.type) for ending in measure.endings),
        )
        for part in score.parts
        for measure in part.measures
        if measure.repeat_forward or measure.repeat_backward or measure.endings
    }


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
def group_coverage() -> tuple[int, int, dict[str | None, int]]:
    documents = groups = 0
    symbols: collections.Counter[str | None] = collections.Counter()
    for path in musx_files():
        try:
            score = build_score(parse_enigma(score_xml(path)))
        except CorruptScoreError:
            continue
        if not score.groups:
            continue
        documents += 1
        groups += len(score.groups)
        symbols.update(group.symbol for group in score.groups)
    return documents, groups, dict(symbols)


@pytest.fixture(scope="module")
def group_agreement() -> tuple[int, int, int]:
    documents = shape_differences = name_only = 0
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
        if not mine.groups and not theirs.groups:
            continue
        documents += 1
        if group_shape(mine) != group_shape(theirs):
            shape_differences += 1
        elif all_groups(mine) != all_groups(theirs):
            name_only += 1
    return documents, shape_differences, name_only


def test_the_corpus_exports_staff_groups(
    group_coverage: tuple[int, int, dict[str | None, int]],
) -> None:
    documents, groups, symbols = group_coverage
    assert documents == GROUP_DOCUMENTS
    assert groups == GROUPS
    assert symbols == GROUP_SYMBOLS


def test_both_containers_produce_the_same_groups(group_agreement: tuple[int, int, int]) -> None:
    """Extent, symbol and barline must match exactly. Names are the one known
    gap: a `.mus` has no text blocks to resolve them against."""
    documents, shape_differences, name_only = group_agreement
    assert documents == PAIRED_WITH_GROUPS
    assert shape_differences == 0
    assert name_only == GROUP_NAME_ONLY_DIFFERENCES


@pytest.fixture(scope="module")
def repeat_coverage() -> tuple[int, int, int, int]:
    documents = forward = backward = brackets = 0
    for path in musx_files():
        try:
            score = build_score(parse_enigma(score_xml(path)))
        except CorruptScoreError:
            continue
        repeats = all_repeats(score)
        if not repeats:
            continue
        documents += 1
        forward += sum(1 for row in repeats.values() if row.forward)
        backward += sum(1 for row in repeats.values() if row.backward)
        brackets += sum(1 for row in repeats.values() for _, kind in row.endings if kind == "start")
    return documents, forward, backward, brackets


@pytest.fixture(scope="module")
def repeat_agreement() -> tuple[int, int]:
    documents = different = 0
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
        ours, expected = all_repeats(mine), all_repeats(theirs)
        if not ours and not expected:
            continue
        documents += 1
        if ours != expected:
            different += 1
    return documents, different


def test_the_corpus_exports_repeats(repeat_coverage: tuple[int, int, int, int]) -> None:
    documents, forward, backward, brackets = repeat_coverage
    assert documents == REPEAT_DOCUMENTS
    assert forward == FORWARD_REPEATS
    assert backward == BACKWARD_REPEATS
    assert brackets == ENDING_BRACKETS


def test_both_containers_produce_the_same_repeats(repeat_agreement: tuple[int, int]) -> None:
    """A bracket's extent is reconstructed from three records and a flag; if
    either container read any of them differently this would not be zero."""
    documents, different = repeat_agreement
    assert documents == PAIRED_WITH_REPEATS
    assert different == 0


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
