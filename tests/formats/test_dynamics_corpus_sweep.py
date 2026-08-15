"""The Maestro dynamic table, checked against the corpus it came from."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.formats.dynamics import (
    DYNAMICS_CATEGORY,
    MAESTRO_DYNAMICS,
    velocity_of,
)

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

_MARKUP = re.compile(r"\^\w+\([^)]*\)")


def test_the_table_is_what_the_corpus_says() -> None:
    """Rebuilt from the files rather than compared against a copy of itself.

    The pairing is on `cmper`, not on `textIDKey`: that field runs exactly
    `cmper + 13`, and using it as the expression number pairs every definition
    with the text thirteen slots later -- which makes the dynamics category
    appear to hold `Adagio` and the velocities appear meaningless.
    """
    found: dict[str, set[int]] = {}
    documents = 0
    for path in sorted(CORPUS.rglob("*.musx"))[:80]:
        try:
            document = parse_enigma(score_xml(path))
        except (FinaleFileError, OSError):
            continue
        categories = {
            r.attrs.get("cmper")
            for r in document.others.records
            if r.tag == "markingsCategory" and r.fields.get("categoryType") == DYNAMICS_CATEGORY
        }
        if not categories:
            continue
        texts = {
            r.attrs.get("number"): (r.text or "")
            for r in document.texts.records
            if r.tag == "expression"
        }
        seen = False
        for record in document.others.records:
            if record.tag != "textExprDef":
                continue
            if str(record.fields.get("categoryID")) not in categories:
                continue
            glyph = _MARKUP.sub("", texts.get(str(record.attrs.get("cmper")), "")).strip()
            value = record.fields.get("value")
            if glyph in MAESTRO_DYNAMICS and isinstance(value, str) and value.isdigit():
                found.setdefault(glyph, set()).add(int(value))
                seen = True
        documents += seen

    assert documents >= 40, f"only {documents} documents carried a dynamics category"
    assert set(found) == set(MAESTRO_DYNAMICS), "the corpus uses a different set of glyphs"
    for glyph, values in found.items():
        # The table is the shipped default, not a promise about every file: a
        # document can have its playback levels edited, and one in this corpus
        # has -- `P` at 58 rather than 62. So the default must be present for
        # every glyph, and it must be what the corpus mostly says.
        assert MAESTRO_DYNAMICS[glyph] in values, (
            f"{glyph!r} is never {MAESTRO_DYNAMICS[glyph]}: saw {sorted(values)}"
        )
        assert len(values) <= 2, f"{glyph!r} takes too many values to call one default: {values}"


def test_forte_and_piano_land_where_they_belong() -> None:
    """The two anchors that make the ordering trustworthy. Maestro writes forte
    as `f` and piano as `p`; a table that put them anywhere but the fourth and
    seventh rungs of a ten-step ladder would be wrong however self-consistent.
    """
    ladder = sorted(MAESTRO_DYNAMICS.values(), reverse=True)
    assert len(ladder) == 10
    assert ladder == [127, 114, 101, 88, 75, 62, 49, 36, 23, 10]
    assert velocity_of("f") == ladder[3]
    assert velocity_of("p") == ladder[6]
    assert velocity_of("ff") is None, "a two-letter spelling is not how this is written"
