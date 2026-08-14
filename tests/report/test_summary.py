"""Tests for the score and document summarisers."""

from __future__ import annotations

from fractions import Fraction

from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
)
from finale_file_parser.ir import Event, Measure, Part, Pitch, Score, TimeSignature, Voice
from finale_file_parser.report.summary import summarise_document, summarise_score


def _score() -> Score:
    event = Event(
        duration=Fraction(1, 4),
        written_duration=Fraction(1, 4),
        pitches=(Pitch("C", 4, 0),),
    )
    measure = Measure(
        number=1,
        voices=(Voice(number=1, events=(event,)),),
        time=TimeSignature(beats=4, beat_type=4),
        clef_sign="G",
    )
    return Score(parts=(Part(id="P1", name="Flute", measures=(measure,)),))


def test_score_summary_carries_per_measure_shape() -> None:
    """Per measure, not just totals: a measure that came out empty is the thing
    a reader is looking for, and a total hides it."""
    summary = summarise_score(_score())
    assert summary["parts"] == [
        {
            "id": "P1",
            "name": "Flute",
            "measures": [
                {
                    "number": 1,
                    "time": "4/4",
                    "clef": "G",
                    "key": None,
                    "events": 1,
                    "pitches": 1,
                }
            ],
        }
    ]


def test_score_summary_totals_agree_with_the_parts() -> None:
    summary = summarise_score(_score())
    assert summary["totals"] == {"parts": 1, "measures": 1, "events": 1, "pitches": 1}


def _document(*records: Record) -> EnigmaDocument:
    empty: tuple[Record, ...] = ()
    return EnigmaDocument(
        version="test",
        header=Pool(records=empty),
        mappings=Pool(records=empty),
        options=OptionsPool(records=empty),
        others=OthersPool(records=records),
        details=DetailsPool(records=empty),
        entries=EntriesPool(records=empty),
        texts=TextsPool(records=empty),
    )


def test_document_summary_counts_records_by_pool_and_tag() -> None:
    document = _document(
        Record(tag="measSpec", attrs={"cmper": "1"}, text="", fields={}),
        Record(tag="measSpec", attrs={"cmper": "2"}, text="", fields={}),
        Record(tag="frameSpec", attrs={"cmper": "1"}, text="", fields={}),
    )
    summary = summarise_document(document)
    assert summary["pools"]["others"] == {"measSpec": 2, "frameSpec": 1}


def test_document_summary_names_the_untranslated_gaps() -> None:
    """A .mus is read by reverse engineering, so what is *not* carried is part of
    the answer."""
    summary = summarise_document(_document())
    assert isinstance(summary["untranslated"], list)
    assert summary["untranslated"], "UNTRANSLATED must be surfaced"


def test_the_music_tree_keeps_layers_apart() -> None:
    """Staff, measure, layer, event -- the shape the music has, rather than the
    shape the file stores.

    Layers stay separate because each independently fills the measure: flatten
    them and a two-layer bar looks like it holds twice its time signature.
    """
    from finale_file_parser.report.summary import music_tree

    tree = music_tree(_score())
    assert [part["id"] for part in tree["parts"]] == ["P1"]
    part = tree["parts"][0]
    assert part["staff"] == 1, "the staff number is recovered from the part id"
    assert [m["number"] for m in part["measures"]] == [1]
    voice = part["measures"][0]["voices"][0]
    assert voice["number"] == 1
    assert voice["events"] == [
        {"duration": "1/4", "pitches": ["C4"], "rest": False, "tie": None, "grace": False}
    ]
    assert voice["mirrors"] == [], "nothing mirrors here, and the field says so rather than absent"


def test_a_mirrored_layer_names_the_other_staves_without_naming_an_original() -> None:
    """A mirror is one staff displaying another's music. The file marks neither
    placement as the copy, so the tree states only which other staves show the
    same entries -- symmetric, and true from either side."""
    from finale_file_parser.report.summary import music_tree

    tree = music_tree(_score(), {(1, 1, 1): [2]})
    assert tree["parts"][0]["measures"][0]["voices"][0]["mirrors"] == [2]


def test_a_pitch_spells_its_alteration_rather_than_folding_it_in() -> None:
    """`F#4`, not the semitone. Someone chasing a spelling bug needs to see
    which of step and alteration came out wrong."""
    from finale_file_parser.report.summary import _pitch

    assert _pitch(Pitch("F", 4, 1)) == "F#4"
    assert _pitch(Pitch("B", 3, -1)) == "Bb3"
    assert _pitch(Pitch("C", 4, 0)) == "C4"
    assert _pitch(Pitch("C", 4, 2)) == "Cx4"
