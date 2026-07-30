"""There is no paired document to identify the `.mus` text-repeat tag from.

`mus_document.UNTRANSLATED` used to say one paired document carries a text repeat,
with two assignments, and that a key set that small matches several tags by
chance. The document was a **mispairing**: the `.mus` and the `.musx` credited to
it hold different arrangements that share a filename.

The corpus does carry text repeats -- ten `.musx` files, seventeen assignments --
and three of those stems also have a `.mus`. None of those `.musx` holds the same
music as the `.mus` it would pair with. So the evidence base is not small, it is
empty, and that is a different thing to record: a small one invites another
matching attempt, an empty one says what the corpus would have to gain first.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest
from corpus_files import CORPUS, corpus_paths, oracle_pairs

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.score import score_xml

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

_ASSIGN = "textRepeatAssign"

DOCUMENTS_WITH_TEXT_REPEATS = 10
TEXT_REPEAT_ASSIGNMENTS = 17
"""`.musx` documents carrying a text repeat, and their assignments.

The markings exist in the corpus. What does not exist is one of them next to a
`.mus` of the same music.
"""

PAIRED_WITH_TEXT_REPEATS = 0
"""Paired documents whose `.musx` carries a text repeat. **Zero.**

The number to watch. If it ever rises, the `.mus` tag becomes identifiable and
this gap can be closed; that is the whole precondition. Pinned at 0 so the day a
document arrives that changes it, a test says so rather than nobody noticing.
"""


def _assignments(document: object) -> int:
    return len(
        [r for r in document.others.of_tag(_ASSIGN) if "part" not in r.attrs]  # type: ignore[attr-defined]
    )


def test_the_corpus_does_carry_text_repeats() -> None:
    """Establishing that the gap is about pairing, not about the markings being
    absent -- otherwise the zero below would be unremarkable."""
    documents = assignments = 0
    for path in corpus_paths(".musx"):
        try:
            count = _assignments(parse_enigma(score_xml(path)))
        except CorruptScoreError:
            continue
        if count:
            documents += 1
            assignments += count
    assert documents == DOCUMENTS_WITH_TEXT_REPEATS
    assert assignments == TEXT_REPEAT_ASSIGNMENTS


def test_no_same_music_pair_carries_one() -> None:
    """The load-bearing assertion, and the reason the tag cannot be identified."""
    paired = 0
    for _mus_path, musx_path in oracle_pairs():
        try:
            paired += bool(_assignments(parse_enigma(score_xml(musx_path))))
        except CorruptScoreError:
            continue
    assert paired == PAIRED_WITH_TEXT_REPEATS


def test_the_text_repeat_musx_files_are_different_music_from_their_mus() -> None:
    """Why they are unpaired, stated as a fact rather than left to the filter.

    Each `.musx` that carries a text repeat and shares a stem with a `.mus`
    disagrees with it on entry count -- so they are different arrangements, and no
    pairing rule should match them.
    """
    mus_by_stem: collections.defaultdict[str, list[Path]] = collections.defaultdict(list)
    for path in corpus_paths(".mus"):
        mus_by_stem[path.stem].append(path)

    compared = 0
    for musx_path in corpus_paths(".musx"):
        try:
            document = parse_enigma(score_xml(musx_path))
        except CorruptScoreError:
            continue
        if not _assignments(document):
            continue
        for mus_path in mus_by_stem.get(musx_path.stem, ()):
            try:
                entries = len(read_mus_entries(mus_path))
            except CorruptScoreError:
                continue
            compared += 1
            assert entries != len(document.entries.records), (
                "a text-repeat .musx holds the same music as a .mus: the oracle "
                "this gap needs now exists, and UNTRANSLATED should say so"
            )
    assert compared, "no text-repeat .musx shares a stem with a .mus"
