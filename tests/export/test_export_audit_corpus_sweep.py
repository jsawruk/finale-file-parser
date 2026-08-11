"""Audit the exported MusicXML itself, over the whole corpus.

Every other sweep checks one feature and counts it. This one takes the finished
document and asks whether it holds together: that the part list agrees with the
parts, that groups nest, that measures line up, that beams close, that nothing
carries an attachment it cannot have. Those are invariants of the **output**,
independent of which reader produced it, and they are the checks that catch a
feature breaking a neighbour rather than itself.

It runs over every corpus document rather than a sample, because the failures it
looks for are rare by nature -- one malformed barline in 400 scores is exactly
what a sample misses.

Two things are deliberately **not** asserted, because the corpus shows they are
not invariants:

* **Ties do not pair.** The corpus carries 7,017 tie starts against 6,990 ends;
  27 ties begin and never finish. That is in the files, not in the reading.
* **Voices need not fill their measure.** A second layer holding a half note in
  a whole-note bar is ordinary Finale, and MusicXML represents it directly.

Report counts only -- never a corpus filename, title, or lyric.
"""

from __future__ import annotations

import collections
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest
from corpus_files import corpus_paths
from defusedxml import ElementTree as DET

from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.ir import Part, Score

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPORTED = 401
"""Corpus documents that export -- **every `.musx` in the corpus**.

Was 398. The three added were not failing to decode: they were failing to
build, on a linked-part `tupletDef` override read as if it were a tuplet
definition. See `enigma.tuplet.tuplets_by_entry`."""

LYRICS_ON_RESTS = 165
"""Syllables Finale itself attaches to a rest.

Not a defect and not ours: the `.musx` carries exactly this many `lyrDataVerse`
records whose entry is a rest, against 16,591 on notes. Pinned so that a change
in the count means the lyric-to-entry mapping moved, rather than going unnoticed.
"""

MUS_EXPORTED = 231
"""`.mus` documents that export. The same invariants are asserted on them: a
reader-specific defect would otherwise hide behind the `.musx` path.

Was 93 until the 2001-2005 reader landed, then 123 -- and 123 was measured
through a case-sensitive glob that never saw the corpus's 101 `.MUS` files at
all. The Windows cohort had been outside this audit since it was written, and
nothing failed to say so, because a sweep that walks fewer files simply reports
a smaller number. Every one of the 99 documents that walk now brings in passes
every invariant below unchanged. The last two arrived when a breve and a dotted
whole stopped being refused as durations.

Was 230. `Bach Concerto.MUS` joined once a mirrored entry could be placed on
every staff that shows it, rather than refused. See `MIRRORED_MEASURES`.
"""

MIRRORED_MEASURES = 42
"""Measures of `Bach Concerto.MUS` that staves 4 and 14 both display.

Asserted at the export level, not just at placement: this is the layer a user
actually sees, and it is where a mirror that resolved but never got written
would show up.
"""


_Contents = dict[int, list[tuple[tuple[tuple[str, int, int], ...], Fraction]]]


def _by_measure(part: Part) -> _Contents:
    """Measure number -> the pitches and durations it holds, spelling included."""
    return {
        m.number: [
            (tuple((p.step, p.octave, p.alteration) for p in e.pitches), e.duration)
            for v in m.voices
            for e in v.events
        ]
        for m in part.measures
    }


_BARLINE_ORDER = ("bar-style", "ending", "repeat")


def musx_files() -> list[Path]:
    return corpus_paths(".musx")


def _rendered(scores: list[tuple[Path, Score]]) -> list[tuple[str, Score, ET.Element]]:
    """Each score with the document it renders to.

    Both are kept because the completeness check needs to compare them, and
    exporting the corpus a second time to get the other half costs more than
    holding it.
    """
    out: list[tuple[str, Score, ET.Element]] = []
    for path, score in scores:
        element: ET.Element = DET.fromstring(to_musicxml(score).decode())
        out.append((path.name, score, element))
    return out


@pytest.fixture(scope="module")
def rendered(musx_scores: list[tuple[Path, Score]]) -> list[tuple[str, Score, ET.Element]]:
    return _rendered(musx_scores)


@pytest.fixture(scope="module")
def documents(rendered: list[tuple[str, Score, ET.Element]]) -> list[tuple[str, ET.Element]]:
    return [(name, element) for name, _, element in rendered]


@pytest.fixture(scope="module")
def mus_documents(mus_scores: list[tuple[Path, Score]]) -> list[tuple[str, ET.Element]]:
    return [(name, element) for name, _, element in _rendered(mus_scores)]


def test_the_mus_path_exports_and_holds_together(
    mus_documents: list[tuple[str, ET.Element]],
) -> None:
    """Every structural invariant above, asserted on the legacy reader too."""
    assert len(mus_documents) == MUS_EXPORTED
    test_the_part_list_matches_the_parts_in_order(mus_documents)
    test_part_groups_pair_and_nest(mus_documents)
    test_every_part_has_the_same_measures_numbered_from_one(mus_documents)
    test_beams_close_within_their_measure_and_voice(mus_documents)
    test_barlines_are_well_formed(mus_documents)
    test_durations_are_positive_integers_against_a_declared_divisions(mus_documents)


def test_a_mirrored_staff_exports_the_music_it_displays(
    mus_scores: list[tuple[Path, Score]],
) -> None:
    """See `MIRRORED_MEASURES`."""
    score = next(s for path, s in mus_scores if path.name == "Bach Concerto.MUS")
    parts = {p.id: p for p in score.parts}
    source, mirror = _by_measure(parts["P4"]), _by_measure(parts["P14"])
    agreeing = [
        number for number, events in source.items() if events and mirror.get(number) == events
    ]
    assert len(agreeing) >= MIRRORED_MEASURES


def test_nothing_the_ir_holds_is_dropped_on_the_way_out(
    rendered: list[tuple[str, Score, ET.Element]],
) -> None:
    """Completeness, end to end: every attachment the IR carries reaches the
    document. A feature wired into `to_ir` but not into the exporter looks
    exactly like one that was never read.
    """
    totals: collections.Counter[str] = collections.Counter()
    for _, score, doc in rendered:
        totals["ir lyrics"] += _count(score, "lyrics")
        totals["xml lyrics"] += len(list(doc.iter("lyric")))
        totals["ir beams"] += _count(score, "beams")
        totals["xml beams"] += len(list(doc.iter("beam")))
        totals["ir articulations"] += _count(score, "articulations")
        totals["xml articulations"] += sum(len(list(a)) for a in doc.iter("articulations"))
        totals["ir directions"] += sum(len(m.directions) for p in score.parts for m in p.measures)
        totals["xml directions"] += len(list(doc.iter("direction")))
    for name in ("lyrics", "beams", "articulations", "directions"):
        assert totals[f"ir {name}"] == totals[f"xml {name}"], f"{name} lost between IR and XML"
        assert totals[f"ir {name}"] > 0, f"no {name} in the corpus; that path is untested here"


def _count(score: Score, attribute: str) -> int:
    return sum(
        len(getattr(event, attribute))
        for part in score.parts
        for measure in part.measures
        for voice in measure.voices
        for event in voice.events
    )


def test_the_whole_corpus_exports(documents: list[tuple[str, ET.Element]]) -> None:
    assert len(documents) == EXPORTED


def test_the_part_list_matches_the_parts_in_order(
    documents: list[tuple[str, ET.Element]],
) -> None:
    """A part with no `score-part` is a part no reader will show."""
    for _, doc in documents:
        listed = [e.get("id") for e in doc.findall("./part-list/score-part")]
        assert [p.get("id") for p in doc.findall("./part")] == listed


def test_part_groups_pair_and_nest(documents: list[tuple[str, ET.Element]]) -> None:
    """Interleaved groups are what a wrong closing order produces, and the
    schema permits them -- no reader draws them."""
    for _, doc in documents:
        stack: list[str | None] = []
        part_list = doc.find("part-list")
        assert part_list is not None
        for child in part_list:
            if child.tag != "part-group":
                continue
            if child.get("type") == "start":
                assert child.get("number") not in stack, "group number reused while open"
                stack.append(child.get("number"))
            else:
                assert stack, "group closed with none open"
                assert stack.pop() == child.get("number"), "groups interleave rather than nest"
        assert not stack, "group left open"


def test_every_part_has_the_same_measures_numbered_from_one(
    documents: list[tuple[str, ET.Element]],
) -> None:
    for _, doc in documents:
        lists = {
            tuple(m.get("number") for m in part.findall("measure"))
            for part in doc.findall("./part")
        }
        assert len(lists) == 1, "parts disagree about which measures exist"
        numbers = next(iter(lists))
        assert list(numbers) == [str(n) for n in range(1, len(numbers) + 1)]


def test_notes_carry_only_what_they_can(documents: list[tuple[str, ET.Element]]) -> None:
    """The cross-feature check: a measure rest with a beam, or a chord's second
    note with a lyric, is what one feature breaking another looks like."""
    lyrics_on_rests = 0
    for _, doc in documents:
        for note in doc.iter("note"):
            rest = note.find("rest")
            if rest is not None and rest.get("measure") == "yes":
                assert note.find("type") is None, "measure rest carries a note type"
                assert note.find("beam") is None, "measure rest carries a beam"
                assert note.find("lyric") is None, "measure rest carries a lyric"
            elif note.find("grace") is None:
                assert note.findtext("type"), "note without a type"
            if note.find("chord") is not None:
                assert note.find("lyric") is None, "a chord's later note carries a lyric"
                assert note.find("beam") is None, "a chord's later note carries a beam"
            if rest is not None and note.find("lyric") is not None:
                lyrics_on_rests += 1
    assert lyrics_on_rests == LYRICS_ON_RESTS


def test_beams_close_within_their_measure_and_voice(
    documents: list[tuple[str, ET.Element]],
) -> None:
    """An unbalanced level renders as a beam running off the end of the bar."""
    for _, doc in documents:
        for measure in doc.iter("measure"):
            levels: dict[tuple[str, str | None], list[str | None]] = collections.defaultdict(list)
            for note in measure.findall("note"):
                voice = note.findtext("voice") or "1"
                for beam in note.findall("beam"):
                    levels[(voice, beam.get("number"))].append(beam.text)
            for kinds in levels.values():
                depth = 0
                for kind in kinds:
                    depth += 1 if kind == "begin" else -1 if kind == "end" else 0
                    assert depth >= 0, "beam ends before it begins"
                assert depth == 0, "beam level left open in a measure"


def test_barlines_are_well_formed(documents: list[tuple[str, ET.Element]]) -> None:
    """One bar-style each, children in schema order, and every ending bracket
    opened before it is closed."""
    for _, doc in documents:
        for part in doc.findall("./part"):
            open_endings: set[str | None] = set()
            for barline in part.iter("barline"):
                assert len(barline.findall("bar-style")) <= 1, "two bar-styles in one barline"
                tags = [c.tag for c in barline if c.tag in _BARLINE_ORDER]
                assert tags == sorted(tags, key=_BARLINE_ORDER.index), "barline out of order"
                for ending in barline.findall("ending"):
                    number = ending.get("number")
                    if ending.get("type") == "start":
                        open_endings.add(number)
                    else:
                        assert number in open_endings, "ending closed without being opened"
                        open_endings.discard(number)
            assert not open_endings, "ending bracket left open"


def test_durations_are_positive_integers_against_a_declared_divisions(
    documents: list[tuple[str, ET.Element]],
) -> None:
    """`divisions` must be declared before any duration is read, and a
    non-positive duration is what a rounding error looks like."""
    for _, doc in documents:
        for part in doc.findall("./part"):
            divisions = None
            for measure in part.findall("measure"):
                declared = measure.findtext("./attributes/divisions")
                if declared is not None:
                    divisions = int(declared)
                    assert divisions > 0
                for note in measure.findall("note"):
                    duration = note.findtext("duration")
                    if note.find("grace") is not None:
                        assert duration is None, "grace note carries a duration"
                        continue
                    assert divisions is not None, "duration before any divisions"
                    assert duration is not None and int(duration) > 0
