"""Unit tests for the report's entry facts. No corpus: every document here is
built in process, so CI runs these even though `corpus/` is gitignored."""

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
from finale_file_parser.enigma.location import _MAX_PLACEMENTS_PER_ENTRY
from finale_file_parser.report.entry_facts import (
    Placement,
    Reference,
    placements_by_entry,
    references_to,
)

EMPTY: tuple[Record, ...] = ()


def _doc(
    details: tuple[Record, ...] = EMPTY,
    others: tuple[Record, ...] = EMPTY,
    entries: tuple[Record, ...] = EMPTY,
) -> EnigmaDocument:
    """A document holding only the pools a test needs."""
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=others),
        details=DetailsPool(records=details),
        entries=EntriesPool(records=entries),
        texts=TextsPool(records=EMPTY),
    )


def test_references_name_only_records_holding_this_entnum() -> None:
    """A record counts as a reference when it names the entry, not when it
    merely sits in the same measure -- otherwise "points at" becomes "is near"."""
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})
    other = Record(tag="articAssign", attrs={"entnum": "11", "inci": "0"}, text="", fields={})
    doc = _doc(details=(artic, other))

    assert references_to(doc, 9) == (
        Reference(pool="details", tag="articAssign", key="(entnum 9, inci 0)"),
    )


def test_a_clean_chain_places_an_entry() -> None:
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    entry = Record(
        tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024", "numNotes": "0"}
    )
    places, unresolved = placements_by_entry(
        _doc(details=(gfhold,), others=(frame,), entries=(entry,))
    )

    assert places[9] == [
        Placement(staff=1, measure=3, layer=1, gfhold_key="(cmper1 1, cmper2 3)", frame=12)
    ]
    assert unresolved.get(9, []) == []


def test_a_missing_frame_spec_still_places_what_it_knows() -> None:
    """The failure `locate_entries` raises on. Staff, measure and layer are all
    known from the gfhold -- only the entry range is lost -- so the report says
    where the entry was meant to sit and which link broke."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, unresolved = placements_by_entry(_doc(details=(gfhold,), entries=(entry,)))

    assert places.get(9, []) == []
    assert unresolved[0] == [
        "gfhold (cmper1 1, cmper2 3) frame1 names frameSpec 12, which is absent"
    ]


def test_an_entry_no_frame_reaches_is_named_as_such() -> None:
    """`locate_entries` raises "orphan entry"; here it is a fact about that
    entry rather than a verdict on the document."""
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, unresolved = placements_by_entry(_doc(entries=(entry,)))

    assert places.get(9, []) == []
    assert unresolved[9] == ["no frame reaches this entry"]


def test_a_part_variant_gfhold_does_not_place_a_second_time() -> None:
    """Score records only, exactly as `locate_entries` does: a linked-part
    gfhold would place the same entry twice and read as a mirror."""
    score = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    part = Record(
        tag="gfhold",
        attrs={"cmper1": "1", "cmper2": "3", "part": "1"},
        text="",
        fields={"frame1": "12"},
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, _ = placements_by_entry(_doc(details=(score, part), others=(frame,), entries=(entry,)))

    assert len(places[9]) == 1


def test_a_mirror_places_one_entry_twice() -> None:
    """Two gfholds naming one frame is a Finale mirror, and both placements are
    real -- this is the shape `locate_entries` was changed to allow."""
    a = Record(tag="gfhold", attrs={"cmper1": "4", "cmper2": "3"}, text="", fields={"frame1": "12"})
    b = Record(
        tag="gfhold", attrs={"cmper1": "14", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, _ = placements_by_entry(_doc(details=(a, b), others=(frame,), entries=(entry,)))

    assert sorted(s for p in places[9] if (s := p.staff) is not None) == [4, 14]


def test_an_enormous_end_entry_does_not_hang() -> None:
    """`startEntry`/`endEntry` are file-supplied integers with no ceiling. The
    walk must follow `next`, not treat [start, end] as a dense arithmetic
    range -- an arithmetic range would iterate without bound here."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": str(10**18)},
    )
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, unresolved = placements_by_entry(
        _doc(details=(gfhold,), others=(frame,), entries=(entry,))
    )

    assert places[9] == [
        Placement(staff=1, measure=3, layer=1, gfhold_key="(cmper1 1, cmper2 3)", frame=12)
    ]
    assert any("chain broke" in message for message in unresolved[0])


def test_a_looping_chain_terminates_via_the_guard() -> None:
    """An entry whose `next` points back at itself is a cycle: every step
    re-claims the same entnum, so the per-entry cap stops it -- deterministically,
    at `_MAX_PLACEMENTS_PER_ENTRY` placements -- long before `_CHAIN_GUARD`'s
    1,000,000-step ceiling would. Pin the placement count so the bound is
    asserted, not incidental to how long the test happens to take."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "999"},
    )
    entry = Record(
        tag="entry", attrs={"entnum": "9", "next": "9"}, text="", fields={"dura": "1024"}
    )
    places, unresolved = placements_by_entry(
        _doc(details=(gfhold,), others=(frame,), entries=(entry,))
    )

    assert len(places[9]) == _MAX_PLACEMENTS_PER_ENTRY
    assert any("cap" in message for message in unresolved[9])


def test_many_claims_on_one_entry_are_capped_across_chains() -> None:
    """`_CHAIN_GUARD` bounds one chain walk; nothing else bounds how many
    separate gfhold/frame chains a hostile file can point at one entry.
    `locate_entries` guards this with `_MAX_PLACEMENTS_PER_ENTRY`, and this
    walk must hold the same line across many distinct, non-cyclic chains, not
    just within one looping chain."""
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    gfholds = tuple(
        Record(
            tag="gfhold",
            attrs={"cmper1": str(staff), "cmper2": "3"},
            text="",
            fields={"frame1": "12"},
        )
        for staff in range(1, _MAX_PLACEMENTS_PER_ENTRY + 10)
    )
    places, unresolved = placements_by_entry(
        _doc(details=gfholds, others=(frame,), entries=(entry,))
    )

    assert len(places[9]) == _MAX_PLACEMENTS_PER_ENTRY
    assert any("cap" in message for message in unresolved[9])
