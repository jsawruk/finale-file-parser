"""Validate the .mus entry reader against paired .musx files.

Skipped wherever corpus/ is absent (e.g. CI). This is the strongest check the
project has on `.mus` decoding: the same document exists in both containers, so
every field can be compared against ground truth rather than merely "parsed
without raising".

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_entries import read_mus_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.pitch import read_transposition
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.version import mus as mus_header
from finale_file_parser.version.detect import detect_version

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

KNOWN_NOTE_COUNT_DIFFS = 1
"""One corpus entry stores two notes in .mus and one in .musx.

Both .mus note records are well-formed, so this reads as a revision made to the
.musx after the .mus was written rather than a decode error. Pinned rather than
tolerated: if the count grows, something has actually broken.
"""

KNOWN_NOTE_DIFFS = 1
"""One note differs, in the same document as KNOWN_NOTE_COUNT_DIFFS and in an
adjacent entry: 553 loses a note and 555 moves by an octave. Two neighbouring
edits in one file read as a revision made to the .musx after the .mus was
written, not a decode error. Pinned so a real regression still fails."""

MIN_PAIRS = 40
"""Guards the sweep: a corpus too small to be meaningful must fail, not pass."""
FIRST_ZLIB_ERA_YEAR = 2011
"""Only this era separates pools into their own streams; see mus_entries."""


def _created(path: Path) -> tuple[int, int, int] | None:
    detail: object
    if path.suffix.lower() == ".mus":
        detail = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE])
    else:
        detail = detect_version(path).detail
    stamp = getattr(detail, "created", None)
    return None if stamp is None else (stamp.year, stamp.month, stamp.day)


def _pairs() -> list[tuple[Path, Path]]:
    """.mus/.musx files that are the same document, in the zlib era."""
    mus = {p.stem: p for p in CORPUS.rglob("*") if p.suffix.lower() == ".mus"}
    musx = {p.stem: p for p in CORPUS.rglob("*") if p.suffix.lower() == ".musx"}
    out = []
    for stem in sorted(set(mus) & set(musx)):
        year = mus_header.parse(mus[stem].read_bytes()[: mus_header.MUS_METADATA_SIZE]).year
        if year is None or year < FIRST_ZLIB_ERA_YEAR:
            continue
        if _created(mus[stem]) is not None and _created(mus[stem]) == _created(musx[stem]):
            out.append((mus[stem], musx[stem]))
    return out


def _has_transposing_staff(document: EnigmaDocument) -> bool:
    """Any staff that actually transposes.

    `read_transposition` returns a zero transposition for an ordinary staff
    rather than None, so presence alone is not the question -- it has to be
    non-zero.
    """
    for record in document.others.records:
        if record.tag != "staffSpec":
            continue
        transposition = read_transposition(record)
        if transposition is not None and (transposition.interval or transposition.adjust):
            return True
    return False


def test_enough_pairs_to_be_meaningful() -> None:
    assert len(_pairs()) >= MIN_PAIRS


def test_entries_match_the_paired_musx() -> None:
    """Entry identity, duration, rest-ness and note count must match exactly.

    Notes are compared only on documents with no transposing staff: those with one
    show a uniform one-octave offset in `harm_lev`, which is an unresolved
    octave-reference question rather than a decode failure. Asserting notes
    everywhere would either fail or force a fudge factor that corrupts the
    non-transposing majority.
    """
    totals = dict(entries=0, duration=0, rest=0, count=0, notes=0, notes_ok=0)
    files_with_notes_checked = 0
    unsupported = 0
    pairs = _pairs()

    for mus_path, musx_path in pairs:
        try:
            actual_entries = read_mus_entries(mus_path)
        except CorruptScoreError as exc:
            # Two corpus files lay their payload out as three streams rather than
            # four, so the entry pool is not a standalone stream. The reader must
            # say so plainly rather than mis-parse -- but it must not be silently
            # tolerated either, hence the ratio assertion below.
            assert "no recognisable entry pool" in str(exc)
            unsupported += 1
            continue

        document = parse_enigma(score_xml(musx_path))
        expected = {}
        for record in document.entries.records:
            entry = read_entry(record)
            expected[entry.entnum] = entry
        actual = {entry.entnum: entry for entry in actual_entries}

        assert set(actual) == set(expected), "entry numbers differ from the paired .musx"

        check_notes = not _has_transposing_staff(document)
        files_with_notes_checked += int(check_notes)
        for entnum, want in expected.items():
            got = actual[entnum]
            totals["entries"] += 1
            totals["duration"] += got.duration == want.duration
            totals["rest"] += got.is_rest == want.is_rest
            totals["count"] += len(got.notes) == len(want.notes)
            if check_notes and len(got.notes) == len(want.notes):
                for a, b in zip(got.notes, want.notes, strict=True):
                    totals["notes"] += 1
                    totals["notes_ok"] += a == b

    supported = len(pairs) - unsupported
    assert supported >= 0.9 * len(pairs), (
        f"only {supported} of {len(pairs)} pairs have a standalone entry-pool stream"
    )
    assert totals["entries"] > 0
    assert totals["duration"] == totals["entries"], "durations disagree with the .musx"
    assert totals["rest"] == totals["entries"], "rest flags disagree with the .musx"
    count_diffs = totals["entries"] - totals["count"]
    assert count_diffs <= KNOWN_NOTE_COUNT_DIFFS, (
        f"{count_diffs} note counts disagree with the .musx (only {KNOWN_NOTE_COUNT_DIFFS} known)"
    )
    assert files_with_notes_checked >= 10, "too few non-transposing files to check notes"
    note_diffs = totals["notes"] - totals["notes_ok"]
    assert note_diffs <= KNOWN_NOTE_DIFFS, (
        f"{note_diffs} notes disagree with the .musx (only {KNOWN_NOTE_DIFFS} known)"
    )
