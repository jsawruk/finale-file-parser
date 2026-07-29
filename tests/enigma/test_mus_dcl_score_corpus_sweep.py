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
from finale_file_parser.enigma.mus_entries import read_mus_entry_records
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.version import mus as mus_header

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

LAST_DCL_YEAR = 2005
EXPECTED_DOCUMENTS = 139

EXPECTED_SCORES = 129
"""Documents that build. Before this reader, none of the 139 did."""

EXPECTED_PARTS = 402
EXPECTED_MEASURES = 13717
EXPECTED_EVENTS = 60476
EXPECTED_PITCHES = 66847
"""The shape of what comes out. A reader that built empty scores would still
pass a "did it build" test; these are what stop that."""

EXPECTED_DEAD_ENTRIES = 4946
"""Entries the reader discards because no frame reaches them.

**This is the pin that keeps the pruning honest.** A `.mus` entry pool is a live
database -- deleting music in Finale leaves its slots behind until the file is
compacted -- so an unreached entry is dead space, not music. Discarding it is
what lets these documents build at all, but it is also exactly how a reader that
*stopped reaching* music would hide the loss.

So the count is pinned, and it may only fall. Reading two frame slots per
`gfhold` instead of four, for instance, put 1,058 more entries out of reach:
under this pin that is a failure rather than a quieter score. The 5,302 are
overwhelmingly provable dead space -- 4,675 duplicate live passages chain for
chain. (The three documents whose frames reach nothing at all are refused
outright rather than pruned to nothing, so their 356 entries are not counted
here.) See `docs/formats/mus-dcl-container.md`.
"""

EXPECTED_MALFORMED = 2
"""Documents `build_score` rejects: one entry that two frames both claim, and
one `gfhold` placing entries in a measure that defines no key.

Pinned rather than tolerated: these are known, named gaps, and the number should
fall, never rise. See `docs/formats/mus-dcl-container.md`.
"""

EXPECTED_CORRUPT = 8
"""Two whose entry pool holds a breve or a dotted whole, which
`duration_from_edu` rejects -- a note-value limit, not a container one -- and
six that carry no music the frames reach. Three of those six have no frame holds
at all; the other three have frame holds that resolve to nothing, so their whole
entry pool is unreachable. All six are blank scores: they have staves and
measures but no music, and building one yields a Score with no parts, which is
not valid MusicXML."""


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


def test_the_reader_discards_only_dead_pool_space() -> None:
    """The counterweight to the pruning in `_live_entries`.

    Discarding unreached entries is what lets these documents build, and it is
    also how a reader that quietly stopped reaching music would look. Reading
    two frame slots per `gfhold` rather than four leaves 1,058 more entries
    unreached; this fails on that, where the build counts alone would only get
    quieter.
    """
    dead = 0
    for path in _dcl_files():
        try:
            document = read_mus_document(path)
        except CorruptScoreError:
            continue
        dead += len(read_mus_entry_records(path)) - len(document.entries.records)
    assert dead == EXPECTED_DEAD_ENTRIES
