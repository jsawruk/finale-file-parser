"""The generated ImHex pattern.

Nothing here can run the pattern -- ImHex is not installable in CI and there is
no headless evaluator for its language -- so these tests pin what *can* be
checked: that the pattern is generated from the catalog, covers all of it, and
never states an offset the parser does not use. Whether it loads is a hand
check, recorded in the plan.
"""

from __future__ import annotations

import re

import pytest
from hexpat.render import HEXPAT_TYPES, _one_struct, _struct_names, render_pattern

from finale_file_parser.enigma.pool_file import HEADER_SIZE, MAGIC
from finale_file_parser.formats.layouts import LAYOUTS, Field, Layout

_HEXPAT_WIDTH = {"u8": 1, "u16": 2, "u32": 4, "s16": 2}
"""Bytes each fixed-size hexpat type occupies -- the arithmetic the offset
reconstruction test below runs to check the generator against the catalog
without needing ImHex."""

_PADDING_LINE = re.compile(r"^\s*padding\[(\d+)\];\s*$")
_FIELD_LINE = re.compile(r"^\s*(u8|u16|u32|s16|char) (\w+)(\[\d*\])?;(.*)$")


def _struct_body(pattern: str, name: str) -> list[str]:
    """The lines between `struct {name} {` and its closing `};`.

    Matched by the exact opening brace, not just the name, so `TextExprDef`
    cannot accidentally grab the body of `TextExprDefDcl`.
    """
    marker = f"struct {name} {{"
    start = pattern.index(marker) + len(marker)
    end = pattern.index("\n};", start)
    return pattern[start:end].splitlines()


def test_the_pattern_reads_the_file_the_extractor_writes() -> None:
    pattern = render_pattern()
    assert MAGIC.decode() in pattern, "does not check the magic"
    assert "Header header @ 0x00;" in pattern, "does not place the header at the start"
    assert f"@ {HEADER_SIZE}" in pattern, "does not place the pool array at the header size"


_PLACEMENTS = {
    ("zlib_2011", "others"): "OthersRecord",
    ("zlib_2011", "details"): "DetailsRecord",
    ("dcl_2005", "others"): "DclOthersRow",
    ("dcl_2005", "details"): "DclDetailsRow",
}
"""Which record shape each era and pool kind puts over its payload."""


def test_each_era_and_kind_places_its_own_record_shape() -> None:
    """A declared struct that is never instantiated is never evaluated: ImHex
    shows the pool as one opaque blob, and the hand-check that is this pattern's
    only execution proves nothing about the shape. Each arm has to *place* its
    struct, not merely declare it above."""
    lines = render_pattern().splitlines()
    for (era, kind), struct in _PLACEMENTS.items():
        head = f"header.era == Era::{era} && kind == PoolKind::{kind}"
        index = next((i for i, line in enumerate(lines) if head in line), None)
        assert index is not None, f"nothing dispatches on the {era} {kind} pool"
        placed = lines[index + 1].strip()
        assert placed.startswith(f"{struct} ") and "[while(" in placed, (
            f"the {era} {kind} pool does not place {struct}: {placed!r}"
        )


def test_a_pool_with_no_catalogued_record_shape_stays_raw_bytes() -> None:
    """`entries` and `text` have no catalogued record shape, so the dispatch's
    last arm hands back bytes. Inventing one there is the failure this pattern
    exists to avoid, and it would be invisible in a hex dump."""
    pattern = render_pattern()
    assert re.search(r"\} else \{\n\s*u8 payload\[length - \d+\];", pattern), (
        "the dispatch has no raw-bytes arm"
    )
    for kind in ("entries", "text"):
        assert f"PoolKind::{kind}" not in pattern, f"{kind} is given a record shape it has none of"


def test_a_2011_record_reads_its_extra_block_rather_than_a_fixed_trailer() -> None:
    """The fixed four-byte trailer is a retracted reading (docs/ARCHITECTURE.md):
    those bytes are the *length* of an extra block, and `mus_others._walk` reads
    that many bytes after them. A pattern that stops at four desynchronizes at
    the first record carrying one."""
    pattern = render_pattern()
    for name in ("OthersRecord", "DetailsRecord"):
        body = "\n".join(_struct_body(pattern, name))
        assert "trailer" not in body, f"{name} brings back the retracted fixed trailer"
        assert "u32 extra_length;" in body, f"{name} does not read the extra block's length"
        assert "u8 extra[extra_length];" in body, f"{name} does not read the extra block"


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
    """Matches the full declaration, including the opening brace: `struct
    TextExprDef` (no brace) is also a substring of `struct TextExprDefDcl {`,
    so a looser match would call the 2011 record present when only the DCL one
    was ever emitted."""
    pattern = render_pattern()
    names = _struct_names()
    for layout in LAYOUTS:
        if layout.computed:
            continue
        assert f"struct {names[layout]} {{" in pattern, f"{layout.name} missing"


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
    what they mean is worth less than the docstring it came from -- and the
    note has to sit on the *same line* as the field it explains, not merely
    appear somewhere in the document, or a note for one field could satisfy the
    check for an unrelated one. Covers every noted field, not a sample: a note
    that only the 21st-and-later fields dropped would be invisible to a slice."""
    pattern = render_pattern()
    names = _struct_names()
    noted = [
        (layout, field)
        for layout in LAYOUTS
        if not layout.computed
        for field in layout.fields
        if field.note
    ]
    assert noted, "the catalog has notes; this test is meaningless without them"
    for layout, field in noted:
        body = _struct_body(pattern, names[layout])
        line = next(
            (
                candidate
                for candidate in body
                if (m := _FIELD_LINE.match(candidate)) and m.group(2) == field.name
            ),
            None,
        )
        assert line is not None, f"{field.name} not found in struct {names[layout]}"
        assert field.note.split(".")[0][:40] in line, f"note for {field.name} not beside its field"


def test_a_slot_array_layout_says_it_repeats() -> None:
    """Four layouts carry a non-zero `stride`, and the three that are not
    `computed` are checked here (`FrameSpec` is excluded on the next line):
    their payload is an array of fixed-size slots, each laid out by the same
    fields, and emitting one slot and stopping would describe a fraction of the
    record. Checked by each layout's *own* comment line, naming its own struct
    -- a bare "array of 24-byte" search passes on another layout's comment,
    since `MeasExprAssign` and `InstUsed` share a stride of 24."""
    pattern = render_pattern()
    names = _struct_names()
    striped = [layout for layout in LAYOUTS if layout.stride and not layout.computed]
    assert striped, "the catalog has slot arrays; this test is meaningless without them"
    for layout in striped:
        expected = (
            f"// {layout.name}: the payload is an array of {layout.stride}-byte "
            f"{names[layout]} slots"
        )
        assert expected in pattern, f"{layout.name} does not say its own payload repeats"


def test_every_emitted_field_lands_at_its_catalog_offset() -> None:
    """The one thing that matters most: a struct is read by laying it directly
    over real bytes, so a field's position in the rendered text has to equal
    `field.offset`, or every field after the first gap misreads. `StaffSpec`'s
    only field sits at `+20`; packed, it lands at `+0`. Reconstructs each
    struct's offsets from its declared fields and `padding[N]` lines -- pure
    arithmetic, so it needs no ImHex -- and checks every non-computed layout,
    plus that a slot struct's total size equals its `stride`."""
    pattern = render_pattern()
    names = _struct_names()
    for layout in LAYOUTS:
        if layout.computed:
            continue
        name = names[layout]
        cursor = 0
        seen = 0
        for line in _struct_body(pattern, name):
            if not line.strip():
                continue
            pad = _PADDING_LINE.match(line)
            if pad:
                cursor += int(pad.group(1))
                continue
            fld = _FIELD_LINE.match(line)
            assert fld, f"unparsed line in struct {name}: {line!r}"
            hexpat_type, field_name, brackets, _rest = fld.groups()
            catalog_field = layout.fields[seen]
            assert field_name == catalog_field.name, (
                f"{name}: expected {catalog_field.name} next, found {field_name}"
            )
            assert cursor == catalog_field.offset, (
                f"{name}.{field_name} rendered at +{cursor}, catalog says +{catalog_field.offset}"
            )
            seen += 1
            if brackets == "[]":  # a NUL-terminated tail: no fixed width, must be last
                break
            cursor += _HEXPAT_WIDTH[hexpat_type]
        assert seen == len(layout.fields), (
            f"{name}: rendered {seen} of {len(layout.fields)} catalog fields"
        )
        if layout.stride:
            assert cursor == layout.stride, (
                f"{name}: rendered body totals {cursor} bytes, stride says {layout.stride}"
            )


def test_a_slot_layout_that_grew_a_tail_refuses_to_render() -> None:
    """A tail has no fixed width, so a struct carrying one cannot also be a
    fixed-size slot: the "array of N-byte slots" comment would be a lie and
    every slot after the first would be read at the wrong offset. No catalog
    layout does this today -- the point is that the day one does, the generator
    stops instead of emitting it. Its two sibling impossibilities (a field
    overlapping the previous one, fields running past the stride) already do."""
    impossible = Layout(
        name="Impossible",
        record="impossible",
        tag=1,
        dcl="",
        pool="others",
        fields=(Field(offset=0, size=0, name="descStr", type_="string", note="runs to the end"),),
        stride=24,
    )
    with pytest.raises(ValueError, match="both a tail field and a 24-byte stride"):
        _one_struct(impossible, "ImpossibleSlot")


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


def test_the_committed_pattern_is_current() -> None:
    """The pattern is generated, and a generated file that is committed can go
    stale silently. Adding a field to a layout must either update this file or
    fail this test -- there is no third outcome worth having.

    `docs/formats/finale-formats.{html,pdf}` are generated and committed with no
    such check; this is the one that has it.
    """
    from pathlib import Path

    committed = Path(__file__).parent.parent.parent / "docs" / "formats" / "finale-mus.hexpat"
    assert committed.exists(), "run: make hexpat"
    assert committed.read_text(encoding="utf-8") == render_pattern(), (
        "docs/formats/finale-mus.hexpat is stale -- run: make hexpat"
    )
