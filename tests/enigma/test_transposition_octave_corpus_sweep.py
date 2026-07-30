"""Pin the relationship between the two containers' `harm_lev` frames.

This is the durable result of the transposition-octave investigation
(`docs/formats/transposition-octave.md`). Finale folds the octaves out of a
transposition into a residue **and** into every note's `harm_lev`; a `.mus`
stores the residue with an unshifted `harm_lev`, a `.musx` the full interval
with a `harm_lev` shifted to match.

The delta is exactly what `harm_lev_octave_shift` predicts. Asserting it here
means the next person to touch transposition finds the relationship measured
rather than argued, and finds out immediately if either reader stops honouring
it.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

import pytest
from corpus_files import oracle_pairs

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_entries import harm_lev_octave_shift, read_mus_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

COMPARED_NOTES = 4472
"""Notes on a transposing staff readable from both containers."""

EXCEPTIONS = 2
"""Notes whose delta is not the predicted one.

Both sit in the single document the entry-pool sweep already pins as a
`.mus`/`.musx` revision difference.
"""


def pairs() -> list[tuple[Path, Path]]:
    return oracle_pairs()


def intervals(xml: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for match in re.finditer(r'<staffSpec cmper="(\d+)"\s*>(.*?)</staffSpec>', xml, re.DOTALL):
        found = re.search(r"<interval>(-?\d+)</interval>", match.group(2))
        if found and int(found.group(1)):
            out[int(match.group(1))] = int(found.group(1))
    return out


@pytest.fixture(scope="module")
def deltas() -> collections.Counter[tuple[int, int, int]]:
    """(interval, predicted shift, measured delta) -> count."""
    out: collections.Counter[tuple[int, int, int]] = collections.Counter()
    for mus_path, musx_path in pairs():
        try:
            raw = score_xml(musx_path)
            document = parse_enigma(raw)
            if len(read_mus_entries(mus_path)) != len(document.entries.records):
                continue
            legacy = read_mus_document(mus_path)
        except CorruptScoreError:
            continue
        except Exception:  # noqa: BLE001 - counted elsewhere; this sweep needs both readers
            continue
        transposing = intervals(raw.decode("utf-8", "replace"))
        if not transposing:
            continue
        location = locate_entries(document)
        theirs = {int(r.attrs["entnum"]): r for r in document.entries.of_tag("entry")}
        mine = {int(r.attrs["entnum"]): r for r in legacy.entries.of_tag("entry")}
        for entnum, where in location.items():
            interval = transposing.get(where.staff)
            if interval is None or entnum not in theirs or entnum not in mine:
                continue
            a, b = read_entry(theirs[entnum]), read_entry(mine[entnum])
            if len(a.notes) != len(b.notes):
                continue
            for note, legacy_note in zip(a.notes, b.notes, strict=True):
                out[
                    (
                        interval,
                        harm_lev_octave_shift(interval),
                        note.harm_lev - legacy_note.harm_lev,
                    )
                ] += 1
    return out


def test_the_containers_differ_by_exactly_the_folded_octaves(
    deltas: collections.Counter[tuple[int, int, int]],
) -> None:
    """`.musx` harm_lev - `.mus` harm_lev == harm_lev_octave_shift(interval).

    Seven diatonic steps per octave folded out of the transposition. This is
    what says the octave is *in* the `.mus`, carried by the notes rather than by
    the staff -- and so what says Finale needs no octave field to display one.
    """
    total = sum(deltas.values())
    wrong = sum(count for (_, shift, delta), count in deltas.items() if delta != shift)
    assert total == COMPARED_NOTES
    assert wrong == EXCEPTIONS


def test_the_fold_is_zero_exactly_when_the_interval_has_no_octave(
    deltas: collections.Counter[tuple[int, int, int]],
) -> None:
    """A transposition inside one octave shifts nothing; beyond it, one octave
    per octave. If this ever fails, the residue model itself is wrong."""
    for interval, shift, _ in deltas:
        assert shift % 7 == 0, "a fold that is not a whole number of octaves"
        assert (shift == 0) == (-4 <= -interval <= 2), (
            f"interval {interval} folds {shift} but its residue says otherwise"
        )
