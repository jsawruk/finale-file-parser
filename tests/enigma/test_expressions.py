"""Unit tests for the expressions a score actually places.

The trap here is the same one text repeats set, one record further along: every
Finale document ships a full library of expression *definitions* -- sixteen
dynamics, a shelf of tempo words -- whether the music uses any of them or not.
Only a `measExprAssign` puts a marking in the score. A reader that walks the
definitions prints a fortissimo in every part of every file.
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
from finale_file_parser.enigma.expressions import SCORE_WIDE_STAFF, expressions_by_measure

EMPTY: tuple[Record, ...] = ()

DYNAMICS_CATEGORY = 1
TEMPO_CATEGORY = 2


def category(cmper: int, kind: str) -> Record:
    return Record(
        tag="markingsCategory",
        attrs={"cmper": str(cmper)},
        text="",
        fields={"categoryType": kind},
    )


def definition(
    cmper: int,
    *,
    category_id: int = DYNAMICS_CATEGORY,
    value: int | None = None,
    desc: str = "",
    part: str | None = None,
) -> Record:
    attrs = {"cmper": str(cmper)}
    if part is not None:
        attrs["part"] = part
    fields = {"categoryID": str(category_id), "descStr": desc}
    if value is not None:
        fields["value"] = str(value)
    return Record(tag="textExprDef", attrs=attrs, text="", fields=fields)


def text(number: int, body: str, *, part: str | None = None) -> Record:
    attrs = {"number": str(number)}
    if part is not None:
        attrs["part"] = part
    return Record(tag="expression", attrs=attrs, text=body, fields={})


def assignment(
    measure: int,
    expr_id: int,
    *,
    staff: int = 1,
    layer: int | None = 1,
    inci: int = 0,
    part: str | None = None,
) -> Record:
    attrs = {"cmper": str(measure), "inci": str(inci)}
    if part is not None:
        attrs["part"] = part
    fields = {"textExprID": str(expr_id), "staffAssign": str(staff)}
    if layer is not None:
        fields["layer"] = str(layer)
    return Record(tag="measExprAssign", attrs=attrs, text="", fields=fields)


def library() -> tuple[Record, ...]:
    """The shipped dynamics library, in miniature: the four the tests use."""
    return (
        category(DYNAMICS_CATEGORY, "dynamics"),
        category(TEMPO_CATEGORY, "tempoMarks"),
        definition(3, value=101, desc="fortissimo (velocity = 101)"),
        definition(4, value=88, desc="forte (velocity = 88)"),
        definition(7, value=49, desc="piano (velocity = 49)"),
        definition(17, category_id=TEMPO_CATEGORY, value=40, desc="Adagio"),
        text(3, "^fontMus(Font0,0)^size(24)^nfx(0)Ä"),
        text(4, "^fontMus(Font0,0)^size(24)^nfx(0)f"),
        text(7, "^fontMus(Font0,0)^size(24)^nfx(0)p"),
        text(17, "^fontTxt(Font1,0)^size(14)Adagio"),
    )


def document(*others: Record) -> EnigmaDocument:
    texts = tuple(r for r in others if r.tag == "expression")
    rest = tuple(r for r in others if r.tag != "expression")
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=rest),
        details=DetailsPool(records=EMPTY),
        entries=EntriesPool(records=EMPTY),
        texts=TextsPool(records=texts),
    )


def test_the_library_alone_places_nothing() -> None:
    """Every corpus document ships these definitions; most use only a few of
    them. Reading the library puts a fortissimo in every score there is."""
    assert expressions_by_measure(document(*library())) == {}


def test_an_assignment_places_its_marking_on_its_staff_and_measure() -> None:
    doc = document(*library(), assignment(measure=12, expr_id=4, staff=2))
    found = expressions_by_measure(doc)
    assert set(found) == {(2, 12)}
    (marking,) = found[(2, 12)]
    assert marking.text == "f"
    assert marking.marking == "f"
    assert marking.category == "dynamics"
    assert marking.velocity == 88
    assert marking.layer == 1


def test_the_glyph_is_resolved_to_a_readable_marking() -> None:
    """The file stores one music-font character. A consumer that printed it
    literally would put an A-umlaut in the score where a fortissimo belongs."""
    doc = document(*library(), assignment(1, 3))
    (marking,) = expressions_by_measure(doc)[(1, 1)]
    assert marking.text == "Ä"
    assert marking.marking == "ff"


def test_two_staves_get_their_own_markings() -> None:
    """The point of the record: an expression belongs to a staff, so the parts
    can and do differ. `directions` cannot express this."""
    doc = document(
        *library(),
        assignment(5, 4, staff=1),
        assignment(5, 7, staff=2, inci=1),
    )
    found = expressions_by_measure(doc)
    assert found[(1, 5)][0].marking == "f"
    assert found[(2, 5)][0].marking == "p"


def test_a_measure_can_carry_more_than_one() -> None:
    doc = document(*library(), assignment(9, 4), assignment(9, 7, inci=1))
    assert [e.marking for e in expressions_by_measure(doc)[(1, 9)]] == ["f", "p"]


def test_an_expression_with_no_layer_belongs_to_the_staff() -> None:
    """1,708 of the corpus's 6,672 assigned dynamics carry no `layer` at all."""
    doc = document(*library(), assignment(3, 4, layer=None))
    assert expressions_by_measure(doc)[(1, 3)][0].layer is None


def test_a_tempo_word_keeps_its_own_category_and_no_marking() -> None:
    """`marking` is for the ten graded dynamics. A tempo word is carried as
    text, in the category the file itself gives it."""
    doc = document(*library(), assignment(1, 17))
    (found,) = expressions_by_measure(doc)[(1, 1)]
    assert found.text == "Adagio"
    assert found.category == "tempoMarks"
    assert found.marking is None
    assert found.velocity == 40


def test_a_part_linked_assignment_is_skipped() -> None:
    """20,606 of the corpus's 33,039 assignments carry a `part` attribute --
    the linked-part copies. Counting them doubles every marking."""
    doc = document(*library(), assignment(2, 4, part="1"))
    assert expressions_by_measure(doc) == {}


def test_an_assignment_naming_a_definition_that_is_not_there_is_dropped() -> None:
    assert expressions_by_measure(document(*library(), assignment(2, 999))) == {}


def test_a_definition_whose_text_is_missing_is_dropped() -> None:
    """306 corpus assignments resolve to a definition with no expression text.
    An expression with nothing to print is not a marking."""
    doc = document(*library(), definition(50, value=88), assignment(2, 50))
    assert expressions_by_measure(doc) == {}


def test_an_unidentified_glyph_is_still_carried() -> None:
    """Unlike a text repeat, an unrecognised expression glyph is kept rather
    than dropped: the exporter decides what it can print, and dropping it here
    would lose the fact that the score marks something at that measure.
    """
    doc = document(
        *library(),
        definition(60, category_id=DYNAMICS_CATEGORY, desc="sforzato"),
        text(60, "^fontMus(Font0,0)§"),
        assignment(6, 60),
    )
    (found,) = expressions_by_measure(doc)[(1, 6)]
    assert found.text == "§"
    assert found.marking is None
    assert found.category == "dynamics"


def test_a_dynamic_glyph_in_a_custom_category_is_still_a_dynamic() -> None:
    """1,191 corpus assignments are a user copy of a Maestro dynamic filed under
    `techniqueText`. It is still the fortissimo character, and the music font
    says so."""
    doc = document(
        *library(),
        category(25, "techniqueText"),
        definition(40, category_id=25, desc="fortissimo (Copy)"),
        text(40, "^fontMus(Font0,0)^size(24)Ä"),
        assignment(4, 40),
    )
    (found,) = expressions_by_measure(doc)[(1, 4)]
    assert found.category == "techniqueText"
    assert found.marking == "ff"


def test_a_bare_letter_in_a_text_font_is_not_read_as_a_dynamic() -> None:
    """The guard this rule exists for: Maestro writes forte as `f`, so matching
    the character alone would turn a literal "f" label into a fortissimo.

    Across 401 documents nothing set in a text font ever matches the dynamics
    table, so this costs nothing real and removes the whole failure mode.
    """
    doc = document(
        *library(),
        category(25, "misc"),
        definition(41, category_id=25),
        text(41, "^fontTxt(Font1,0)^size(12)f"),
        assignment(4, 41),
    )
    (found,) = expressions_by_measure(doc)[(1, 4)]
    assert found.text == "f"
    assert found.marking is None, "a letter in a text font is not a dynamic"


def test_a_glyph_with_no_font_markup_falls_back_to_the_category() -> None:
    """114 corpus assignments carry no font markup but sit in the dynamics
    category, which is signal enough. The 129 that carry neither are left
    unmarked rather than guessed at."""
    doc = document(*library(), definition(42, value=88), text(42, "f"), assignment(5, 42))
    assert expressions_by_measure(doc)[(1, 5)][0].marking == "f"

    doc = document(
        *library(),
        category(26, "misc"),
        definition(43, category_id=26),
        text(43, "f"),
        assignment(6, 43),
    )
    assert expressions_by_measure(doc)[(1, 6)][0].marking is None


def test_a_definition_whose_text_is_only_markup_is_dropped() -> None:
    """Distinct from a missing text record, and the case a missing-record test
    does not reach: the record is present and its content is entirely font and
    size commands, so it prints nothing. `plain_text` correctly returns "" --
    a direction with no words is not a marking.
    """
    doc = document(
        *library(),
        definition(51, value=88),
        text(51, "^fontMus(Font0,0)^size(24)^nfx(0)"),
        assignment(8, 51),
    )
    assert expressions_by_measure(doc) == {}


def test_a_score_wide_assignment_keeps_its_sentinel_and_is_flagged() -> None:
    """`staffAssign = -1` means a staff list, not a staff. The reader keeps the
    sentinel as the key so `to_ir` can decide where a score-wide marking goes,
    and flags the expression so the fact is not lost in the move."""
    doc = document(*library(), assignment(4, 4, staff=-1, layer=None))
    found = expressions_by_measure(doc)
    assert set(found) == {(SCORE_WIDE_STAFF, 4)}
    (marking,) = found[(SCORE_WIDE_STAFF, 4)]
    assert marking.score_wide is True
    assert marking.marking == "f"


def test_a_score_wide_copy_of_a_marking_already_on_a_staff_is_dropped() -> None:
    """A score expression is drawn once. Where the same measure also assigns the
    same expression to a real staff, the score-wide copy would print it twice --
    102 of the corpus's 746 list assignments are this shape.
    """
    doc = document(
        *library(),
        assignment(7, 4, staff=2),
        assignment(7, 4, staff=-1, inci=1, layer=None),
    )
    found = expressions_by_measure(doc)
    assert set(found) == {(2, 7)}, "the redundant score-wide copy should be gone"


def test_a_score_wide_marking_survives_when_nothing_else_places_it() -> None:
    """The 644 that are not redundant must still come through: dropping all of
    them is what cost 596 markings before this existed."""
    doc = document(
        *library(),
        assignment(7, 7, staff=2),
        assignment(7, 4, staff=-1, inci=1, layer=None),
    )
    found = expressions_by_measure(doc)
    assert set(found) == {(2, 7), (SCORE_WIDE_STAFF, 7)}
