"""Unit tests for staff groups.

Written as small staff layouts rather than as documents. The cases that matter
are the ones the corpus is thin on or that only one kind of document exercises:
a staff list that is not in numeric order, a group that runs backwards, and the
part-variant records that quietly double a group if they are not filtered out.
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
from finale_file_parser.enigma.groups import staff_groups, staff_order
from finale_file_parser.enigma.to_ir import _groups

EMPTY: tuple[Record, ...] = ()


def group(
    start: int,
    end: int,
    *,
    bracket: int | None = None,
    barline: bool = False,
    full_id: int | None = None,
    part: str | None = None,
    group_id: int = 1,
) -> Record:
    fields: dict[str, str | Record] = {"startInst": str(start), "endInst": str(end)}
    if bracket is not None:
        fields["bracket"] = Record(tag="bracket", attrs={}, text="", fields={"id": str(bracket)})
    if barline:
        fields["groupBarlineStyle"] = "group"
    if full_id is not None:
        fields["fullID"] = str(full_id)
    attrs = {"cmper1": "0", "cmper2": str(group_id)}
    if part is not None:
        attrs["part"] = part
    return Record(tag="staffGroup", attrs=attrs, text="", fields=fields)


def inst_used(*staves: int, part: str | None = None) -> tuple[Record, ...]:
    out = []
    for inci, staff in enumerate(staves):
        attrs = {"cmper": "0", "inci": str(inci)}
        if part is not None:
            attrs["part"] = part
        out.append(Record(tag="instUsed", attrs=attrs, text="", fields={"inst": str(staff)}))
    return tuple(out)


def staff(number: int) -> Record:
    return Record(tag="staffSpec", attrs={"cmper": str(number)}, text="", fields={})


def document(others: tuple[Record, ...] = (), details: tuple[Record, ...] = ()) -> EnigmaDocument:
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=others),
        details=DetailsPool(records=details),
        entries=EntriesPool(records=EMPTY),
        texts=TextsPool(records=EMPTY),
    )


def test_the_staff_order_follows_the_instrument_list() -> None:
    """Not numeric order: 10 corpus documents lay staves out in an order their
    numbers do not follow, and sorting would silently regroup them."""
    assert staff_order(document(others=inst_used(1, 2, 14, 3))) == (1, 2, 14, 3)


def test_part_variants_do_not_duplicate_the_staff_order() -> None:
    """`all_with` returns the score record *and* every linked part's, which
    lists each staff once per part and corrupts the order."""
    others = inst_used(1, 2, 3) + inst_used(1, 2, 3, part="1")
    assert staff_order(document(others=others)) == (1, 2, 3)


def test_the_staff_order_falls_back_to_numeric_when_there_is_no_list() -> None:
    """The `.mus` path: its instrument list is unidentified, so staves come out
    in numeric order."""
    assert staff_order(document(others=(staff(3), staff(1), staff(2)))) == (1, 2, 3)


def test_a_group_covers_the_run_in_list_order_not_the_numeric_range() -> None:
    """Staves 2..3 of the list [1, 2, 14, 3] are 2 and 14, not 2 and 3."""
    doc = document(others=inst_used(1, 2, 14, 3), details=(group(2, 14),))
    assert staff_groups(doc)[0].staves == (2, 14)


def test_a_known_bracket_becomes_its_musicxml_symbol() -> None:
    doc = document(others=inst_used(1, 2), details=(group(1, 2, bracket=3),))
    assert staff_groups(doc)[0].symbol == "brace"


def test_an_unmapped_bracket_yields_no_symbol_but_keeps_the_group() -> None:
    """Bracket 8 has no evidence behind it. The group still exists -- dropping
    it would lose the grouping as well as the shape."""
    doc = document(others=inst_used(1, 2), details=(group(1, 2, bracket=8),))
    groups = staff_groups(doc)
    assert len(groups) == 1
    assert groups[0].symbol is None


def test_a_group_running_backwards_is_dropped() -> None:
    """Three corpus groups end before they start; bracing that span would join
    staves the score does not group."""
    doc = document(others=inst_used(1, 2, 3), details=(group(3, 1),))
    assert staff_groups(doc) == ()


def test_a_group_naming_a_staff_outside_the_list_is_dropped() -> None:
    doc = document(others=inst_used(1, 2), details=(group(1, 9),))
    assert staff_groups(doc) == ()


def test_a_part_variant_group_is_ignored() -> None:
    """A linked part can restate a group; counting both braces it twice."""
    doc = document(
        others=inst_used(1, 2),
        details=(group(1, 2, bracket=3), group(1, 2, bracket=3, part="1")),
    )
    assert len(staff_groups(doc)) == 1


def test_the_group_barline_is_read() -> None:
    doc = document(others=inst_used(1, 2), details=(group(1, 2, barline=True),))
    assert staff_groups(doc)[0].barline
    plain = document(others=inst_used(1, 2), details=(group(1, 2),))
    assert not staff_groups(plain)[0].barline


def test_groups_come_out_outermost_first() -> None:
    """An exporter opens them in this order, and a wider group must open before
    the one it contains or the brackets interleave."""
    doc = document(
        others=inst_used(1, 2, 3, 4),
        details=(group(1, 2, group_id=1), group(1, 4, group_id=2)),
    )
    assert [g.staves for g in staff_groups(doc)] == [(1, 2, 3, 4), (1, 2)]


def test_a_group_name_resolves_through_the_text_block_chain() -> None:
    others = (
        *inst_used(1, 2),
        Record(tag="textBlock", attrs={"cmper": "99"}, text="", fields={"textID": "7"}),
    )
    texts = (Record(tag="blockText", attrs={"number": "7"}, text="Winds", fields={}),)
    doc = document(others=others, details=(group(1, 2, full_id=99),))
    doc.texts = TextsPool(records=texts)
    assert staff_groups(doc)[0].name == "Winds"


def test_an_unresolvable_name_is_empty_rather_than_a_number() -> None:
    """The `.mus` case: it stores the text-block id but carries no text blocks,
    so the chain has nowhere to land. Printing the raw id would put "99" where
    a group name belongs."""
    doc = document(others=inst_used(1, 2), details=(group(1, 2, full_id=99),))
    assert staff_groups(doc)[0].name == ""


def test_a_group_whose_parts_are_not_contiguous_is_dropped() -> None:
    """`build_score` orders parts by staff number, so a group defined over a
    staff list in some other order can land on a run of parts that is not
    contiguous. Emitting it would brace parts the score does not group -- worse
    than no bracket. 8 of 209 corpus groups take this path.
    """
    doc = document(others=inst_used(1, 14, 2), details=(group(1, 14),))
    assert [g.staves for g in staff_groups(doc)] == [(1, 14)]
    assert _groups(doc, ["P1", "P2", "P14"]) == ()


def test_a_contiguous_group_survives_the_same_check() -> None:
    doc = document(others=inst_used(1, 2, 14), details=(group(1, 2),))
    assert [g.part_ids for g in _groups(doc, ["P1", "P2", "P14"])] == [("P1", "P2")]
