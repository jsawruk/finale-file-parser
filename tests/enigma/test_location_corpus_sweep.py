"""Sweep the full local corpus through locate_entries, resolving every entry to its

staff, measure, and raw key via the gfhold -> frameSpec -> entry link chain.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted third-party
material and is gitignored; these assertions are the only check against real archives.

The core assertion is that every entry is located exactly once and locate_entries does
not raise -- the survey found 0 orphans over 24,159 entries, so any MalformedScoreError
here is a real finding, not a reason to loosen an assertion.

Report counts only -- never a corpus filename, record value, pitch, lyric, or text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_corpus_entry_is_located_exactly_once() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    archives_read = 0
    entries_located = 0
    seen_multi_layer_measure = False

    for path in paths:
        doc = parse_enigma(score_xml(path))
        archives_read += 1

        entry_records = list(doc.entries.of_tag("entry"))
        locations = locate_entries(doc)

        assert len(locations) == len(entry_records), path

        staff_cmpers = {
            int(record.attrs["cmper"])
            for record in doc.others.of_tag("staffSpec")
            if "cmper" in record.attrs
        }

        for location in locations.values():
            assert isinstance(location.key_signature, int), path
            assert location.staff in staff_cmpers, path

        entries_located += len(locations)

        if not seen_multi_layer_measure:
            for gfhold in doc.details.of_tag("gfhold"):
                frame2 = gfhold.fields.get("frame2")
                if isinstance(frame2, str) and frame2 not in ("", "0"):
                    seen_multi_layer_measure = True
                    break

    assert archives_read == EXPECTED_ARCHIVES
    assert entries_located > 0, "no entries were located across the sweep"
    assert seen_multi_layer_measure, "no multi-layer (frame2) measure was seen across the sweep"


def test_layers_are_recorded_and_multi_layer_measures_exist() -> None:
    """`layer` must be populated, and the corpus must actually exercise layers > 1.

    Without the second assertion this would pass on a corpus where every measure
    used only layer 1, proving nothing about the field that matters.
    """
    from collections import Counter

    seen: Counter[int] = Counter()
    multi_layer_measures = 0
    for path in _archives()[:40]:
        document = parse_enigma(score_xml(path))
        located = locate_entries(document)
        seen.update(where.layer for where in located.values())
        by_measure: dict[tuple[int, int], set[int]] = {}
        for where in located.values():
            by_measure.setdefault((where.staff, where.measure), set()).add(where.layer)
        multi_layer_measures += sum(1 for layers in by_measure.values() if len(layers) > 1)

    assert seen, "no entries located"
    assert set(seen) <= {1, 2, 3, 4}, f"layer outside 1-4: {sorted(seen)}"
    assert seen[1] > 0
    assert multi_layer_measures > 0, "corpus exercises only layer 1; the field is untested"


RETURNS_TO_C = 18
"""Times a measure drops its `keySig` while a non-C key is running.

A `measSpec` that carries no `keySig` is C major. Reading the absence as
"carry the previous key forward" instead keeps a piece in its opening key
through every passage that returns to C, and the reader did exactly that until
`Easy Holiday Ukulele Songbook.musx` was rendered: key=1 through measure 32, no
element for 33-52, key=1 again from 53, and Finale showing a natural cancelling
the sharp over chords of C, G7 and F.

Each is the start of a passage in C major. Across the corpus they cover 741
measures holding 11,421 entries.

Pinned because **nothing else moved when the rule was corrected**. The full
suite passed under both readings, so every one of those entries was invisible to
every other assertion. This number falling means a passage stopped returning to
C; it rising means more documents do.
"""

DOCUMENTS_RETURNING_TO_C = 15
"""Corpus documents containing at least one such measure."""


def test_a_measure_without_a_keysig_reads_as_c_major_not_the_previous_key() -> None:
    """See `MEASURES_RETURNING_TO_C`. Counts only measures where the two rules
    disagree: a measure with no `keySig` whose running key is not already 0."""
    from finale_file_parser.enigma.location import effective_keys

    measures = 0
    documents = 0
    for path in _archives():
        document = parse_enigma(score_xml(path))
        keys = effective_keys(document)
        specs = {
            int(r.attrs["cmper"]): r
            for r in document.others.of_tag("measSpec")
            if "part" not in r.attrs and "cmper" in r.attrs
        }
        running = 0
        hit = 0
        for measure in sorted(specs):
            record = specs[measure]
            stated = record.fields.get("keySig")
            if stated is None and running != 0:
                hit += 1
            running = keys.get(measure, running)
        if hit:
            documents += 1
            measures += hit

    assert measures == RETURNS_TO_C
    assert documents == DOCUMENTS_RETURNING_TO_C
