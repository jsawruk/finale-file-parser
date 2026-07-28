"""Resolve a document's staff groups: the braces and brackets down the left edge.

A `staffGroup` detail record spans a run of staves and says how they are joined.
Its field order is documented — `etfspec.pdf` describes the ETF `NG` record as
`startInst endInst fullNameID fullXadj fullYadj | bracketType bracPos bracTop
bracBot bracFlag | flag abrvNameID ...` — and the `.mus` binary lays those out in
the same order, which is how `mus_document` reads it.

**`startInst` and `endInst` are staff numbers, not slots in the instrument
list.** The two readings agree wherever a document's instrument list happens to
run 1, 2, 3…, which is most of them; the 31 corpus documents where it does not
are the ones that decide, and there all 75 groups name a staff. Reading them as
slots would group the wrong staves in exactly those documents.

The staves a group covers are then the run **in instrument-list order**, not the
numeric range between the two. Those differ in 14 of 230 corpus groups, because
a score can lay its staves out in an order its staff numbers do not follow.

Bracket shapes are an enum this project has partial evidence for:

* **3 is the piano brace** — `etfspec.pdf` says so outright ("bracket type: 3
  (piano brace)"), and the corpus agrees with what a brace can do: all 132 span
  exactly two staves, none contains another group, none is named.
* **6 is the section bracket.** No direct documentation, but it is the only id
  that ever contains another group (14 of 78), the only one spanning more than
  two staves (34 of 78), and the only one carrying a group name (31 of 78). Those
  are facts about the grammar of a score rather than about what this repertoire
  contains: a brace cannot span five staves or wrap another group, and a bracket
  can.
* **8 is left unmapped.** All 20 sit nested inside another group and none is
  named, which says it is a sub-group marker but not what it is drawn as —
  MusicXML's `square` and `brace` are both consistent with that. The group is
  still emitted, with its barline and extent; only the symbol is withheld, the
  same way `enigma.articulations` declines to name a character it cannot place.

`groupBarlineStyle` is `group` where barlines run through the whole group, and
absent otherwise. Only the positive is read: `.musx` writes nothing for the other
case, and one corpus document is too thin a basis for claiming what nothing
means.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.text import plain_text, text_block

__all__ = ["BRACKET_SYMBOLS", "StaffGroup", "staff_groups", "staff_order"]

_GROUP = "staffGroup"
_INST_USED = "instUsed"
_SCORE_LIST = "0"
"""`staffGroup.cmper1` and `instUsed.cmper` both name an instrument list; 0 is
the score's own. Every corpus group uses it."""

BRACKET_SYMBOLS = {3: "brace", 6: "bracket"}
"""Finale bracket id -> MusicXML `<group-symbol>`.

Deliberately partial; see the module docstring for what each rests on and why 8
is absent.
"""

_GROUP_BARLINE = "group"


@dataclass(frozen=True)
class StaffGroup:
    """One brace or bracket, and the staves it joins."""

    staves: tuple[int, ...]
    """Every staff in the group, in instrument-list order."""

    symbol: str | None
    """MusicXML `<group-symbol>`, or None where the bracket id is unmapped."""

    barline: bool
    """Barlines run through the group rather than stopping at each staff."""

    name: str = ""
    abbreviation: str = ""


def staff_order(document: EnigmaDocument) -> tuple[int, ...]:
    """The staves of the score, in the order the document lays them out.

    `instUsed` holds one record per slot, and a slot's `inst` is its staff. That
    order is not always ascending -- 10 corpus documents lay staves out in an
    order their staff numbers do not follow -- so it cannot be replaced by
    sorting where the record exists.

    Where it does not, the staves are returned in numeric order. A `.mus` always
    takes that path: its `instUsed` equivalent is unidentified, and the corpus
    cannot identify it, because **every** paired document numbers its slots and
    staves alike, so no pair distinguishes a right guess from a wrong one. The
    fallback is therefore equivalent on all available evidence, and wrong only
    for a `.mus` whose staves are laid out out of order -- which no paired
    document is. See `enigma.mus_document.UNTRANSLATED`.
    """
    slots: list[tuple[int, int]] = []
    for record in document.others.all_with(_INST_USED, _SCORE_LIST):
        # `all_with` returns the score record *and* every linked-part variant;
        # keeping the variants lists each staff once per part and corrupts the
        # order the groups are resolved through.
        if "part" in record.attrs:
            continue
        inci = _int(record.attrs.get("inci"))
        staff = _int(record.fields.get("inst"))
        if inci is not None and staff is not None:
            slots.append((inci, staff))
    if slots:
        return tuple(staff for _, staff in sorted(slots))
    return tuple(sorted(_staves(document)))


def _staves(document: EnigmaDocument) -> set[int]:
    return {
        staff
        for record in document.others.of_tag("staffSpec")
        if "part" not in record.attrs and (staff := _int(record.attrs.get("cmper"))) is not None
    }


def staff_groups(document: EnigmaDocument) -> tuple[StaffGroup, ...]:
    """Every staff group in the score, outermost first.

    A group whose endpoints are missing from the instrument list, or which runs
    backwards through it, is dropped: the corpus holds three of the latter, and
    a reversed span would brace a run of staves the score does not group.
    """
    order = staff_order(document)
    position = {staff: index for index, staff in enumerate(order)}

    out: list[StaffGroup] = []
    for record in document.details.of_tag(_GROUP):
        # Score records only, as everywhere else: a linked part can restate a
        # group, and counting both braces the same staves twice.
        if record.attrs.get("cmper1") != _SCORE_LIST or "part" in record.attrs:
            continue
        start = _int(record.fields.get("startInst"))
        end = _int(record.fields.get("endInst"))
        if start is None or end is None or start not in position or end not in position:
            continue
        first, last = position[start], position[end]
        if first > last:
            continue
        out.append(
            StaffGroup(
                staves=order[first : last + 1],
                symbol=BRACKET_SYMBOLS.get(_bracket_id(record) or -1),
                barline=record.fields.get("groupBarlineStyle") == _GROUP_BARLINE,
                name=_name(document, record.fields.get("fullID")),
                abbreviation=_name(document, record.fields.get("abbrvID")),
            )
        )
    # Outermost first, so an exporter opening groups in this order nests them
    # correctly; a wider group must open before the one it contains.
    return tuple(sorted(out, key=lambda group: (-len(group.staves), position[group.staves[0]])))


def _bracket_id(record: Record) -> int | None:
    bracket = record.fields.get("bracket")
    if not isinstance(bracket, Record):
        return None
    return _int(bracket.fields.get("id"))


def _name(document: EnigmaDocument, field: object) -> str:
    if not isinstance(field, str):
        return ""
    number = _int(field)
    if number is None or number == 0:
        return ""
    return plain_text(text_block(document, number) or "")


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
