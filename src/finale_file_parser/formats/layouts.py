"""Payload layouts for the record types this project has decoded.

A layout is a plain description of where a record's fields sit -- no bytes, no
prose, no rendering. It lives in the library rather than in the specification
generator because two readers need it: the generator, which draws each struct as
a tinted hex dump, and the inspector, which tints the bytes of a record actually
read from a file. Describing a field twice is how a document and a decoder come
to disagree about where a field sits.

Twelve layouts appear here, for eleven record types -- `textExprDef` gets two,
one per era, because what the 2011 record confirms does not all carry back to the
older DCL spelling. One corpus document alone carries 146 `others` tags and 41
`details` tags, so most records have no layout -- those are the ones whose
meaning this project does not claim to know, and a consumer must treat a missing
layout as "not decoded" rather than as an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma import mus_others as OTH

PALETTE = (
    "#ffd9d9",
    "#d9ecff",
    "#dcffd9",
    "#fff3cc",
    "#e8d9ff",
    "#d9fbff",
    "#ffe0f0",
    "#eaeaea",
)
"""Tints for a struct's fields, taken in turn and keyed by field position.

Presentation, but it belongs here: the colour a field gets is its index in
`fields`, so the palette and the ordering it indexes have to travel together.
Both renderers use it -- the specification's hex dumps and the inspector's --
so a field is the same colour in the document and in the tool. Chosen to stay
legible in print: light enough for black text, distinct in greyscale.
"""


@dataclass(frozen=True)
class Field:
    """One field of a binary structure.

    `note` states what the field means, in one line: it is shown beside the
    field wherever a layout is rendered.
    """

    offset: int

    size: int
    """Bytes the field occupies, or **0 for a variable-length tail**.

    A NUL-terminated string running to the end of the payload has no fixed width
    -- a `textExprDef` description sits at `+36` in records of 48, 60 and 72
    bytes. Only the last field of a layout may use 0, and its note must say what
    ends it.
    """

    name: str
    type_: str
    note: str = ""

    @property
    def is_tail(self) -> bool:
        """True for a variable-length field: it claims every byte from `offset`
        to the end of whatever payload the caller is holding."""
        return self.size == 0

    @property
    def end(self) -> int:
        """One past the last byte of a fixed-size field.

        A tail has no end to give -- where it stops depends on the payload in
        front of the caller and not on the layout -- so this returns `offset`,
        an empty span, and `is_tail` is what a caller branches on.

        It deliberately does **not** return a large sentinel. `end` is what a
        renderer subtracts one from and what a loop counts up to, and
        `range(f.offset, f.end)` reads as safe at a glance; with `sys.maxsize`
        here that line became an allocation that ran until the machine gave out
        -- 28.8 GB in one pytest process before it was killed.
        """
        return self.offset + self.size


@dataclass(frozen=True)
class Layout:
    """A record type's payload layout.

    `tag` is the 2011-era numeric tag; `dcl` is the two-character tag the older
    DCL container uses for the same record, empty where that era has none. Both
    identify the same record type, so a consumer holding either can find this.

    The reverse also happens: `tag` is **0** for a layout that describes only the
    DCL spelling, where what is confirmed of the 2011 record does not carry
    across. `DT` is the case -- its `+4` and its description are established and
    its enums measurably are not, so the two eras get two layouts rather than one
    that overstates the older.
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

    computed: bool = False
    """True when a reader works out where these fields sit, per record or era.

    Such a layout still describes the record -- the specification draws it, and
    it is the shape a reader starts from -- but it must not be laid over the
    bytes of an arbitrary record, because the reader does not read that record
    at these offsets. Every consumer that points a layout at real bytes has to
    skip these, or work the offsets out the same way the reader does.

    Named for what is true of both cases rather than for one of them. This flag
    was called `era_dependent`, which is right for `gfhold` -- its frame slots
    sit at an era base of 4 or 6 -- and wrong for `frameSpec`, whose entry pair
    moves with the individual record's length and not with the era at all. The
    old name asserted the very thing the corpus disproved.
    """

    def field_at(self, index: int) -> tuple[int, Field] | None:
        """The field covering byte `index`, with its position in `fields`.

        The position is what a renderer keys a colour to, so it must come from
        the same place as the field itself.

        A tail covers every byte from its offset on, however long the payload
        turns out to be -- a `textExprDef` description sits at `+36` in records
        of 48, 60 and 72 bytes, and the caller is the one holding the length.
        """
        for i, f in enumerate(self.fields):
            if f.offset <= index and (f.is_tail or index < f.end):
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

FRAME_SLOT = 12
"""A frameSpec payload is an array of 12-byte slots, one per incidence."""

# **The entry pair is in the LAST slot, at +0 and +4 -- not at +6.**
#
# Measured against 10,290 frameSpec records in paired documents, comparing every
# candidate offset with the startEntry/endEntry the paired `.musx` states: the
# pair matched at `(incidences - 1) * 12` in all 10,290, and at +6 in none. The
# shapes are 12-byte single-slot (10,275) and 24-byte two-slot (15), and the
# 2001-2005 cohort carries exactly the same two (4,571 and 27), so the offset
# does not vary by era either.
#
# The specification used to draw a 6-byte lead-in with startEntry at +6, and
# annotate it "the base offset differs by era: 4 for 2001, 6 for 2005". Those
# two numbers are real but belong to `gfhold`, whose frame slots do sit at an
# era base -- see GFHOLD_FRAME_BASE_2005. Nothing supports them here: the
# vendored ETF documentation does not describe this record at all.
FRAME_SPEC = Layout(
    name="FrameSpec",
    record="frameSpec",
    tag=OTH.TAG_FRAME_SPEC,
    dcl="FR",
    pool="others",
    fields=(
        Field(0, 4, "startEntry", "uint32", "first entry number in this frame"),
        Field(4, 4, "endEntry", "uint32", "last entry number, inclusive"),
        Field(8, 4, "unused", "uint32", "zero in all 10,465 corpus records"),
    ),
    stride=FRAME_SLOT,
    # Which slot carries the pair depends on how many the record has, so the
    # fields above describe the LAST one. A leading slot holds a startTime u32
    # at +0 instead -- in EDU from the start of the measure -- so laying this
    # over one would read a time as an entry number.
    computed=True,
)

GFHOLD_FRAME_BASE_2005 = 6
"""Where a gfhold's frame slots start in a 2005 document; 2001 uses 4.

`mus_document._rows_details` reads them at `base + 2 * layer`, with the base
established per document from whether the first staffSpec carries three
incidences. `clefID` at +0 does not move.

This is the era split the specification once attributed to `frameSpec` too,
where it does not apply -- the two numbers were real, and on the wrong record.
"""

GF_HOLD = Layout(
    name="GfHold",
    record="gfhold",
    tag=1044,
    dcl="GF",
    pool="details",
    fields=(
        Field(0, 2, "clefID", "uint16", "clef in force for this measure"),
        Field(GFHOLD_FRAME_BASE_2005, 2, "frame1", "uint16", "layer 1 frame id; 0 = layer empty"),
        Field(GFHOLD_FRAME_BASE_2005 + 2, 2, "frame2", "uint16", "layer 2 frame id"),
    ),
    computed=True,
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

TEXT_EXPR_DEF = Layout(
    name="TextExprDef",
    record="textExprDef",
    tag=OTH.TAG_TEXT_EXPR_DEF,
    dcl="",
    pool="others",
    fields=(
        Field(0, 2, "textIDKey", "uint16", "points at the expression text; not its number"),
        Field(4, 2, "value", "uint16", "playback level; the velocity for a dynamic"),
        Field(
            6, 2, "auxdata1", "uint16", "purpose unknown; agrees with the .musx field of that name"
        ),
        Field(8, 2, "playPass", "uint16", "which repeat pass it plays on"),
        Field(
            12,
            2,
            "horzMeasExprAlign",
            "uint16",
            "1 startTimeSig, 3 manual, 13 leftOfPrimaryNotehead, 14 rightOfAllNoteheads",
        ),
        Field(
            24,
            2,
            "vertMeasExprAlign",
            "uint16",
            "2 manual, 4 topNote, 8 aboveStaffOrEntry, 9 belowStaffOrEntry",
        ),
        Field(30, 2, "yAdjustBaseline", "int16", "vertical offset from the baseline, in EVPU"),
        Field(32, 2, "yAdjustEntry", "int16", "vertical offset from the entry, in EVPU"),
        Field(36, 0, "descStr", "string", "the marking in words, NUL-terminated, runs to the end"),
    ),
)
"""The 2011 numeric spelling. Every field confirmed by exact equality against the
97 paired documents -- see `mus_others.TAG_TEXT_EXPR_DEF` for the counts.

`categoryID` and `playType` are absent because neither is identified.

**`dcl` is empty on purpose.** The DCL container spells this record `DT`, but only
its `+4` and its description survive the crossing: no offset in a `DT` payload
separates the "Below Staff" descriptions from the rest, so the enums above are not
evidenced there. `TEXT_EXPR_DEF_DCL` describes what is.
"""

TEXT_EXPR_DEF_DCL = Layout(
    name="TextExprDef",
    record="textExprDef",
    tag=0,
    dcl="DT",
    pool="others",
    fields=(
        Field(0, 2, "counter", "uint16", "runs with cmper; the 2011 record has textIDKey here"),
        Field(4, 2, "value", "uint16", "playback level; read in the document's byte order"),
        Field(36, 0, "descStr", "string", "the marking in words, NUL-terminated, runs to the end"),
    ),
)
"""What a DCL `DT` payload is known to hold -- three fields, not the twelve of the
2011 record.

`+4` is confirmed **without any paired document**: the description states the
velocity in words, and it equals the `uint16` at `+4` in **434 records out of 434,
with zero disagreements**. The record vouches for its own field.

Deliberately smaller than `TEXT_EXPR_DEF`. Laying that layout over these bytes
would name `+12` and `+24` as alignment enums, and the corpus says otherwise: no
offset separates the `Below Staff` descriptions. Two eras, two layouts.

**Read `+4` in the document's byte order.** 37 corpus documents are big-endian,
where a little-endian reading turns 127 into 32,512.
"""

MEAS_EXPR_ASSIGN_SLOT = 24

MEAS_EXPR_ASSIGN = Layout(
    name="MeasExprAssign",
    record="measExprAssign",
    tag=OTH.TAG_MEAS_EXPR_ASSIGN,
    dcl="",
    pool="others",
    stride=MEAS_EXPR_ASSIGN_SLOT,
    fields=(
        Field(0, 2, "textExprID", "uint16", "names a textExprDef; a shapeExprID when +11 has 0x20"),
        Field(2, 2, "horzEduOff", "int16", "horizontal offset in EDU, along the measure"),
        Field(4, 2, "horzEvpuOff", "int16", "horizontal offset in EVPU"),
        Field(6, 2, "vertOff", "int16", "vertical offset in EVPU"),
        Field(8, 2, "staffAssign", "int16", "the staff, or -1 for a staff list"),
        Field(11, 1, "flags", "uint8", "0x20 marks a shape assignment rather than a text one"),
        Field(12, 2, "staffGroup", "uint16", "the group, on a staff-list assignment"),
        Field(14, 2, "staffList", "uint16", "which staff list, on a staff-list assignment"),
    ),
)
"""One marking per 24-byte slot, so a measure carrying two dynamics is one 48-byte
record. `layer` is absent: its best offset is `+8`, which `staffAssign` already
holds at 100%.

**`dcl` is empty because nothing about `^DY` is decoded.** Claiming this layout for
it would assert a 24-byte slot in a record no one has looked at.
"""

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
    TEXT_EXPR_DEF,
    TEXT_EXPR_DEF_DCL,
    MEAS_EXPR_ASSIGN,
)


def _by_tag() -> dict[tuple[str, str], Layout]:
    """Both spellings of every tag, keyed with the pool that disambiguates them.

    A numeric tag and a DCL tag never collide -- one is digits, the other
    letters -- but a tag number is only unique within its pool, so the pool is
    part of the key rather than a thing the caller is trusted to check.
    """
    index: dict[tuple[str, str], Layout] = {}
    for layout in LAYOUTS:
        # Tag 0 is the "DCL only" marker, not a record number: indexing it would
        # claim every tag-less caller.
        numeric = str(layout.tag) if layout.tag else ""
        for spelling in (numeric, layout.dcl):
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
