"""The generated ImHex pattern.

Nothing here can run the pattern -- ImHex is not installable in CI and there is
no headless evaluator for its language -- so these tests pin what *can* be
checked: that the pattern is generated from the catalog, covers all of it, and
never states an offset the parser does not use. Whether it loads is a hand
check, recorded in the plan.
"""

from __future__ import annotations

import re

from hexpat.render import HEXPAT_TYPES, render_pattern

from finale_file_parser.enigma.pool_file import HEADER_SIZE, MAGIC
from finale_file_parser.formats.layouts import LAYOUTS


def test_the_pattern_reads_the_file_the_extractor_writes() -> None:
    pattern = render_pattern()
    assert MAGIC.decode() in pattern, "does not check the magic"
    assert "Header header @ 0x00;" in pattern, "does not place the header at the start"
    assert f"@ {HEADER_SIZE}" in pattern, "does not place the pool array at the header size"


def test_every_field_type_in_the_catalog_maps_to_a_hexpat_type() -> None:
    """A new field type must fail loudly here rather than silently emitting
    nothing into a specification."""
    used = {field.type_ for layout in LAYOUTS for field in layout.fields}
    assert used <= set(HEXPAT_TYPES), f"unmapped field types: {sorted(used - set(HEXPAT_TYPES))}"


def test_the_two_eras_both_appear() -> None:
    """A 2011 pool holds variable-length self-identifying records; a DCL pool
    holds fixed 16-byte rows. One shape cannot describe both."""
    pattern = render_pattern()
    for marker in ("OthersRecord", "DetailsRecord", "DclOthersRow", "DclDetailsRow"):
        assert marker in pattern, f"{marker} missing"


def test_the_pattern_sets_its_endianness_from_the_file() -> None:
    """The order byte is runtime data. 37 of 139 DCL-era corpus documents are
    big-endian, and reading one the wrong way round yields plausible nonsense
    rather than an error."""
    assert "set_endian" in render_pattern()


def test_every_layout_that_can_be_laid_over_bytes_is_emitted() -> None:
    pattern = render_pattern()
    for layout in LAYOUTS:
        if layout.computed:
            continue
        assert f"struct {layout.name}" in pattern, f"{layout.name} missing"


def test_a_computed_layout_is_named_but_never_laid_over_bytes() -> None:
    """`Layout.computed` means a reader works out where these fields sit, per
    record or era, so the offsets in the catalog are the shape a reader starts
    from and not where the bytes are. Laying it over a record would show
    confident, wrong values -- `report/model.py` skips these for the same
    reason. FrameSpec and GfHold carry it."""
    pattern = render_pattern()
    for layout in LAYOUTS:
        if not layout.computed:
            continue
        assert f"struct {layout.name}" not in pattern, (
            f"{layout.name} is computed and must not be laid over bytes"
        )
        assert layout.name in pattern, f"{layout.name} should still be named, with the reason"


def test_every_field_note_travels_with_its_field() -> None:
    """The evidence is the point. A pattern that gives offsets without saying
    what they mean is worth less than the docstring it came from."""
    pattern = render_pattern()
    noted = [
        field for layout in LAYOUTS if not layout.computed for field in layout.fields if field.note
    ]
    assert noted, "the catalog has notes; this test is meaningless without them"
    for field in noted[:20]:
        assert field.note.split(".")[0][:40] in pattern, f"note for {field.name} missing"


def test_a_slot_array_layout_says_it_repeats() -> None:
    """Four layouts have a non-zero `stride`: their payload is an array of
    fixed-size slots, each laid out by the same fields. Emitting one slot and
    stopping would describe a fraction of the record."""
    pattern = render_pattern()
    striped = [layout for layout in LAYOUTS if layout.stride and not layout.computed]
    assert striped, "the catalog has slot arrays; this test is meaningless without them"
    for layout in striped:
        assert f"{layout.name}Slot" in pattern, f"{layout.name} does not emit a slot type"


def test_no_duplicate_struct_names() -> None:
    """ImHex Pattern Language rejects a redefinition, so a pattern that declares
    the same struct name twice fails to *load* -- a class of bug nothing else
    here can catch. Two eras of one record legitimately share a catalog `name`
    (`TEXT_EXPR_DEF` / `TEXT_EXPR_DEF_DCL`), so the generator must disambiguate
    collisions rather than emit them."""
    pattern = render_pattern()
    names = re.findall(r"struct (\w+) \{", pattern)
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"duplicate struct names: {duplicates}"
