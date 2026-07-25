"""Tests for the MusicXML exporter."""

from __future__ import annotations

from fractions import Fraction

import pytest
from defusedxml import ElementTree as DET

from finale_file_parser.export.musicxml import ExportError, to_musicxml
from finale_file_parser.ir import Event, Measure, Part, Pitch, Score, TimeSignature, Voice

QUARTER = Fraction(1, 4)
EIGHTH = Fraction(1, 8)
TRIPLET_EIGHTH = Fraction(1, 12)


def _score(*events: Event, **measure_kwargs: object) -> Score:
    measure = Measure(number=1, voices=(Voice(number=1, events=events),), **measure_kwargs)  # type: ignore[arg-type]
    return Score(parts=(Part(id="P1", name="Flute", measures=(measure,)),))


def _tree(score: Score):  # type: ignore[no-untyped-def]
    return DET.fromstring(to_musicxml(score).decode())


def _note(**kwargs: object) -> Event:
    base: dict[str, object] = {
        "duration": QUARTER,
        "written_duration": QUARTER,
        "pitches": (Pitch("C", 4, 0),),
    }
    base.update(kwargs)
    return Event(**base)  # type: ignore[arg-type]


def test_emits_a_well_formed_document() -> None:
    root = _tree(_score(_note()))
    assert root.tag == "score-partwise"
    assert root.findtext("./part-list/score-part/part-name") == "Flute"
    assert root.findtext("./part/measure/note/pitch/step") == "C"


def test_divisions_accommodate_triplets() -> None:
    """A triplet eighth is 1/12 of a whole note.

    With divisions=1 its duration rounds to zero, so the count must clear the
    denominator -- here 3 per quarter.
    """
    root = _tree(
        _score(_note(duration=TRIPLET_EIGHTH, written_duration=EIGHTH, tuplet_ratio=Fraction(2, 3)))
    )
    assert root.findtext("./part/measure/attributes/divisions") == "3"
    assert root.findtext("./part/measure/note/duration") == "1"


def test_tuplet_emits_time_modification_the_right_way_round() -> None:
    """A triplet is 3 notes in the time of 2, while its sounded ratio is 2/3."""
    root = _tree(
        _score(_note(duration=TRIPLET_EIGHTH, written_duration=EIGHTH, tuplet_ratio=Fraction(2, 3)))
    )
    modification = root.find("./part/measure/note/time-modification")
    assert modification is not None
    assert modification.findtext("actual-notes") == "3"
    assert modification.findtext("normal-notes") == "2"


def test_grace_notes_omit_duration_entirely() -> None:
    """The schema requires duration > 0, and a grace note has none.

    Writing zero fails validation -- this is the bug the W3C schema caught on real
    corpus output, not a hypothetical.
    """
    root = _tree(_score(_note(duration=Fraction(0), is_grace=True), _note()))
    notes = root.findall("./part/measure/note")
    assert notes[0].find("grace") is not None
    assert notes[0].find("duration") is None
    assert notes[1].find("grace") is None
    assert notes[1].findtext("duration") == "1"


def test_grace_notes_do_not_affect_divisions() -> None:
    """A zero duration must not drag the divisions calculation."""
    root = _tree(_score(_note(duration=Fraction(0), is_grace=True), _note()))
    assert root.findtext("./part/measure/attributes/divisions") == "1"


def test_chord_marks_only_the_notes_after_the_first() -> None:
    root = _tree(_score(_note(pitches=(Pitch("C", 4, 0), Pitch("E", 4, 1), Pitch("G", 4, 0)))))
    notes = root.findall("./part/measure/note")
    assert [n.find("chord") is None for n in notes] == [True, False, False]
    assert notes[1].findtext("./pitch/alter") == "1"


def test_rest_has_no_pitch() -> None:
    root = _tree(_score(_note(pitches=())))
    note = root.find("./part/measure/note")
    assert note is not None
    assert note.find("rest") is not None
    assert note.find("pitch") is None


def test_ties_emit_both_sound_and_notation() -> None:
    """`<tie>` is the sounding instruction, `<tied>` the visual slur.

    Most applications need both for a tie to survive a round trip.
    """
    root = _tree(_score(_note(tie_start=True, tie_end=True)))
    note = root.find("./part/measure/note")
    assert note is not None
    assert {t.get("type") for t in note.findall("tie")} == {"start", "stop"}
    assert {t.get("type") for t in note.findall("./notations/tied")} == {"start", "stop"}


def test_dotted_note_type_is_the_undotted_base() -> None:
    """A dotted quarter is 3/8 of a whole, which is not a note value."""
    root = _tree(_score(_note(duration=Fraction(3, 8), written_duration=Fraction(3, 8), dots=1)))
    note = root.find("./part/measure/note")
    assert note is not None
    assert note.findtext("type") == "quarter"
    assert len(note.findall("dot")) == 1


def test_attributes_are_emitted_only_where_they_change() -> None:
    first = Measure(
        number=1,
        voices=(Voice(number=1, events=(_note(),)),),
        key_fifths=2,
        time=TimeSignature(4, 4),
        clef_sign="G",
        clef_line=2,
    )
    second = Measure(number=2, voices=(Voice(number=1, events=(_note(),)),))
    score = Score(parts=(Part(id="P1", name="P", measures=(first, second)),))
    measures = _tree(score).findall("./part/measure")
    assert measures[0].find("attributes") is not None
    assert measures[1].find("attributes") is None, "unchanged attributes must not repeat"


def test_second_voice_is_preceded_by_a_backup() -> None:
    measure = Measure(
        number=1,
        voices=(
            Voice(number=1, events=(_note(), _note())),
            Voice(number=2, events=(_note(),)),
        ),
    )
    root = _tree(Score(parts=(Part(id="P1", name="P", measures=(measure,)),)))
    backup = root.find("./part/measure/backup")
    assert backup is not None
    assert backup.findtext("duration") == "2", "must rewind by the first voice's full length"


def test_unrepresentable_duration_raises() -> None:
    with pytest.raises(ExportError, match="note value"):
        to_musicxml(_score(_note(written_duration=Fraction(5, 16))))
