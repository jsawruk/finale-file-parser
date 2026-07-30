"""Sweep the 2001-2005 `.mus` record rows, and pin what is *not* yet solved.

Skipped wherever corpus/ is absent (e.g. CI). This cohort has **no paired
`.musx`**, so the checks here are of three kinds:

* the ETF spec's own documented field order, applied to real files
  (`^MS(1) 600 0 4 1024 1 16` -> measpace, key, beats, divbeat, auxflag, meflag);
* cross-references closing inside a document (a gfhold's frame is a real frame,
  a frame's entry numbers are real entries);
* a **control against the 2011 cohort**, where the same pipeline demonstrably
  works, so a metric can be checked before it is trusted.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_details import TAG_GFHOLD, read_mus_details
from finale_file_parser.enigma.mus_entries import read_mus_entry_records
from finale_file_parser.enigma.mus_others import TAG_FRAME_SPEC, read_mus_others
from finale_file_parser.enigma.mus_rows import MusRows, read_mus_rows
from finale_file_parser.version import mus as mus_header

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

LAST_DCL_YEAR = 2005

EXPECTED_DOCUMENTS = 139

EXPECTED_MEASURES = 4113
"""`MS` records across the cohort, one per measure."""

EXPECTED_STAVES = 571
EXPECTED_THREE_INCIDENCE_DOCS = 102
EXPECTED_SIX_INCIDENCE_DOCS = 37
"""A staff spec is three incidences in a 2001 file and six in a 2005 one.
`etfspec.pdf` documents the three-incidence shape and its field order."""

FRAMES_CHECKED_AGAINST_ENTRIES = 13710
"""Frames in documents whose entry pool also reads.

Was 13,322 until a breve and a dotted whole stopped being refused: two more
documents' pools read end to end, so their frames are checked too."""

NOTE_VALUES = frozenset(
    {64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192}
)
"""Written durations the corpus holds, in EDU. 6144 is a dotted whole and 8192 a
breve; both appear once the note-value model stops refusing them."""

LAYERS = 4
"""Frame slots per `GF` record, one per Finale layer, from the base."""

FRAMES_REFERENCED = 13241
FRAMES_TOTAL = 13710
"""Frames a `GF` names, once the base is chosen by the staff-spec shape.
Was 4,711 while the base was read as +6 for every document."""

ENTRY_COVERAGE = 0.92
"""Entries reachable through gfhold -> frame -> chain. Was 0.293."""


def _mus_files() -> list[Path]:
    """Case-insensitive: a case-sensitive glob drops the whole Windows cohort."""
    return sorted(p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".mus")


def _by_era(old: bool) -> list[Path]:
    out = []
    for path in _mus_files():
        year = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE]).year
        if year is not None and (year <= LAST_DCL_YEAR) == old:
            out.append(path)
    return out


def _u16(payload: bytes, offset: int, rows: MusRows) -> int:
    return int.from_bytes(payload[offset : offset + 2], rows.byte_order)


def _u32(payload: bytes, offset: int, rows: MusRows) -> int:
    return int.from_bytes(payload[offset : offset + 4], rows.byte_order)


def _frame_base(rows: MusRows) -> int:
    """Where a `GF` record's frame array starts.

    The 2005 layout carries two more bytes ahead of it than the 2001 one, and
    the staff spec's incidence count is what tells the eras apart -- three in a
    2001 file, six in a 2005 one.
    """
    specs = [record for (tag, _), record in rows.others.items() if tag == "IS"]
    return 4 if specs and specs[0].incidences == 3 else 6


def test_every_dcl_document_reads_as_rows() -> None:
    failures: list[str] = []
    read = 0
    for path in _by_era(old=True):
        try:
            read_mus_rows(path)
        except Exception as exc:  # noqa: BLE001 - collecting, not suppressing
            failures.append(type(exc).__name__)
        else:
            read += 1
    assert not failures, f"{len(failures)} failed: {failures[:5]}"
    assert read == EXPECTED_DOCUMENTS


def test_measure_specs_follow_the_spec_field_order() -> None:
    """`^MS(n)` is measpace, key, beats, divbeat, auxflag, meflag.

    Wrong field order shows up immediately: `beats` lands on a measure width in
    the hundreds and `divbeat` on a key signature.
    """
    measures = gapless = 0
    for path in _by_era(old=True):
        rows = read_mus_rows(path)
        keys = sorted(cmper for tag, cmper in rows.others if tag == "MS")
        if keys and keys == list(range(1, len(keys) + 1)):
            gapless += 1
        for cmper in keys:
            payload = rows.others[("MS", cmper)].payload
            beats = _u16(payload, 4, rows)
            divbeat = _u16(payload, 6, rows)
            assert 1 <= beats <= 32, "beats outside any real time signature"
            assert divbeat in NOTE_VALUES, "divbeat is not a note value"
            measures += 1
    assert measures == EXPECTED_MEASURES
    assert gapless == EXPECTED_DOCUMENTS


def test_staff_specs_come_in_the_two_documented_shapes() -> None:
    staves = 0
    shapes: dict[int, int] = {}
    for path in _by_era(old=True):
        rows = read_mus_rows(path)
        specs = [record for (tag, _), record in rows.others.items() if tag == "IS"]
        assert specs, "every document has at least one staff"
        shapes[specs[0].incidences] = shapes.get(specs[0].incidences, 0) + 1
        staves += len(specs)
    assert staves == EXPECTED_STAVES
    assert shapes == {3: EXPECTED_THREE_INCIDENCE_DOCS, 6: EXPECTED_SIX_INCIDENCE_DOCS}


def test_a_frames_entry_numbers_are_real_entries() -> None:
    """`FR(n)` holds startEntry and endEntry as u32, as the 2011 `frameSpec` does."""
    checked = start_real = end_real = ordered = 0
    for path in _by_era(old=True):
        rows = read_mus_rows(path)
        try:
            entnums = {int(r.attrs["entnum"]) for r in read_mus_entry_records(path)}
        except CorruptScoreError:
            continue
        if not entnums:
            continue
        for (tag, _), record in rows.others.items():
            if tag != "FR":
                continue
            start, end = _u32(record.payload, 0, rows), _u32(record.payload, 4, rows)
            if not start and not end:
                continue  # an empty frame
            checked += 1
            start_real += start in entnums
            end_real += end in entnums
            ordered += start <= end
    assert checked == FRAMES_CHECKED_AGAINST_ENTRIES
    assert start_real / checked >= 0.99
    assert end_real / checked >= 0.99
    # 275 frames run backwards. That is not a decode error: the 2011 cohort,
    # whose frameSpec is confirmed field-by-field against paired .musx files,
    # does the same thing on 24 of 10,465 records.
    assert ordered / checked >= 0.97


def test_the_frame_slots_sit_at_a_base_the_staff_spec_shape_selects() -> None:
    """A `GF` record holds a frame per layer, and where that array starts
    depends on the era: **+4 in a 2001 file, +6 in a 2005 one**, told apart by
    whether the staff spec is three incidences or six.

    A correction, recorded because the wrong version shipped first: an earlier
    revision of this file called +4 a coincidence, on the grounds that it is
    `clefPercent` and always 75. It is 75 in only 5,205 of 14,191 records -- in
    34 documents, all of them 2005-era. That conclusion came from generalising
    one sampled document, and it cost the frame link a release.

    What makes the rule more than a fit: choosing the base per document by
    whichever reaches more entries picks exactly what the staff-spec shape
    predicts, in 134 of 134 documents.
    """
    resolved = non_zero = 0
    for path in _by_era(old=True):
        rows = read_mus_rows(path)
        frames = {cmper for tag, cmper in rows.others if tag == "FR"}
        if not frames:
            continue
        base = _frame_base(rows)
        for (tag, _, _), record in rows.details.items():
            if tag != "GF":
                continue
            for layer in range(LAYERS):
                frame = _u16(record.payload, base + 2 * layer, rows)
                if frame:
                    non_zero += 1
                    resolved += frame in frames
    assert non_zero, "no frame references to check"
    assert resolved / non_zero >= 0.99


def test_the_frame_link_reaches_almost_every_frame() -> None:
    """Pins the link, which the previous release had at 34%.

    Reading the frame array at the base the staff-spec shape selects takes
    frames referenced from 4,711 to 13,241 of 13,322, and entries reached from
    29.3% to 92.3%.
    """
    referenced = total = 0
    for path in _by_era(old=True):
        rows = read_mus_rows(path)
        frames = {cmper for tag, cmper in rows.others if tag == "FR"}
        total += len(frames)
        base = _frame_base(rows)
        seen: set[int] = set()
        for (tag, _, _), record in rows.details.items():
            if tag != "GF":
                continue
            for layer in range(LAYERS):
                frame = _u16(record.payload, base + 2 * layer, rows)
                if frame in frames:
                    seen.add(frame)
        referenced += len(seen)
    assert total == FRAMES_TOTAL
    assert referenced >= FRAMES_REFERENCED, "frames were lost"


def test_the_frame_chain_reaches_most_entries() -> None:
    """Walking gfhold -> frame -> entry chain, how much music is reachable.

    Not yet all of it: 5,435 entries in 56 documents are missed, and only 10 of
    them start a frame nothing references -- so what is left is inside frames
    that *are* referenced, and reads as a second voice hanging off the same
    frame rather than a missing link. That is why this is a floor, not equality.
    """
    reached_total = entries_total = 0
    for path in _by_era(old=True):
        rows = read_mus_rows(path)
        try:
            records = read_mus_entry_records(path)
        except CorruptScoreError:
            continue
        if not records:
            continue
        following = {int(r.attrs["entnum"]): int(r.attrs["next"]) for r in records}
        specs = {cmper: record for (tag, cmper), record in rows.others.items() if tag == "FR"}
        base = _frame_base(rows)
        reached: set[int] = set()
        for (tag, _, _), record in rows.details.items():
            if tag != "GF":
                continue
            for layer in range(LAYERS):
                spec = specs.get(_u16(record.payload, base + 2 * layer, rows))
                if spec is None:
                    continue
                start = _u32(spec.payload, 0, rows)
                end = _u32(spec.payload, 4, rows)
                entry, steps = start, 0
                while entry and entry in following and steps <= len(following):
                    reached.add(entry)
                    if entry == end:
                        break
                    entry = following[entry]
                    steps += 1
        reached_total += len(reached)
        entries_total += len(following)
    assert entries_total
    assert reached_total / entries_total >= ENTRY_COVERAGE


def test_the_same_measurement_is_complete_on_the_2011_cohort() -> None:
    """The control that makes the gap above a finding rather than a bad metric.

    Same question, same arithmetic, on files whose pipeline is known to work:
    every `frameSpec` is referenced and all but a handful of `gfhold`s carry a
    frame. So a 34% result on the other cohort is the data speaking, not the
    measurement.
    """
    referenced = total = with_frame = gfholds = 0
    for path in _by_era(old=False):
        try:
            others = read_mus_others(path)
            details = read_mus_details(path)
        except CorruptScoreError:
            continue
        frames = {r.cmper for r in others if r.tag == TAG_FRAME_SPEC}
        total += len(frames)
        seen: set[int] = set()
        for record in details:
            if record.tag != TAG_GFHOLD:
                continue
            gfholds += 1
            hit = False
            for offset in (6, 8):
                if len(record.payload) >= offset + 2:
                    frame = int.from_bytes(record.payload[offset : offset + 2], "little")
                    if frame in frames:
                        seen.add(frame)
                        hit = True
            with_frame += hit
        referenced += len(seen)
    assert total and gfholds
    assert referenced == total, "every 2011 frameSpec is referenced by a gfhold"
    assert with_frame / gfholds >= 0.99
