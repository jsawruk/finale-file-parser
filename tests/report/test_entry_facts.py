"""Unit tests for the report's entry facts. No corpus: every document here is
built in process, so CI runs these even though `corpus/` is gitignored."""

from __future__ import annotations

import time

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
from finale_file_parser.enigma.location import _MAX_PLACEMENTS_PER_ENTRY, locate_entries
from finale_file_parser.enigma.music import NoteValue
from finale_file_parser.enigma.pitch import StaffTransposition
from finale_file_parser.report.entry_facts import (
    _DURATION_NAMES,
    _MAX_DOCUMENT_FAILURES,
    Placement,
    Reference,
    _references_by_entnum,
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
        Reference(
            pool="details",
            tag="articAssign",
            key="(entnum 9, inci 0)",
            tree_tag="articAssign",
            tree_key="(entnum 9, inci 0)",
        ),
    )


def _measure(cmper: str, key: str = "0") -> Record:
    """A `measSpec` stating a key.

    Present in the documents below because `locate_entries` refuses a document
    whose gfhold places entries in a measure that states no key -- and these
    documents are the ones the two walks are compared on (see
    `test_the_two_walks_agree_on_a_document_locate_entries_accepts`). It makes
    no difference to `placements_by_entry`, which reads no `measSpec` at all.
    """
    return Record(
        tag="measSpec",
        attrs={"cmper": cmper},
        text="",
        fields={"keySig": Record(tag="keySig", attrs={}, text="", fields={"key": key})},
    )


def _clean_chain_document() -> EnigmaDocument:
    """One gfhold, one frame, one entry -- the shape everything else varies."""
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
    return _doc(details=(gfhold,), others=(frame, _measure("3", "2")), entries=(entry,))


def test_a_clean_chain_places_an_entry() -> None:
    places, unresolved = placements_by_entry(_clean_chain_document())

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


def _part_variant_document() -> EnigmaDocument:
    """A score gfhold and its linked-part twin, both naming one frame."""
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
    entry = Record(
        tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024", "numNotes": "0"}
    )
    return _doc(details=(score, part), others=(frame, _measure("3")), entries=(entry,))


def test_a_part_variant_gfhold_does_not_place_a_second_time() -> None:
    """Score records only, exactly as `locate_entries` does: a linked-part
    gfhold would place the same entry twice and read as a mirror."""
    places, _ = placements_by_entry(_part_variant_document())

    assert len(places[9]) == 1


def _mirror_document() -> EnigmaDocument:
    """Two staves displaying one entry span -- Finale's mirror."""
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
    entry = Record(
        tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024", "numNotes": "0"}
    )
    return _doc(details=(a, b), others=(frame, _measure("3")), entries=(entry,))


def test_a_mirror_places_one_entry_twice() -> None:
    """Two gfholds naming one frame is a Finale mirror, and both placements are
    real -- this is the shape `locate_entries` was changed to allow."""
    places, _ = placements_by_entry(_mirror_document())

    assert sorted(s for p in places[9] if (s := p.staff) is not None) == [4, 14]


def test_a_frame_spec_with_one_entry_bound_says_which_is_missing() -> None:
    """`locate_entries` raises on a `frameSpec` carrying only one of
    `startEntry`/`endEntry`. Skipping it silently reported the wrong absence:
    the entries came back "no frame reaches this entry" and nothing anywhere
    said the frame naming them was half-written."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec", attrs={"cmper": "12"}, text="", fields={"startEntry": "9"}
    )  # no endEntry
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})

    _, unresolved = placements_by_entry(_doc(details=(gfhold,), others=(frame,), entries=(entry,)))

    assert any("endEntry" in message for message in unresolved[0]), unresolved
    assert any("startEntry" in message for message in unresolved[0])


def test_a_frame_spec_with_neither_entry_bound_is_an_empty_layer_not_a_failure() -> None:
    """The case `locate_entries` also passes over: an incidence that exists
    with other fields and never got an entry chain. A frame cmper can carry a
    second incidence that does, so this is ordinary rather than broken, and
    calling it a failure would fill the report with noise."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(tag="frameSpec", attrs={"cmper": "12"}, text="", fields={"startTime": "0"})
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})

    _, unresolved = placements_by_entry(_doc(details=(gfhold,), others=(frame,), entries=(entry,)))

    assert unresolved.get(0, []) == []


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


_EXCESS_FAILURES = 50
"""How far past the cap the document-cap test goes.

Small and constant on purpose: the failures this drives are one Python string
each, and the test's own allocation must be bounded by a number written here
rather than by anything the walk decides -- see the module docstring's note on
a prior test that allocated 28.8 GB.
"""


def test_document_level_failures_are_capped_with_a_counted_tail() -> None:
    """How many broken frame links a document has is a number read out of the
    file: `gfhold` count times four slots times `frameSpec` incidences, none of
    them bounded relative to the others. Recording a message for each -- which
    is exactly what a tolerant walk does, and what `locate_entries` never does
    because it raises at the first one -- lets a small crafted document decide
    how much text this holds in memory and embeds in the report.

    The first messages are kept rather than the last: the first failure in a
    document is the one a reader chasing a broken score needs.
    """
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    gfholds = tuple(
        Record(
            tag="gfhold",
            attrs={"cmper1": str(staff), "cmper2": "3"},
            text="",
            fields={"frame1": "12"},  # frameSpec 12 is absent, so each one fails
        )
        for staff in range(1, _MAX_DOCUMENT_FAILURES + _EXCESS_FAILURES + 1)
    )

    _, unresolved = placements_by_entry(_doc(details=gfholds, entries=(entry,)))

    messages = unresolved[0]
    assert len(messages) == _MAX_DOCUMENT_FAILURES + 1, "the list is capped, tail included"
    assert "(cmper1 1, cmper2 3)" in messages[0], "the first failure is kept, not the last"
    assert all("which is absent" in message for message in messages[:-1])
    assert str(_EXCESS_FAILURES) in messages[-1], "the tail counts what it dropped"
    assert "further" in messages[-1]


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


def _indexed_document() -> EnigmaDocument:
    """One placed, spelled, articulated entry: the whole feature in one file."""
    gfhold = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    frame = Record(
        tag="frameSpec",
        attrs={"cmper": "12"},
        text="",
        fields={"startEntry": "9", "endEntry": "9"},
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
    return _doc(
        details=(gfhold, artic), others=(frame, _measure("3", "2"), staff), entries=(entry,)
    )


def test_the_index_answers_both_questions_for_one_entry() -> None:
    index = build_entry_index(_indexed_document())

    facts = index["9"]
    assert facts.placements[0].staff == 1 and facts.placements[0].measure == 3
    assert facts.named_by[0].tag == "articAssign"
    assert facts.decode is not None and facts.decode.duration_name == "quarter"
    assert facts.decode.notes[0].spelled == "F#4"
    assert facts.unresolved == ()


def test_a_mirrored_entry_spells_from_the_first_placement() -> None:
    """The rule `build_entry_index`'s docstring documents: a mirrored entry
    carries two placements, and spelling always uses the *first* one's key and
    transposition -- even though a real mirror can transpose differently on
    each staff, which is exactly what would make the two answers disagree.

    Staff 1 is concert pitch; staff 2 is a B-flat transposition (interval=1,
    adjust=2, the same figures `test_spell_note_bb_staff_written_and_concert`
    pins). The same stored note -- harmLev 0 in C major -- spells "C4" on
    staff 1 and "D4" on staff 2, so this only passes if the index picked one
    placement's transposition and held to it.
    """
    concert = Record(
        tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"}
    )
    transposing = Record(
        tag="gfhold", attrs={"cmper1": "2", "cmper2": "3"}, text="", fields={"frame1": "12"}
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
        fields={"keySig": Record(tag="keySig", attrs={}, text="", fields={"key": "0"})},
    )
    staff_concert = Record(tag="staffSpec", attrs={"cmper": "1"}, text="", fields={})
    keysig = Record(tag="keysig", attrs={}, text="", fields={"interval": "1", "adjust": "2"})
    transposition = Record(tag="transposition", attrs={}, text="", fields={"keysig": keysig})
    staff_transposing = Record(
        tag="staffSpec",
        attrs={"cmper": "2"},
        text="",
        fields={"transposition": transposition},
    )
    entry = Record(
        tag="entry",
        attrs={"entnum": "9"},
        text="",
        fields={"dura": "1024", "numNotes": "1", "note": (_note("0"),)},
    )

    index = build_entry_index(
        _doc(
            details=(concert, transposing),
            others=(frame, meas, staff_concert, staff_transposing),
            entries=(entry,),
        )
    )

    facts = index["9"]
    assert len(facts.placements) == 2
    assert sorted(s for p in facts.placements if (s := p.staff) is not None) == [1, 2]
    assert facts.placements[0].staff == 1
    assert facts.decode is not None
    assert facts.decode.notes[0].spelled == "C4", "must spell from the first placement (staff 1)"


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


def test_a_reference_carries_the_tree_row_it_should_select() -> None:
    """A reference is only useful if the reader can get from it to the record.

    On a `.musx` the record the reference names *is* the row the tree rendered,
    so the two targeting fields repeat the identity. On a `.mus` they are
    retargeted at the numeric row (see `report.model`), and either being None
    means "no row to point at" rather than "point at this one anyway".
    """
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})

    (reference,) = references_to(_doc(details=(artic,)), 9)

    assert reference.tree_tag == reference.tag
    assert reference.tree_key == reference.key


def test_every_note_value_is_spelled_the_way_a_musician_writes_it() -> None:
    """Covers the enum rather than a sample: a value added later with no name
    would otherwise render as its own member name -- "one twenty eighth" -- and
    nothing would say so.
    """
    for value in NoteValue:
        name = _DURATION_NAMES.get(value)
        assert name is not None, f"{value.name} has no readable name"
        assert "_" not in name
        assert name == name.lower()


def test_the_short_values_are_named_by_number_not_by_syllable() -> None:
    """The regression: `NoteValue.name.lower().replace("_", " ")` rendered
    "thirty second" and "one twenty eighth", neither of which is notation."""
    assert _DURATION_NAMES[NoteValue.SIXTEENTH] == "16th"
    assert _DURATION_NAMES[NoteValue.THIRTY_SECOND] == "thirty-second"
    assert _DURATION_NAMES[NoteValue.SIXTY_FOURTH] == "64th"
    assert _DURATION_NAMES[NoteValue.ONE_TWENTY_EIGHTH] == "128th"


def test_a_thirty_second_decodes_under_its_notation_name() -> None:
    decode = decode_entry(_entry_record(dura="128"), key_raw=None, transposition=None)

    assert decode is not None
    assert decode.duration_base == "thirty-second"
    assert decode.duration_name == "thirty-second"


def test_a_dotted_sixteenth_reads_as_one_phrase() -> None:
    """384 EDU = 256 + 128, a dotted 16th -- the composed phrase, not "dotted
    sixteenth" and not "dotted 16"."""
    decode = decode_entry(_entry_record(dura="384"), key_raw=None, transposition=None)

    assert decode is not None
    assert decode.duration_name == "dotted 16th"


def test_grouped_references_agree_with_references_to_for_every_entnum() -> None:
    """`_references_by_entnum` is a grouped rewrite of `references_to`'s answer,
    not a new rule -- the two must agree for every entnum, including one that
    nothing points at, which must come back as an empty tuple rather than a
    missing key (a reader asking "what points at entry 3" gets a real, empty
    answer, not a `KeyError`)."""
    refs = (
        Record(tag="articAssign", attrs={"entnum": "1", "inci": "0"}, text="", fields={}),
        Record(tag="articAssign", attrs={"entnum": "1", "inci": "1"}, text="", fields={}),
        Record(tag="expression", attrs={"entnum": "2", "inci": "0"}, text="", fields={}),
    )
    doc = _doc(details=refs)
    grouped = _references_by_entnum(doc)

    for entnum in (1, 2, 3):  # 3 is an entry nothing points at
        assert grouped.get(str(entnum), ()) == references_to(doc, entnum)
    assert grouped.get("3", ()) == ()
    assert len(grouped["1"]) == 2


_STRESS_ENTRY_COUNT = 8_000
"""Entries in the quadratic-cost stress test. Kept in the thousands, not the
million-record pool cap, so the test's own allocation stays small and bounded
-- see the module docstring's note on a prior test that allocated 28.8 GB.
Measured directly against this repo's `references_to`: at this size the old
per-entry rescan takes ~3.4s; the grouped lookup takes ~0.05s. A smaller count
(e.g. 3,000, giving 9,000,000 comparisons) still passes even unfixed --
CPython's string-compare loop is fast enough that the quadratic cost only
becomes clearly, reliably slow once `entries x details` reaches this size."""

_STRESS_DETAIL_COUNT = 8_000
"""Details records in the quadratic-cost stress test, same rationale as
`_STRESS_ENTRY_COUNT`. `entries x details` here is 64,000,000."""


def test_build_entry_index_is_linear_not_quadratic_in_entries_and_details() -> None:
    """Before the grouped lookup, `build_entry_index` called `references_to`
    (a full scan of `doc.details.records`) once per entry, costing
    `entries x details`. With `_STRESS_ENTRY_COUNT` entries and
    `_STRESS_DETAIL_COUNT` details that is 64,000,000 string comparisons --
    measured at ~3.4s against the unfixed code, ~0.05s against the grouped
    lookup. This asserts the index still comes back promptly (well under
    either number) and with the right references, not just that it
    eventually returns."""
    entries = tuple(
        Record(
            tag="entry",
            attrs={"entnum": str(n)},
            text="",
            fields={"dura": "1024", "numNotes": "0"},
        )
        for n in range(1, _STRESS_ENTRY_COUNT + 1)
    )
    # Every detail names an entry that exists, spread across the whole range,
    # so the grouped lookup and the naive scan would find the same references.
    details = tuple(
        Record(
            tag="articAssign",
            attrs={"entnum": str((n % _STRESS_ENTRY_COUNT) + 1), "inci": "0"},
            text="",
            fields={},
        )
        for n in range(_STRESS_DETAIL_COUNT)
    )

    started = time.perf_counter()
    index = build_entry_index(_doc(details=details, entries=entries))
    elapsed = time.perf_counter() - started

    # 2.0s separates ~0.05s (grouped) from ~3.4s (per-entry rescan): 40x
    # headroom over the passing measurement and still under the failing one.
    # A tighter bound would say nothing more and would flake on a loaded
    # machine, which is a poor trade in a suite that runs on every commit.
    assert elapsed < 2.0, f"build_entry_index took {elapsed:.2f}s -- looks quadratic again"
    assert len(index) == _STRESS_ENTRY_COUNT
    assert len(index["1"].named_by) >= 1
    assert index["1"].named_by[0].tag == "articAssign"


def _layered_document() -> EnigmaDocument:
    """A document with something for the walk to do: three gfholds across two
    staves and two measures, one of them holding two layers, and a frame whose
    entry range is a real `next` chain rather than a single entry.

    The four documents above each isolate one rule. This one runs them
    together, which is where a drift between the two walks would actually show:
    the frame-slot enumeration (`frame2` is layer 2), the chain walk, and the
    order placements come back in.
    """
    entries = tuple(
        Record(
            tag="entry",
            attrs={"entnum": str(n), "next": str(nxt)},
            text="",
            fields={"dura": "1024", "numNotes": "0"},
        )
        for n, nxt in ((1, 2), (2, 0), (3, 0), (4, 0), (5, 6), (6, 0))
    )
    frames = tuple(
        Record(
            tag="frameSpec",
            attrs={"cmper": str(cmper)},
            text="",
            fields={"startEntry": str(start), "endEntry": str(end)},
        )
        for cmper, start, end in ((10, 1, 2), (20, 3, 3), (30, 4, 4), (40, 5, 6))
    )
    gfholds = (
        Record(
            tag="gfhold",
            attrs={"cmper1": "1", "cmper2": "1"},
            text="",
            fields={"frame1": "10", "frame2": "20"},
        ),
        Record(
            tag="gfhold", attrs={"cmper1": "2", "cmper2": "1"}, text="", fields={"frame1": "30"}
        ),
        Record(
            tag="gfhold", attrs={"cmper1": "1", "cmper2": "2"}, text="", fields={"frame1": "40"}
        ),
    )
    return _doc(
        details=gfholds,
        others=(*frames, _measure("1", "2"), _measure("2")),
        entries=entries,
    )


def test_the_two_walks_agree_on_a_document_locate_entries_accepts() -> None:
    """The containment for the duplication, in CI.

    `placements_by_entry` deliberately re-walks the join `locate_entries`
    walks, because `locate_entries` raises on exactly the documents a
    diagnostic report exists for. The only thing that stopped the two drifting
    was `test_entry_facts_corpus_sweep.py`, and `corpus/` is gitignored and
    absent in CI -- so the branch's central bet was undefended there. These
    documents are built in process, so this runs everywhere, in milliseconds.

    Placements are compared **in order**, not as a set: the order is what picks
    the key and transposition an entry is spelled with, and the corpus sweep
    sorts before comparing.
    """
    for name, build in (
        ("clean chain", _clean_chain_document),
        ("part variant", _part_variant_document),
        ("mirror", _mirror_document),
        ("indexed", _indexed_document),
        ("layered", _layered_document),
    ):
        document = build()
        # Not in a `try`: a document this refuses would silently compare
        # nothing, which is how a containment test stops containing anything.
        located = locate_entries(document)
        placements, _ = placements_by_entry(document)

        theirs = {
            entnum: [(p.staff, p.measure, p.layer) for p in places]
            for entnum, places in located.items()
        }
        ours = {
            entnum: [(p.staff, p.measure, p.layer) for p in places]
            for entnum, places in placements.items()
        }
        assert ours == theirs, f"the two walks disagree on the {name} document"
