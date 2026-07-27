"""Unit tests for repeat structure.

The interesting part is the ending bracket, whose extent is spread across three
records and one flag that does not mean what it looks like it means. These are
written as small measure layouts rather than as documents, because the cases
that matter -- a bracket with unflagged measures inside it, and two brackets
back to back -- are ones the corpus has few of.
"""

from __future__ import annotations

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
from finale_file_parser.enigma.repeats import repeats_for

EMPTY: tuple[Record, ...] = ()


def measure(number: int, *flags: str) -> Record:
    """A `measSpec`. Flags are empty elements, as in a `.musx`."""
    return Record(
        tag="measSpec",
        attrs={"cmper": str(number)},
        text="",
        fields=dict.fromkeys(flags, ""),
    )


def ending_start(number: int) -> Record:
    return Record(tag="repeatEndingStart", attrs={"cmper": str(number)}, text="", fields={})


def pass_list(number: int, *acts: int) -> Record:
    value: str | tuple[str, ...] = tuple(str(a) for a in acts) if len(acts) > 1 else str(acts[0])
    return Record(
        tag="repeatPassList", attrs={"cmper": str(number)}, text="", fields={"act": value}
    )


def repeat_back(number: int, actuate: int | None = None) -> Record:
    fields = {} if actuate is None else {"actuate": str(actuate)}
    return Record(tag="repeatBack", attrs={"cmper": str(number)}, text="", fields=fields)


def document(*records: Record) -> EnigmaDocument:
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=records),
        details=DetailsPool(records=EMPTY),
        entries=EntriesPool(records=EMPTY),
        texts=TextsPool(records=EMPTY),
    )


def test_a_forward_repeat_is_a_measure_flag() -> None:
    repeats = repeats_for(document(measure(1), measure(5, "forRepBar")))
    assert repeats.get(5).forward
    assert not repeats.get(1).forward


def test_a_backward_repeat_is_a_measure_flag() -> None:
    repeats = repeats_for(document(measure(8, "bacRepBar"), repeat_back(8)))
    assert repeats.get(8).backward
    assert repeats.get(8).passes == 2


def test_total_passes_comes_from_the_repeat_record() -> None:
    repeats = repeats_for(document(measure(8, "bacRepBar"), repeat_back(8, actuate=3)))
    assert repeats.get(8).passes == 3


def test_a_measure_with_no_repeat_reports_nothing() -> None:
    repeats = repeats_for(document(measure(1), measure(2)))
    assert repeats.get(1).endings == ()
    assert not repeats.get(2).forward and not repeats.get(2).backward


def test_an_ending_spans_to_its_last_flagged_measure() -> None:
    """`barEnding` marks the bracket's first and last measure -- **not** every
    measure it covers. A four-measure first ending flags 1 and 4 and leaves 2
    and 3 clear, so reading the flags as a consecutive run stops the bracket at
    measure 1 and loses three measures of it.
    """
    repeats = repeats_for(
        document(
            measure(1, "barEnding"),
            measure(2),
            measure(3),
            measure(4, "barEnding", "bacRepBar"),
            measure(5),
            ending_start(1),
            pass_list(1, 1),
            repeat_back(4),
        )
    )
    assert [e.type for e in repeats.get(1).endings] == ["start"]
    assert [e.type for e in repeats.get(4).endings] == ["stop"]
    assert repeats.get(2).endings == ()


def test_a_bracket_stops_where_the_next_one_starts() -> None:
    """Back-to-back endings: the first must not swallow the second.

    Taking the last flagged measure without that boundary makes ending 1 run to
    measure 2 -- on top of ending 2, which starts there.
    """
    repeats = repeats_for(
        document(
            measure(1, "barEnding", "bacRepBar"),
            measure(2, "barEnding"),
            ending_start(1),
            ending_start(2),
            pass_list(1, 1),
            pass_list(2, 2),
            repeat_back(1),
        )
    )
    assert [(e.numbers, e.type) for e in repeats.get(1).endings] == [
        ((1,), "start"),
        ((1,), "stop"),
    ]
    assert [(e.numbers, e.type) for e in repeats.get(2).endings] == [
        ((2,), "start"),
        ((2,), "discontinue"),
    ]


def test_a_bracket_with_no_backward_repeat_is_discontinued() -> None:
    """A final "2." ending just stops being drawn; only a bracket that actually
    repeats gets the downward hook MusicXML calls "stop"."""
    repeats = repeats_for(document(measure(9, "barEnding"), ending_start(9), pass_list(9, 2)))
    assert [e.type for e in repeats.get(9).endings] == ["start", "discontinue"]


def test_an_ending_taken_on_two_passes_carries_both_numbers() -> None:
    repeats = repeats_for(document(measure(3, "barEnding"), ending_start(3), pass_list(3, 1, 2)))
    assert repeats.get(3).endings[0].numbers == (1, 2)


def test_a_single_measure_ending_opens_and_closes_on_itself() -> None:
    repeats = repeats_for(
        document(measure(3, "barEnding", "bacRepBar"), ending_start(3), pass_list(3, 1))
    )
    assert [e.type for e in repeats.get(3).endings] == ["start", "stop"]


def test_part_records_are_ignored() -> None:
    """A part can override a barline; honouring that would give the score a
    repeat it does not have."""
    override = Record(
        tag="measSpec",
        attrs={"cmper": "4", "part": "1"},
        text="",
        fields={"forRepBar": ""},
    )
    repeats = repeats_for(document(measure(4), override))
    assert not repeats.get(4).forward


def test_a_flagged_measure_with_no_ending_record_starts_nothing() -> None:
    """`barEnding` alone does not open a bracket -- `repeatEndingStart` does.

    The corpus has three such orphan flags; inventing a bracket for them would
    put a volta on music that has none.
    """
    repeats = repeats_for(document(measure(7, "barEnding")))
    assert repeats.get(7).endings == ()
