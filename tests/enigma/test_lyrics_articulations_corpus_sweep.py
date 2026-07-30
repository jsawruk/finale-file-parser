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
from conftest import PairedCorpus
from corpus_files import oracle_pairs

from finale_file_parser.enigma.to_ir import RESERVED_STAFF
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

ARTICULATION_DOCUMENTS = 276
ARTICULATIONS = 26301
"""Articulations exported across the corpus.

Only the five characters `enigma.articulations` has evidence for are emitted, so
this counts what is understood rather than what is present -- the corpus assigns
29 distinct characters.
"""

PAIRED_WITH_ARTICULATIONS = 75
ARTICULATION_DIFFERENCES = 7
"""Events whose articulations differ, all in one pair.

**Not a reader gap: the marks are not in the `.mus`.** The `.musx` assigns its
accent 12 times and the `.mus` 5, on entries that carry a staccato in both, and
the two files' `articDef` tables are identical. What rules out a dropped record is
`test_the_pool_tiles_its_stream_exactly`: the details walk accounts for every byte
of the pool, so 174 assignments read is 174 assignments present.

The two are the same music from different collections -- a later edition with
seven more accents -- which the entry-count pairing filter cannot separate from an
identical save. Pinned in the same spirit as `OTHER_PITCHES`: a content
difference between two files, counted rather than explained away.
"""

BEAM_DOCUMENTS = 369
BEAMS = 90824

PAIRED_WITH_BEAMS = 90
BEAM_EVENT_DIFFERENCES = 2
"""Two events whose beams differ between containers.

One corpus entry disagrees about Enigma's beam bit -- the same `.mus`/`.musx`
revision the entry-pool sweep already pins -- and a bit that opens a group
changes the beams of the note on each side of the break.
"""

GROUP_DOCUMENTS = 158
GROUPS = 230
"""Staff groups reaching the IR -- every one of the 209 in the pool.

It was 201 while parts were ordered by staff number, which left 8 groups
spanning a non-contiguous run; ordering parts by the document's own staff
layout makes all of them contiguous. The equality with the pool count is also
the check that no part-variant record is counted twice.
"""

GROUP_SYMBOLS = {"brace": 132, "bracket": 78, None: 20}
"""Only bracket ids with evidence get a symbol; id 8's groups are emitted
without one rather than guessed at.

The 8 groups recovered by ordering parts along the score's staff layout are 7
brackets and 1 unmapped -- section brackets over staves the numeric order split
apart. No brace was ever affected, which fits: a brace spans two adjacent staves
of one instrument.

Rose again when three documents that had never built started to: see
`enigma.tuplet.tuplets_by_entry`."""

PAIRED_WITH_GROUPS = 22
GROUP_NAME_ONLY_DIFFERENCES = 6
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

The two barline counts briefly fell to 107 and 119, in the window between
excluding the reserved staff and giving every part every measure: 4 repeats sat
on bars no part reached. Every measure now belongs to every part, so a barline
always has somewhere to be drawn.
"""

PAIRED_WITH_REPEATS = 24
"""Same-content pairs where either container carries a repeat."""

FINGERING_DOCUMENTS = 18
FINGERINGS = 834
"""Fingerings exported from the `.musx` corpus.

The distribution corroborates the reading: 3 is most common (261), then 1 (219),
2 (174), 4 (126) and 5 (54) -- the shape you would expect of keyboard and string
music.
"""

MUS_FINGERING_DOCUMENTS = 5
MUS_FINGERINGS = 218
"""The legacy reader's own count. Pinned separately because **no paired
document verifies it**: six pairs carry a fingering in the `.musx`, four have a
`.mus` that does not read and two are a different arrangement. What is verified
is the field -- `articDef.charMain` agrees across 72 pairs -- not these values.
"""

BARLINE_DOCUMENTS = 92
BARLINE_STYLES = {"light-light": 228, "light-heavy": 110}
"""Double and final bars exported, counted per measure.

`normal` is not counted: it is the default barline and needs no element.
"""

PAIRED_WITH_BARLINES = 9
"""Same-content pairs where either container styles a barline. Still small, and
still why a `.mus` refuses to guess at `final`: none of the nine carries one."""

JUMP_DOCUMENTS = 3
JUMP_MARKINGS = 6
"""Text repeats reaching the export, counted per measure rather than per part.

Small on purpose. The corpus holds 17 assignments across 10 documents; 5 name a
definition whose text the file does not carry, and several more are a music-font
glyph rather than words. What is left is "Fine" and "D.C. al Coda". The palette
every document carries is deliberately not counted -- see `enigma.jumps`.
"""

MEASURE_RESTS = 7013
"""Bars a part rests through, across the corpus.

They were absent entirely until parts were given every measure: 420 of 731
parts skipped at least one, and their measure numbering jumped over it.
"""

RESERVED_STAFF_PARTS = 0
"""Exported parts for staff 32767, which every corpus document declares and
none lays out. Must stay zero: it was one per document until it was excluded,
and nothing else in the corpus is absent from the instrument list."""

PAIRED_WITH_LYRICS = 15
"""Same-content pairs where the `.musx` carries lyrics, so the two containers
can be compared. The only oracle for the `.mus` side, and it was 6 until pairing
stopped guessing which `.musx` a stem meant -- nine of these fifteen were being
discarded because an arbitrary same-stem candidate failed the same-music check
while a sibling would have passed. The comparison below is unchanged and still
finds no difference, which is what makes the extra coverage worth having."""


def musx_files() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*.musx"))]


def pairs() -> list[tuple[Path, Path]]:
    return oracle_pairs()


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
def coverage(
    musx_scores: list[tuple[Path, Score]],
) -> tuple[int, int]:
    documents = syllables = 0
    for _, score in musx_scores:
        total = sum(len(item) for item in all_lyrics(score))
        if total:
            documents += 1
            syllables += total
    return documents, syllables


@pytest.fixture(scope="module")
def agreement(
    paired_scores: PairedCorpus,
) -> tuple[int, int, int]:
    documents = identical = different = 0
    for mine, theirs in paired_scores.pairs:
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
def articulation_coverage(
    musx_scores: list[tuple[Path, Score]],
) -> tuple[int, int]:
    documents = marks = 0
    for _, score in musx_scores:
        total = sum(len(item) for item in all_articulations(score))
        if total:
            documents += 1
            marks += total
    return documents, marks


@pytest.fixture(scope="module")
def articulation_agreement(
    paired_scores: PairedCorpus,
) -> tuple[int, int, int]:
    documents = identical = different = 0
    for mine, theirs in paired_scores.pairs:
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
def group_coverage(
    musx_scores: list[tuple[Path, Score]],
) -> tuple[int, int, dict[str | None, int]]:
    documents = groups = 0
    symbols: collections.Counter[str | None] = collections.Counter()
    for _, score in musx_scores:
        if not score.groups:
            continue
        documents += 1
        groups += len(score.groups)
        symbols.update(group.symbol for group in score.groups)
    return documents, groups, dict(symbols)


@pytest.fixture(scope="module")
def group_agreement(
    paired_scores: PairedCorpus,
) -> tuple[int, int, int]:
    documents = shape_differences = name_only = 0
    for mine, theirs in paired_scores.pairs:
        if not mine.groups and not theirs.groups:
            continue
        documents += 1
        if group_shape(mine) != group_shape(theirs):
            shape_differences += 1
        elif all_groups(mine) != all_groups(theirs):
            name_only += 1
    return documents, shape_differences, name_only


def test_the_corpus_exports_fingerings(
    musx_scores: list[tuple[Path, Score]],
) -> None:
    documents = 0
    digits: collections.Counter[str] = collections.Counter()
    for _, score in musx_scores:
        found = [
            digit
            for part in score.parts
            for measure in part.measures
            for voice in measure.voices
            for event in voice.events
            for digit in event.fingerings
        ]
        if found:
            documents += 1
            digits.update(found)
    assert documents == FINGERING_DOCUMENTS
    assert sum(digits.values()) == FINGERINGS
    assert set(digits) <= {"1", "2", "3", "4", "5"}


def test_the_legacy_reader_finds_fingerings_too(
    mus_scores: list[tuple[Path, Score]],
) -> None:
    """Unverifiable against a `.musx`, so pinned on its own: a change here means
    the legacy `articDef` reading moved."""
    documents = total = 0
    for _, score in mus_scores:
        found = sum(
            len(event.fingerings)
            for part in score.parts
            for measure in part.measures
            for voice in measure.voices
            for event in voice.events
        )
        if found:
            documents += 1
            total += found
    assert documents == MUS_FINGERING_DOCUMENTS
    assert total == MUS_FINGERINGS


def test_the_corpus_exports_barline_styles(
    musx_scores: list[tuple[Path, Score]],
) -> None:
    documents = 0
    styles: collections.Counter[str] = collections.Counter()
    for _, score in musx_scores:
        found = {
            measure.number: measure.barline_style
            for part in score.parts
            for measure in part.measures
            if measure.barline_style
        }
        if found:
            documents += 1
            styles.update(found.values())
    assert documents == BARLINE_DOCUMENTS
    assert dict(styles) == BARLINE_STYLES


def test_both_containers_style_the_same_barlines(
    paired_scores: PairedCorpus,
) -> None:
    """A `.mus` keeps the style in a nibble of the repeat flags byte, so this
    also checks the two readings of that byte do not interfere."""
    documents = different = 0

    def styles(score: Score) -> dict[int, str | None]:
        return {
            measure.number: measure.barline_style
            for part in score.parts
            for measure in part.measures
            if measure.barline_style
        }

    for mus_score, musx_score in paired_scores.pairs:
        mine, theirs = styles(mus_score), styles(musx_score)
        if not mine and not theirs:
            continue
        documents += 1
        if mine != theirs:
            different += 1
    assert documents == PAIRED_WITH_BARLINES
    assert different == 0


def test_the_corpus_exports_text_repeats(
    musx_scores: list[tuple[Path, Score]],
) -> None:
    """Guards the palette trap from the other side: if the definitions were read
    without their assignments this would be in the hundreds, not 6."""
    documents = markings = 0
    for _, score in musx_scores:
        found = {
            (measure.number, words)
            for part in score.parts
            for measure in part.measures
            for words in measure.directions
        }
        if found:
            documents += 1
            markings += len(found)
    assert documents == JUMP_DOCUMENTS
    assert markings == JUMP_MARKINGS


def test_every_part_covers_every_measure(
    musx_scores: list[tuple[Path, Score]],
) -> None:
    """A part that falls silent must still have the bar. Asserted over the
    corpus because the failure is invisible in a single document -- the output
    stays well-formed, the numbering simply skips."""
    rests = 0
    for _, score in musx_scores:
        lists = {tuple(m.number for m in part.measures) for part in score.parts}
        assert len(lists) == 1, "parts of one score disagree about which measures exist"
        numbers = next(iter(lists))
        assert list(numbers) == list(range(1, len(numbers) + 1)), "measure numbering has a gap"
        rests += sum(
            1
            for part in score.parts
            for measure in part.measures
            for voice in measure.voices
            for event in voice.events
            if event.is_measure_rest
        )
    assert rests == MEASURE_RESTS


def test_no_document_exports_the_reserved_staff(
    musx_scores: list[tuple[Path, Score]],
) -> None:
    """Asserted over the whole corpus rather than a constructed document,
    because the claim is about every file Finale writes, not about the rule."""
    parts = 0
    for _, score in musx_scores:
        parts += sum(1 for part in score.parts if part.id == f"P{RESERVED_STAFF}")
        assert score.parts, "excluding the reserved staff must not empty a score"
    assert parts == RESERVED_STAFF_PARTS


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
def repeat_coverage(
    musx_scores: list[tuple[Path, Score]],
) -> tuple[int, int, int, int]:
    documents = forward = backward = brackets = 0
    for _, score in musx_scores:
        repeats = all_repeats(score)
        if not repeats:
            continue
        documents += 1
        forward += sum(1 for row in repeats.values() if row.forward)
        backward += sum(1 for row in repeats.values() if row.backward)
        brackets += sum(1 for row in repeats.values() for _, kind in row.endings if kind == "start")
    return documents, forward, backward, brackets


@pytest.fixture(scope="module")
def repeat_agreement(
    paired_scores: PairedCorpus,
) -> tuple[int, int]:
    documents = different = 0
    for mine, theirs in paired_scores.pairs:
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
def beam_coverage(
    musx_scores: list[tuple[Path, Score]],
) -> tuple[int, int]:
    documents = beams = 0
    for _, score in musx_scores:
        total = sum(len(item) for item in all_beams(score))
        if total:
            documents += 1
            beams += total
    return documents, beams


@pytest.fixture(scope="module")
def beam_agreement(
    paired_scores: PairedCorpus,
) -> tuple[int, int, int]:
    documents = identical = different = 0
    for mine, theirs in paired_scores.pairs:
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
    assert identical > 18_000


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
    assert different == ARTICULATION_DIFFERENCES
    assert identical > 16_000


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
    assert identical > 1_400
