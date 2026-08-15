"""The Maestro dynamic table, checked against the corpus it came from."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.formats.dynamics import (
    ACCENT_DYNAMICS,
    DYNAMICS,
    DYNAMICS_CATEGORY,
    GRADED_DYNAMICS,
    MAESTRO_DYNAMICS,
    dynamic_for,
    marking_of,
    velocity_of,
)

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

_MARKUP = re.compile(r"\^\w+\([^)]*\)")
_VELOCITY = re.compile(r"velocity\s*=\s*(\d+)", re.IGNORECASE)


def _name_in(desc: str) -> str:
    """The words `descStr` uses, without the velocity or a `(Copy)` suffix.

    Normalised for case and doubled spaces: one Finale version writes
    `'Fortissimo  (Velocity = 101)'` where the rest write
    `'fortissimo (velocity = 101)'`, and that is the same name.
    """
    return " ".join(desc.split("(")[0].split()).lower()


class _Reading:
    """What the corpus says, rebuilt from the files rather than compared against
    a copy of the table."""

    def __init__(self) -> None:
        self.names: dict[str, Counter[str]] = defaultdict(Counter)
        self.velocities: dict[str, Counter[int]] = defaultdict(Counter)
        self.self_consistent = 0
        self.edited = 0
        self.documents = 0
        self.desynchronised = 0


def _rows(doc: EnigmaDocument) -> list[tuple[str, str, str | None]]:
    """(glyph, name, value) for every dynamic definition, joined on `cmper`."""
    categories = {
        r.attrs.get("cmper")
        for r in doc.others.records
        if r.tag == "markingsCategory" and r.fields.get("categoryType") == DYNAMICS_CATEGORY
    }
    if not categories:
        return []
    texts = {
        str(r.attrs.get("number")): (r.text or "")
        for r in doc.texts.records
        if r.tag == "expression"
    }
    out: list[tuple[str, str, str | None]] = []
    for record in doc.others.records:
        if record.tag != "textExprDef":
            continue
        if str(record.fields.get("categoryID")) not in categories:
            continue
        desc = str(record.fields.get("descStr") or "")
        # A user duplicate keeps the description of whatever it was copied from
        # while its text is retyped, so it says nothing about a glyph.
        if not desc or "(Copy)" in desc:
            continue
        glyph = _MARKUP.sub("", texts.get(str(record.attrs.get("cmper")), "")).strip()
        if not glyph:
            continue
        value = record.fields.get("value")
        out.append((glyph, _name_in(desc), value if isinstance(value, str) else None))
    return out


def _join_holds(rows: list[tuple[str, str, str | None]]) -> bool:
    """Is this document's `cmper` join actually aligned?

    Two anchors decide it: Maestro writes *forte* as `f` and *piano* as `p`, so
    the definition described as `forte` must print `f`. One corpus document had
    *mezzo forte* deleted, which renumbered the definitions while the text
    records kept their old numbers -- every glyph below the hole then pairs with
    its neighbour's description. Such a document must not contribute a glyph,
    and dropping it silently would be worse than failing.
    """
    anchors = {"forte": "f", "piano": "p"}
    seen: set[str] = set()
    for glyph, name, _ in rows:
        want = anchors.get(name)
        if want is None:
            continue
        if glyph != want:
            return False
        seen.add(name)
    # Both anchors must actually be present -- but a document may carry the
    # library twice (two leadsheets here do, from a merge), so count distinct
    # anchors rather than rows.
    return seen == set(anchors)


@pytest.fixture(scope="module")
def reading() -> _Reading:
    out = _Reading()
    for path in sorted(CORPUS.rglob("*.musx")):
        try:
            document = parse_enigma(score_xml(path))
        except (FinaleFileError, OSError):
            continue
        rows = _rows(document)
        if not rows:
            continue
        if not _join_holds(rows):
            out.desynchronised += 1
            continue
        for glyph, name, value in rows:
            out.names[glyph][name] += 1
            if isinstance(value, str) and value.isdigit():
                out.velocities[glyph][int(value)] += 1
        out.documents += 1
        # descStr and value are in the same record, so they agree unless a user
        # edited the playback level. Counted on the raw description, which
        # `_name_in` has stripped by now.
        for record in document.others.records:
            if record.tag != "textExprDef":
                continue
            desc = str(record.fields.get("descStr") or "")
            raw = record.fields.get("value")
            stated = _VELOCITY.search(desc)
            if not stated or not (isinstance(raw, str) and raw.isdigit()):
                continue
            if "(Copy)" in desc:
                continue
            if int(stated.group(1)) == int(raw):
                out.self_consistent += 1
            else:
                out.edited += 1
    return out


def test_the_corpus_is_large_enough_to_conclude_from(reading: _Reading) -> None:
    """Pinned so that a sweep which quietly stops early fails instead of passing.

    401 documents parse; 396 of them reach a named dynamic.
    """
    assert reading.documents >= 390, (
        f"only {reading.documents} documents carried a dynamics category"
    )
    assert reading.self_consistent >= 4200, (
        f"only {reading.self_consistent} records had descStr and value agree"
    )
    # Stated rather than implied: the corpus holds three copies of the one
    # document whose numbering is desynchronised (`Christmas Canon.musx`, which
    # had its mezzo forte deleted). Pinned exactly, in both directions -- a rise
    # means the join is slipping somewhere new, and a drop to zero means the
    # check that catches it has stopped working, which is the worse failure
    # because everything downstream would still look green.
    assert reading.desynchronised == 3, (
        f"{reading.desynchronised} documents failed the join check, expected 3"
    )


def test_the_file_names_every_graded_dynamic(reading: _Reading) -> None:
    """The heart of it: each glyph's name is read out of `descStr`, not assumed.

    This is what makes the table a reading rather than a guess -- delete a row
    from `GRADED_DYNAMICS` or mis-spell one and this fails.
    """
    for entry in GRADED_DYNAMICS:
        found = reading.names.get(entry.glyph)
        assert found, f"{entry.glyph!r} never appeared in a dynamics category"
        name, count = found.most_common(1)[0]
        assert name == entry.name, f"{entry.glyph!r} is called {name!r}, not {entry.name!r}"
        assert count >= 300, f"{entry.glyph!r} is only named {name!r} in {count} documents"


def test_descstr_and_value_agree_on_the_velocity(reading: _Reading) -> None:
    """Two fields of one record saying the same number. The exceptions are named:
    two documents have an edited playback level, so a handful of records differ.
    """
    assert reading.edited <= 40, f"{reading.edited} records disagree, too many to call edits"
    assert reading.self_consistent > reading.edited * 50


def test_the_velocities_are_what_the_corpus_says(reading: _Reading) -> None:
    for entry in GRADED_DYNAMICS:
        values = reading.velocities[entry.glyph]
        assert entry.velocity in values, (
            f"{entry.glyph!r} is never {entry.velocity}: saw {sorted(values)}"
        )
        # The default must also be the *usual* reading, not a rare one.
        assert values.most_common(1)[0][0] == entry.velocity


def test_the_accent_dynamics_ship_without_a_level(reading: _Reading) -> None:
    """They shape an attack rather than setting a level, so the shipped library
    gives them no `value` -- which is what a velocity of None records.

    Not "can never have one": a user may set a playback level on any expression,
    and one corpus document has given its *sforzando* 88 with
    `playType='amplitude'`. The test therefore pins the default, allowing a
    handful of documents to differ, rather than claiming the field is always
    absent.
    """
    for entry in ACCENT_DYNAMICS:
        assert entry.velocity is None
        documents_with_a_level = sum(reading.velocities.get(entry.glyph, Counter()).values())
        assert documents_with_a_level <= 5, (
            f"{entry.glyph!r} carries a velocity in {documents_with_a_level} documents, "
            f"too many to call it undefaulted: {reading.velocities[entry.glyph]}"
        )
        found = reading.names.get(entry.glyph)
        assert found, f"{entry.glyph!r} never appeared"
        name, count = found.most_common(1)[0]
        assert name == entry.name, f"{entry.glyph!r} is called {name!r}, not {entry.name!r}"
        assert count >= 300, f"{entry.glyph!r} is only named {name!r} in {count} documents"


def test_the_ladder_is_even_and_the_anchors_land(reading: _Reading) -> None:
    """The ordering check, kept from before the names were read: Maestro writes
    forte as `f` and piano as `p`, and those must sit on the fourth and seventh
    rungs of a ten-step ladder. Now that the names are known this is a
    cross-check on them rather than the only evidence for the order.
    """
    ladder = [d.velocity for d in GRADED_DYNAMICS]
    assert ladder == [127, 114, 101, 88, 75, 62, 49, 36, 23, 10]
    assert velocity_of("f") == ladder[3]
    assert velocity_of("p") == ladder[6]
    assert marking_of("f") == "f"
    assert marking_of("p") == "p"
    assert velocity_of("ff") is None, "a two-letter spelling is not how this is written"
    assert dynamic_for("ff") is None


def test_the_two_sforzato_glyphs_are_left_unnamed() -> None:
    """The file gives `§` and `\\x8d` the same description, so which is which is
    not established. A future edit that names one must bring evidence; this test
    exists so that doing it silently fails.
    """
    sforzato = [d for d in DYNAMICS if d.name == "sforzato"]
    assert len(sforzato) == 2, f"expected two glyphs described 'sforzato', got {sforzato}"
    assert {d.glyph for d in sforzato} == {"§", "\x8d"}
    named = [d for d in sforzato if d.marking is not None]
    assert not named, (
        f"a marking was claimed for {named} -- descStr does not distinguish the two "
        "sforzato glyphs, so naming one needs evidence from outside the file"
    )


def test_maestro_dynamics_holds_only_the_levelled_ones() -> None:
    """The compatibility mapping is glyph to velocity, so it must not silently
    gain the accent dynamics as zeroes or Nones."""
    assert MAESTRO_DYNAMICS == {d.glyph: d.velocity for d in GRADED_DYNAMICS} | {"subito p": 49}
    assert all(isinstance(v, int) for v in MAESTRO_DYNAMICS.values())
