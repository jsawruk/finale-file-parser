"""Build a `Score` from every 2001-2005 `.mus`, and pin what does not build.

Skipped wherever corpus/ is absent (e.g. CI). This cohort has **no paired
`.musx`**, so "it built" is not on its own evidence of anything. What is pinned
here is the shape of the result -- parts, measures, events, pitches -- so that a
change which quietly empties a score fails instead of passing.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.location import MalformedScoreError
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.version import mus as mus_header

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

LAST_DCL_YEAR = 2005
EXPECTED_DOCUMENTS = 139

EXPECTED_SCORES = 118
"""Documents that build. Before this reader, none of the 139 did."""

EXPECTED_PARTS = 321
EXPECTED_MEASURES = 9711
EXPECTED_EVENTS = 48112
EXPECTED_PITCHES = 55463
"""The shape of what comes out. A reader that built empty scores would still
pass a "did it build" test; these are what stop that."""

EXPECTED_MALFORMED = 16
"""Documents `build_score` rejects.

Almost all are orphan entries -- music no frame reaches. They concentrate in 16
documents: 258 are chain heads nothing frames at all, 4,325 continue one of
those chains, and 711 sit past a frame whose `endEntry` stops short of where the
music does. One rejection is an entry two frames both claim, and one a gfhold
naming a measure past the end.

Pinned rather than tolerated: these are known, named gaps, and the number should
fall, never rise. See `docs/formats/mus-dcl-container.md`.
"""

EXPECTED_CORRUPT = 5
"""Two whose entry pool holds a breve or a dotted whole, which
`duration_from_edu` rejects -- a note-value limit, not a container one -- and
three that carry no frame holds at all. Those three are blank scores: they have
staves and measures but no music, and building one yields a Score with no parts,
which is not valid MusicXML."""


def _dcl_files() -> list[Path]:
    """Case-insensitive: a case-sensitive glob drops the whole Windows cohort."""
    out = []
    for path in sorted(p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".mus"):
        year = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE]).year
        if year is not None and year <= LAST_DCL_YEAR:
            out.append(path)
    return out


def test_the_cohort_builds_scores_with_music_in_them() -> None:
    built = malformed = corrupt = 0
    parts = measures = events = pitches = 0
    for path in _dcl_files():
        try:
            score = build_score(read_mus_document(path))
        except MalformedScoreError:
            malformed += 1
            continue
        except CorruptScoreError:
            corrupt += 1
            continue
        built += 1
        parts += len(score.parts)
        for part in score.parts:
            measures += len(part.measures)
            for measure in part.measures:
                for voice in measure.voices:
                    events += len(voice.events)
                    pitches += sum(len(event.pitches) for event in voice.events)

    assert built == EXPECTED_SCORES
    assert malformed == EXPECTED_MALFORMED
    assert corrupt == EXPECTED_CORRUPT
    assert built + malformed + corrupt == EXPECTED_DOCUMENTS
    assert parts == EXPECTED_PARTS
    assert measures == EXPECTED_MEASURES
    assert events == EXPECTED_EVENTS
    assert pitches == EXPECTED_PITCHES


def test_every_built_measure_carries_a_time_signature_and_most_carry_music() -> None:
    """A score of empty measures would satisfy the counts above document by
    document but not this: the time signature comes from `MS` and the events
    from the frame chain, so this fails if either link is broken.
    """
    with_time = with_events = total = 0
    for path in _dcl_files():
        try:
            score = build_score(read_mus_document(path))
        except Exception:  # noqa: BLE001 - counted by the sweep above
            continue
        for part in score.parts:
            for measure in part.measures:
                total += 1
                with_time += measure.time is not None
                with_events += any(voice.events for voice in measure.voices)
    assert total == EXPECTED_MEASURES
    # A time signature is written only where it changes, so the first measure of
    # each part carries one and the rest inherit.
    assert with_time >= EXPECTED_PARTS
    assert with_events / total >= 0.75


def test_no_built_score_is_empty() -> None:
    """A score with no parts is not a successful read.

    Three documents used to produce one, and it took the export audit to notice:
    the totals above were satisfied document-by-document while one file
    contributed nothing at all. Asserted per document rather than in aggregate,
    which is the whole point.
    """
    for path in _dcl_files():
        try:
            score = build_score(read_mus_document(path))
        except (CorruptScoreError, MalformedScoreError):
            continue
        assert score.parts, "built a score with no parts"
        assert any(measure.voices for part in score.parts for measure in part.measures), (
            "built a score with no music"
        )
