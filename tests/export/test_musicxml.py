"""Tests for the MusicXML exporter."""

from __future__ import annotations

from fractions import Fraction

import pytest
from defusedxml import ElementTree as DET

from finale_file_parser.export.musicxml import ExportError, to_musicxml
from finale_file_parser.ir import (
    Beam,
    Event,
    Lyric,
    Measure,
    Part,
    Pitch,
    Score,
    TimeSignature,
    Voice,
)

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


def test_a_lyric_is_emitted_with_its_syllabic_and_text() -> None:
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            lyrics=(Lyric(number=1, text="ho", syllabic="begin"),),
        )
    )
    xml = to_musicxml(score).decode()
    assert '<lyric number="1">' in xml
    assert "<syllabic>begin</syllabic>" in xml
    assert "<text>ho</text>" in xml


def test_a_word_extension_emits_extend() -> None:
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            lyrics=(Lyric(number=1, text="ah", syllabic="single", extend=True),),
        )
    )
    assert "<extend />" in to_musicxml(score).decode()


def test_a_chord_sings_its_syllable_once() -> None:
    """The syllable belongs to the event, not to each pitch: repeating it per
    note of a chord would make the part sing it three times."""
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(
                Pitch(step="C", alteration=0, octave=4),
                Pitch(step="E", alteration=0, octave=4),
            ),
            lyrics=(Lyric(number=1, text="ah", syllabic="single"),),
        )
    )
    assert to_musicxml(score).decode().count("<lyric ") == 1


def test_lyric_comes_after_notations_as_the_schema_requires() -> None:
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            tie_start=True,
            lyrics=(Lyric(number=1, text="ah", syllabic="single"),),
        )
    )
    xml = to_musicxml(score).decode()
    assert xml.index("<notations>") < xml.index("<lyric ")


def test_articulations_are_emitted_inside_notations() -> None:
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            articulations=("staccato", "accent"),
        )
    )
    xml = to_musicxml(score).decode()
    assert "<articulations>" in xml
    assert xml.index("<staccato />") < xml.index("<accent />")


def test_ties_and_articulations_share_one_notations_element() -> None:
    """The schema allows one <notations> per note, with <tied> before
    <articulations>."""
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            tie_start=True,
            articulations=("staccato",),
        )
    )
    xml = to_musicxml(score).decode()
    assert xml.count("<notations>") == 1
    assert xml.index("<tied ") < xml.index("<articulations>")


def test_a_chord_carries_its_articulation_once() -> None:
    score = _score(
        Event(
            duration=Fraction(1, 4),
            written_duration=Fraction(1, 4),
            pitches=(
                Pitch(step="C", alteration=0, octave=4),
                Pitch(step="E", alteration=0, octave=4),
            ),
            articulations=("staccato",),
        )
    )
    assert to_musicxml(score).decode().count("<staccato />") == 1


def test_beams_are_emitted_with_their_level() -> None:
    score = _score(
        Event(
            duration=Fraction(1, 16),
            written_duration=Fraction(1, 16),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            beams=(Beam(number=1, type="begin"), Beam(number=2, type="begin")),
        )
    )
    xml = to_musicxml(score).decode()
    assert '<beam number="1">begin</beam>' in xml
    assert '<beam number="2">begin</beam>' in xml


def test_a_beam_comes_before_notations() -> None:
    """Schema order: <beam> after <time-modification>, before <notations>."""
    score = _score(
        Event(
            duration=Fraction(1, 8),
            written_duration=Fraction(1, 8),
            pitches=(Pitch(step="C", alteration=0, octave=4),),
            beams=(Beam(number=1, type="begin"),),
            articulations=("staccato",),
        )
    )
    xml = to_musicxml(score).decode()
    assert xml.index("<beam ") < xml.index("<notations>")


def test_a_chord_beams_once() -> None:
    """The beam belongs to the stem, not to each pitch."""
    score = _score(
        Event(
            duration=Fraction(1, 8),
            written_duration=Fraction(1, 8),
            pitches=(
                Pitch(step="C", alteration=0, octave=4),
                Pitch(step="E", alteration=0, octave=4),
            ),
            beams=(Beam(number=1, type="begin"),),
        )
    )
    assert to_musicxml(score).decode().count("<beam ") == 1
