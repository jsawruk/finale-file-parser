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
        for index in range(f.offset, f.end):
            assert index not in claimed, (
                f"{layout.record}: {f.name} and {claimed[index]} both claim byte {index}"
            )
            claimed[index] = f.name


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.record)
def test_fields_are_ordered_and_sized(layout: Layout) -> None:
    assert layout.fields, f"{layout.record} has no fields"
    offsets = [f.offset for f in layout.fields]
    assert offsets == sorted(offsets), f"{layout.record}: fields are out of order"
    for f in layout.fields:
        assert f.size > 0, f"{layout.record}: {f.name} has size {f.size}"
        assert f.offset >= 0, f"{layout.record}: {f.name} is at {f.offset}"
        assert f.note, f"{layout.record}: {f.name} says nothing about what it means"


@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.record)
def test_a_slot_holds_its_fields(layout: Layout) -> None:
    """A strided layout describes one slot, so its fields must fit inside one."""
    if not layout.stride:
        return
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
        assert layout_for(layout.pool, str(layout.tag)) is layout
        if layout.dcl:
            assert layout_for(layout.pool, layout.dcl) is layout
