"""Payload layouts for the record types this project has decoded.

A layout is a plain description of where a record's fields sit -- no bytes, no
prose, no rendering. It lives in the library rather than in the specification
generator because two readers need it: the generator, which draws each struct as
a tinted hex dump, and the inspector, which tints the bytes of a record actually
read from a file. Describing a field twice is how a document and a decoder come
to disagree about where a field sits.

Only nine record types appear here. One corpus document alone carries 146
`others` tags and 41 `details` tags, so most records have no layout -- those are
the ones whose meaning this project does not claim to know, and a consumer must
treat a missing layout as "not decoded" rather than as an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma import mus_others as OTH


@dataclass(frozen=True)
class Field:
    """One field of a binary structure.

    `note` states what the field means, in one line: it is shown beside the
    field wherever a layout is rendered.
    """

    offset: int
    size: int
    name: str
    type_: str
    note: str = ""

    @property
    def end(self) -> int:
        return self.offset + self.size


@dataclass(frozen=True)
class Layout:
    """A record type's payload layout.

    `tag` is the 2011-era numeric tag; `dcl` is the two-character tag the older
    DCL container uses for the same record, empty where that era has none. Both
    identify the same record type, so a consumer holding either can find this.
    """

    name: str
    """The struct's name, as the specification document writes it."""

    record: str
    """The record's name, as the readers and the report write it."""

    tag: int
    dcl: str
    pool: str
    """Which pool the record lives in: `others` or `details`."""

    fields: tuple[Field, ...]

    stride: int = 0
    """Non-zero when the payload is an array of fixed-size slots, each laid out
    by `fields`. Zero when the payload is a single structure."""

    def field_at(self, index: int) -> tuple[int, Field] | None:
        """The field covering byte `index`, with its position in `fields`.

        The position is what a renderer keys a colour to, so it must come from
        the same place as the field itself.
        """
        for i, f in enumerate(self.fields):
            if f.offset <= index < f.end:
                return i, f
        return None


MEAS_SPEC = Layout(
    name="MeasSpec",
    record="measSpec",
    tag=OTH.TAG_MEAS_SPEC,
    dcl="MS",
    pool="others",
    fields=(
        Field(0, 2, "width", "uint16", "measure width in EVPU"),
        Field(2, 2, "key", "uint16", "key signature; 0 means inherit"),
        Field(4, 2, "beats", "uint16", "time signature numerator"),
        Field(6, 2, "divbeat", "uint16", "EDU per beat; 1024 = quarter"),
        Field(10, 2, "flags", "uint16", "low byte holds the barline nibble"),
    ),
)

# The lead-in is 6 bytes for 2005 and 4 for 2001, so `startEntry` and
# `endEntry` move with the era. This layout states the 2005 shape. Reading a
# 2001 frameSpec at this base yields entry numbers that look plausible and are
# wrong, so a consumer that cannot establish the era must not apply it.
FRAME_SPEC_BASE_2005 = 6

FRAME_SPEC = Layout(
    name="FrameSpec",
    record="frameSpec",
    tag=OTH.TAG_FRAME_SPEC,
    dcl="FR",
    pool="others",
    fields=(
        Field(0, FRAME_SPEC_BASE_2005, "header", "uint8[]", "era-dependent lead-in"),
        Field(FRAME_SPEC_BASE_2005, 4, "startEntry", "uint32", "first entry number in this frame"),
        Field(FRAME_SPEC_BASE_2005 + 4, 4, "endEntry", "uint32", "last entry number, inclusive"),
    ),
)

GF_HOLD = Layout(
    name="GfHold",
    record="gfhold",
    tag=1044,
    dcl="GF",
    pool="details",
    fields=(
        Field(0, 2, "clefID", "uint16", "clef in force for this measure"),
        Field(6, 2, "frame1", "uint16", "layer 1 frame id; 0 = layer empty"),
        Field(8, 2, "frame2", "uint16", "layer 2 frame id"),
    ),
)

STAFF_SPEC = Layout(
    name="StaffSpec",
    record="staffSpec",
    tag=OTH.TAG_STAFF_SPEC,
    dcl="IS",
    pool="others",
    fields=(Field(20, 2, "transposition", "uint16", "written-to-sounding interval"),),
)

TUPLET_DEF = Layout(
    name="TupletDef",
    record="tupletDef",
    tag=1072,
    dcl="",
    pool="details",
    fields=(
        Field(0, 2, "symbolicNum", "uint16", "printed count, the 3 of a triplet"),
        Field(2, 2, "symbolicDur", "uint16", "printed unit in EDU"),
        Field(4, 2, "refNum", "uint16", "count these replace"),
        Field(6, 2, "refDur", "uint16", "unit they replace, in EDU"),
    ),
)

STAFF_GROUP = Layout(
    name="StaffGroup",
    record="staffGroup",
    tag=1057,
    dcl="",
    pool="details",
    fields=(
        Field(0, 2, "startInst", "uint16", "first staff in the group"),
        Field(2, 2, "endInst", "uint16", "last staff, inclusive"),
        Field(10, 2, "bracketId", "uint16", "bracket shape"),
        Field(21, 1, "barlineFlags", "uint8", "bit 0: barlines cross the group"),
    ),
)

LYRIC_VERSE = Layout(
    name="LyricVerseSlot",
    record="lyricVerse",
    tag=1108,
    dcl="",
    pool="details",
    fields=(
        Field(0, 2, "number", "uint16", "verse number"),
        Field(2, 2, "syll", "uint16", "syllable index into the text pool"),
        Field(8, 2, "wext", "uint16", "non-zero: word extends with a melisma"),
    ),
    stride=20,
)

ARTIC_ASSIGN = Layout(
    name="ArticAssign",
    record="articAssign",
    tag=1009,
    dcl="",
    pool="details",
    fields=(Field(0, 2, "definition", "uint16", "key of the articDef this uses"),),
)

INST_USED = Layout(
    name="InstUsedSlot",
    record="instUsed",
    tag=OTH.TAG_INST_USED,
    dcl="",
    pool="others",
    fields=(Field(0, 2, "staff", "uint16", "staff number, one per incidence"),),
    stride=24,
)

LAYOUTS: tuple[Layout, ...] = (
    MEAS_SPEC,
    FRAME_SPEC,
    GF_HOLD,
    STAFF_SPEC,
    TUPLET_DEF,
    STAFF_GROUP,
    LYRIC_VERSE,
    ARTIC_ASSIGN,
    INST_USED,
)


def _by_tag() -> dict[tuple[str, str], Layout]:
    """Both spellings of every tag, keyed with the pool that disambiguates them.

    A numeric tag and a DCL tag never collide -- one is digits, the other
    letters -- but a tag number is only unique within its pool, so the pool is
    part of the key rather than a thing the caller is trusted to check.
    """
    index: dict[tuple[str, str], Layout] = {}
    for layout in LAYOUTS:
        for spelling in (str(layout.tag), layout.dcl):
            if spelling:
                index[(layout.pool, spelling)] = layout
    return index


_INDEX = _by_tag()


def layout_for(pool: str, tag: str) -> Layout | None:
    """The layout for a record, or None when this project has not decoded it.

    `tag` is spelled as the readers spell it: a 2011 numeric tag as a string
    (`"176"`), or a two-character DCL tag (`"MS"`).
    """
    return _INDEX.get((pool, tag))
