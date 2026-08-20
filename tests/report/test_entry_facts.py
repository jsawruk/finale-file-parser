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
from finale_file_parser.enigma.pitch import StaffTransposition
from finale_file_parser.report.entry_facts import (
    Placement,
    Reference,
    build_entry_index,
    decode_entry,
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


def _entry_record(dura: str = "1024", notes: tuple[Record, ...] = EMPTY) -> Record:
    return Record(
        tag="entry",
        attrs={"entnum": "9"},
        text="",
        fields={"dura": dura, "numNotes": str(len(notes)), "note": notes},
    )


def _note(harm_lev: str, harm_alt: str = "0") -> Record:
    return Record(tag="note", attrs={}, text="", fields={"harmLev": harm_lev, "harmAlt": harm_alt})


def test_duration_and_raw_values_need_nothing_but_the_entry() -> None:
    """The half that always works: no key, no transposition, still a decode."""
    decode = decode_entry(_entry_record(notes=(_note("4"),)), key_raw=None, transposition=None)

    assert decode is not None
    assert decode.duration_edu == 1024
    assert decode.duration_base == "quarter"
    assert decode.dots == 0
    assert decode.duration_name == "quarter"
    assert decode.notes[0].harm_lev == 4
    assert decode.notes[0].spelled is None


def test_an_undotted_quarter_decodes_with_zero_dots() -> None:
    decode = decode_entry(_entry_record(dura="1024"), key_raw=None, transposition=None)

    assert decode is not None
    assert decode.duration_edu == 1024
    assert decode.duration_base == "quarter"
    assert decode.dots == 0
    assert decode.duration_name == "quarter"


def test_a_dotted_quarter_names_itself_dotted_not_bare_quarter() -> None:
    """The regression this whole change exists for: 1536 EDU (1024 + 512) is a
    dotted quarter, and the dot must not be silently dropped from the name."""
    decode = decode_entry(_entry_record(dura="1536"), key_raw=None, transposition=None)

    assert decode is not None
    assert decode.duration_edu == 1536
    assert decode.duration_base == "quarter"
    assert decode.dots == 1
    assert decode.duration_name == "dotted quarter"


def test_a_double_dotted_half_names_itself_double_dotted() -> None:
    """3584 EDU = 2048 (half) + 1024 + 512, i.e. a half with two augmentation dots."""
    decode = decode_entry(_entry_record(dura="3584"), key_raw=None, transposition=None)

    assert decode is not None
    assert decode.duration_edu == 3584
    assert decode.duration_base == "half"
    assert decode.dots == 2
    assert decode.duration_name == "double dotted half"


def test_a_missing_key_produces_no_spelling_and_says_why() -> None:
    """Never a C-major default: an absent key means the pitch is unknown, and
    the report says which input was missing rather than inventing one."""
    decode = decode_entry(
        _entry_record(notes=(_note("4"),)),
        key_raw=None,
        transposition=StaffTransposition(interval=0, adjust=0),
    )

    assert decode is not None
    assert decode.notes[0].spelled is None
    assert decode.notes[0].why_not == "no key in force (placement unresolved)"


def test_a_missing_transposition_produces_no_spelling_and_says_why() -> None:
    decode = decode_entry(_entry_record(notes=(_note("4"),)), key_raw=2, transposition=None)

    assert decode is not None
    assert decode.notes[0].spelled is None
    assert decode.notes[0].why_not == "no staffSpec transposition for this staff"


def test_a_resolved_note_spells_a_pitch() -> None:
    """harmLev 2 in D major (raw key 2) is F#4: two diatonic letters above the
    D tonic is F, and D major's two sharps (F, C) put a sharp on F."""
    decode = decode_entry(
        _entry_record(notes=(_note("2"),)),
        key_raw=2,
        transposition=StaffTransposition(interval=0, adjust=0),
    )

    assert decode is not None
    assert decode.notes[0].spelled == "F#4"
    assert decode.notes[0].why_not is None


def test_an_entry_that_will_not_read_yields_no_decode() -> None:
    """`read_entry` raises `MalformedEntryError` on a record it cannot type.
    That is one entry's problem, not the report's: return None and let the
    caller record it in `unresolved`."""
    assert (
        decode_entry(
            Record(tag="entry", attrs={}, text="", fields={}), key_raw=2, transposition=None
        )
        is None
    )


def test_a_double_sharp_reuses_spelledpitchs_own_convention() -> None:
    """`_spell` must format via `SpelledPitch.name`, not a second accidental
    table: this pins that a double sharp renders "##", matching every other
    module and test in this codebase (not "x", a convention nothing else uses)."""
    decode = decode_entry(
        _entry_record(notes=(_note("0", "2"),)),
        key_raw=0,
        transposition=StaffTransposition(interval=0, adjust=0),
    )

    assert decode is not None
    assert decode.notes[0].spelled == "C##4"
    assert decode.notes[0].why_not is None


def test_the_index_answers_both_questions_for_one_entry() -> None:
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    meas = Record(
        tag="measSpec",
        attrs={"cmper": "3"},
        text="",
        fields={"keySig": Record(tag="keySig", attrs={}, text="", fields={"key": "2"})},
    )
    staff = Record(tag="staffSpec", attrs={"cmper": "1"}, text="", fields={})
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})
    entry = Record(
        tag="entry",
        attrs={"entnum": "9"},
        text="",
        fields={
            "dura": "1024",
            "numNotes": "1",
            "note": (_note("2"),),
        },
    )

    index = build_entry_index(
        _doc(details=(gfhold, artic), others=(frame, meas, staff), entries=(entry,))
    )

    facts = index["9"]
    assert facts.placements[0].staff == 1 and facts.placements[0].measure == 3
    assert facts.named_by[0].tag == "articAssign"
    assert facts.decode is not None and facts.decode.duration_name == "quarter"
    assert facts.decode.notes[0].spelled == "F#4"
    assert facts.unresolved == ()


def test_the_index_never_raises_on_a_broken_document() -> None:
    """The property the whole module exists for. `locate_entries` refuses this
    document; the index must still answer what it can."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )  # frameSpec 12 absent
    # numNotes is required for `read_entry` to accept the record at all (Task 3);
    # "needs only the entry" means the entry record itself, not a shortened one.
    entry = Record(
        tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024", "numNotes": "0"}
    )
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})

    index = build_entry_index(_doc(details=(gfhold, artic), entries=(entry,)))

    assert index["9"].placements == ()
    assert index["9"].named_by[0].tag == "articAssign"  # survives independently
    assert index["9"].decode is not None  # needs only the entry
    assert index["9"].unresolved == ("no frame reaches this entry",)


def test_the_index_never_raises_on_a_malformed_measspec() -> None:
    """`effective_keys` is not tolerant -- unlike `placements_by_entry` and
    `_transpositions` it raises `MalformedScoreError` straight through on a
    `measSpec` it cannot read, and that used to reach `build_entry_index`'s
    caller unguarded. A non-integer `cmper` is the simplest way to trip it.

    Placements and references come from `gfhold`/`articAssign`, not from
    `measSpec`, so they still resolve; only spelling is lost, and the reason
    is filed under entnum 0, the same "belongs to no single entry" bucket
    `placements_by_entry` already uses."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
    )
    bad_meas = Record(
        tag="measSpec",
        attrs={"cmper": "not-a-number"},
        text="",
        fields={"keySig": Record(tag="keySig", attrs={}, text="", fields={"key": "2"})},
    )
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})
    entry = Record(
        tag="entry",
        attrs={"entnum": "9"},
        text="",
        fields={"dura": "1024", "numNotes": "1", "note": (_note("2"),)},
    )

    index = build_entry_index(
        _doc(details=(gfhold, artic), others=(frame, bad_meas), entries=(entry,))
    )

    facts = index["9"]
    assert facts.placements[0].staff == 1 and facts.placements[0].measure == 3
    assert facts.named_by[0].tag == "articAssign"
    assert facts.decode is not None
    assert facts.decode.notes[0].spelled is None
    assert facts.decode.notes[0].why_not == "no key in force (placement unresolved)"
    assert "0" in index
    assert len(index["0"].unresolved) == 1
    assert "no key could be resolved for this document" in index["0"].unresolved[0]
