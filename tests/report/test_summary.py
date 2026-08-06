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
