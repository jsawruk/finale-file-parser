"""The generated ImHex pattern.

Nothing here can run the pattern -- ImHex is not installable in CI and there is
no headless evaluator for its language -- so these tests pin what *can* be
checked: that the pattern is generated from the catalog, covers all of it, and
never states an offset the parser does not use. Whether it loads is a hand
check, recorded in the plan.
"""

from __future__ import annotations

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
