"""Where a frameSpec keeps its entry pair, as the layout states it.

The corpus measurement behind this lives in
`test_frame_spec_offset_corpus_sweep.py` -- it reads every paired document and
costs about a minute, which does not belong on the path run between edits.
"""

from __future__ import annotations

from finale_file_parser.formats.layouts import FRAME_SLOT, FRAME_SPEC


def test_the_layout_puts_the_pair_at_the_start_of_a_slot() -> None:
    """+0 and +4 of a 12-byte slot, not +6 and +10 of the payload."""
    by_name = {f.name: f for f in FRAME_SPEC.fields}
    assert by_name["startEntry"].offset == 0
    assert by_name["endEntry"].offset == 4
    assert FRAME_SPEC.stride == FRAME_SLOT == 12
    assert FRAME_SPEC.computed, "which slot holds the pair depends on the record"
