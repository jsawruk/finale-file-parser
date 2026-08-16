"""The layouts must hold the properties their consumers assume.

Both consumers -- the specification generator and the inspector -- tint a
record's bytes by asking which field covers each byte. That answer is only
well defined if fields do not overlap, and it is only useful if the colour a
field gets is stable, which means the order of `fields` is part of the layout
rather than incidental.
"""

from __future__ import annotations

import pytest

from finale_file_parser.formats.layouts import LAYOUTS, Layout, layout_for


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.record)
def test_fields_do_not_overlap(layout: Layout) -> None:
    """Two fields claiming one byte would make `field_at` silently pick one."""
    claimed: dict[int, str] = {}
    for f in layout.fields:
        if f.is_tail:
            # A tail has no end to count to. It claims everything from its
            # offset on, so what has to be free is that offset onwards -- and
            # since a tail is last and the fields are ordered, its own offset
            # being unclaimed is the whole of it.
            assert f.offset not in claimed, (
                f"{layout.record}: the tail {f.name} starts inside {claimed[f.offset]}"
            )
            continue
        for index in range(f.offset, f.end):
            assert index not in claimed, (
                f"{layout.record}: {f.name} and {claimed[index]} both claim byte {index}"
            )
            claimed[index] = f.name


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.record)
def test_no_field_advertises_an_unbounded_span(layout: Layout) -> None:
    """`end` must stay a number a caller can safely count up to.

    This is the guard on a real incident, not a hypothetical. `end` returned
    `sys.maxsize` for a variable-length tail, `test_fields_do_not_overlap` did
    `for index in range(f.offset, f.end)`, and the run reached 28.8 GB and took
    the machine down with it. Both halves are fixed -- the test skips a tail and
    `end` is finite -- and this pins the half that protects every other caller,
    including the two renderers that compute `f.end - 1` for a span label.

    A record payload is bytes read off a file, so no honest field ends anywhere
    near a megabyte.
    """
    for f in layout.fields:
        assert f.end == f.offset + f.size, (
            f"{layout.record}: {f.name} reports an end of {f.end}, not offset + size"
        )
        assert f.end < 1 << 20, f"{layout.record}: {f.name} claims to end at byte {f.end}"


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.record)
def test_fields_are_ordered_and_sized(layout: Layout) -> None:
    assert layout.fields, f"{layout.record} has no fields"
    offsets = [f.offset for f in layout.fields]
    assert offsets == sorted(offsets), f"{layout.record}: fields are out of order"
    for index, f in enumerate(layout.fields):
        last = index == len(layout.fields) - 1
        if f.size == 0:
            # A variable-length tail: a NUL-terminated string running to the end
            # of a payload whose length varies. Only the last field may do this,
            # or the fields after it would sit inside it.
            assert last, f"{layout.record}: {f.name} has size 0 but is not the last field"
            assert "runs to the end" in f.note, (
                f"{layout.record}: {f.name} is a tail and its note must say so"
            )
        else:
            assert f.size > 0, f"{layout.record}: {f.name} has size {f.size}"
        assert f.offset >= 0, f"{layout.record}: {f.name} is at {f.offset}"
        assert f.note, f"{layout.record}: {f.name} says nothing about what it means"


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.record)
def test_a_slot_holds_its_fields(layout: Layout) -> None:
    """A strided layout describes one slot, so its fields must fit inside one."""
    if not layout.stride:
        return
    assert all(f.size for f in layout.fields), (
        f"{layout.record}: a strided slot cannot hold a variable-length tail"
    )
    end = max(f.end for f in layout.fields)
    assert end <= layout.stride, (
        f"{layout.record}: fields run to {end}, past the {layout.stride}-byte slot"
    )


def test_field_at_finds_the_field_and_its_position() -> None:
    from finale_file_parser.formats.layouts import MEAS_SPEC

    assert MEAS_SPEC.field_at(0) == (0, MEAS_SPEC.fields[0])
    assert MEAS_SPEC.field_at(5) == (2, MEAS_SPEC.fields[2])
    # +8 is between divbeat and flags: undecoded, and not to be claimed.
    assert MEAS_SPEC.field_at(8) is None


def test_a_record_is_found_by_either_spelling_of_its_tag() -> None:
    from finale_file_parser.formats.layouts import MEAS_SPEC

    assert layout_for("others", "176") is MEAS_SPEC
    assert layout_for("others", "MS") is MEAS_SPEC


def test_a_tag_is_only_found_in_its_own_pool() -> None:
    """gfhold is a details record; the same number in `others` is not gfhold."""
    assert layout_for("details", "1044") is not None
    assert layout_for("others", "1044") is None


def test_an_undecoded_tag_has_no_layout() -> None:
    assert layout_for("others", "124") is None


def test_every_layout_is_reachable_by_its_tag() -> None:
    for layout in LAYOUTS:
        if layout.tag:
            assert layout_for(layout.pool, str(layout.tag)) is layout
        else:
            # Tag 0 marks a DCL-only layout. It must be reachable by its DCL
            # spelling and must not answer to "0", which is no record's number.
            assert layout.dcl, f"{layout.record}: tag 0 with no DCL spelling is unreachable"
            assert layout_for(layout.pool, "0") is None
        if layout.dcl:
            assert layout_for(layout.pool, layout.dcl) is layout


def test_the_expression_records_are_registered() -> None:
    """The bug this test exists for: both layouts were written and never added to
    `LAYOUTS`, so `layout_for` could not find them and the report went on saying
    no layout was known. A layout outside the registry is dead code that none of
    the invariants above ever check.
    """
    assert layout_for("others", "241") is not None, "the 2011 textExprDef"
    assert layout_for("others", "177") is not None, "the 2011 measExprAssign"
    assert layout_for("others", "DT") is not None, "the DCL text expression"


def test_dt_claims_only_what_the_dcl_era_confirms() -> None:
    """Two eras, two layouts.

    The 2011 record's alignment enums are confirmed by exact equality against the
    paired corpus; in a DCL payload no offset separates the "Below Staff"
    descriptions, so they are not evidenced there. Naming them anyway is what a
    single shared layout would do.
    """
    dcl = layout_for("others", "DT")
    numeric = layout_for("others", "241")
    assert dcl is not None and numeric is not None
    assert dcl is not numeric
    names = {f.name for f in dcl.fields}
    assert names == {"counter", "value", "descStr"}
    assert "horzMeasExprAlign" not in names
    assert "vertMeasExprAlign" not in names
    # The shared ground: both eras put the playback value at +4.
    assert next(f.offset for f in dcl.fields if f.name == "value") == 4
    assert next(f.offset for f in numeric.fields if f.name == "value") == 4


def test_no_layout_is_claimed_for_the_dcl_assignment() -> None:
    """`^DY` is undecoded. A layout for it would assert a 24-byte slot in a record
    nobody has looked at."""
    assert layout_for("others", "DY") is None


def test_a_variable_length_tail_covers_the_rest_of_the_record() -> None:
    """`field_at` has to place a byte inside the description however long the
    payload is -- 48, 60 and 72 all occur."""
    layout = layout_for("others", "241")
    assert layout is not None
    for index in (36, 50, 71, 200):
        found = layout.field_at(index)
        assert found is not None, f"byte {index} is not covered"
        assert found[1].name == "descStr"
    assert layout.field_at(34) is None, "the gap before the tail is not claimed"
