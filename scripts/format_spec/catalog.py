"""The record catalogue: one entry per decoded record type.

Offsets are those the reader actually uses. Where a record's payload is only
partly decoded, that is stated rather than padded out with guesses -- an
invented offset in a format specification is worse than an admitted gap.
"""

from __future__ import annotations

from finale_file_parser.enigma import mus_others as OTH

from .content import le16, le32
from .hexview import Field, Struct, render_struct


def _pad(data: bytes, size: int) -> bytes:
    return data + bytes(max(0, size - len(data)))


# --------------------------------------------------------------------------


def meas_spec() -> Struct:
    buf = bytearray(12)
    buf[0:2] = le16(0x0258)  # width, EVPU
    buf[2:4] = le16(3)  # keySig.key
    buf[4:6] = le16(4)  # beats
    buf[6:8] = le16(1024)  # divbeat
    buf[10:12] = le16(0x0002)  # flags; low byte carries the barline nibble
    return Struct(
        name="MeasSpec",
        fields=[
            Field(0, 2, "width", "uint16", "measure width in EVPU"),
            Field(2, 2, "key", "uint16", "key signature; 0 means inherit"),
            Field(4, 2, "beats", "uint16", "time signature numerator"),
            Field(6, 2, "divbeat", "uint16", "EDU per beat; 1024 = quarter"),
            Field(10, 2, "flags", "uint16", "low byte holds the barline nibble"),
        ],
        data=bytes(buf),
        caption="measSpec &mdash; one per measure, keyed by measure number. "
        "2011 tag 176; DCL tag <code>^MS</code>.",
        notes=[
            "<strong>A key of 0 means &ldquo;inherit&rdquo;, not C major.</strong> A "
            ".musx omits the element entirely rather than writing zero. Emitting "
            "<code>key=&quot;0&quot;</code> would silently turn every inheriting measure "
            "into C major.",
            "<strong>The barline nibble is the low byte of the u16 at +10, not the byte "
            "at +10.</strong> ETF stores others data as two-byte values, so on a "
            "big-endian file that byte is at +11. Reading +10 either way took the high "
            "byte from all 37 big-endian DCL documents.",
        ],
    )


def frame_spec() -> Struct:
    base = 6
    buf = bytearray(base + 8)
    buf[base : base + 4] = le32(101)
    buf[base + 4 : base + 8] = le32(108)
    return Struct(
        name="FrameSpec",
        fields=[
            Field(0, base, "header", "uint8[]", "era-dependent lead-in"),
            Field(base, 4, "startEntry", "uint32", "first entry number in this frame"),
            Field(base + 4, 4, "endEntry", "uint32", "last entry number, inclusive"),
        ],
        data=bytes(buf),
        caption="frameSpec &mdash; a run of entries forming one layer of one measure. "
        "2011 tag 146; DCL tag <code>^FR</code>.",
        notes=[
            "<strong>The base offset differs by era: 4 for 2001, 6 for 2005.</strong> The "
            "reader distinguishes them by incidence count &mdash; a three-incidence spec "
            "is the 2001 shape. Reading the wrong base yields entry numbers that look "
            "plausible and are wrong, which is the worst kind of error this format offers.",
            "When a spec has more than one incidence, a <code>startTime</code> u32 sits at "
            "+0, in EDU from the start of the measure.",
        ],
    )


def gfhold() -> Struct:
    buf = bytearray(10)
    buf[0:2] = le16(1)  # clefID
    buf[6:8] = le16(41)  # frame1
    buf[8:10] = le16(0)  # frame2, empty
    return Struct(
        name="GfHold",
        fields=[
            Field(0, 2, "clefID", "uint16", "clef in force for this measure"),
            Field(6, 2, "frame1", "uint16", "layer 1 frame id; 0 = layer empty"),
            Field(8, 2, "frame2", "uint16", "layer 2 frame id"),
        ],
        data=bytes(buf),
        caption="gfhold (&ldquo;frame hold&rdquo;) &mdash; keyed by <em>two</em> cmpers, "
        "(staff, measure). 2011 tag 1044; DCL tag <code>^GF</code>. This is the "
        "record that connects a place in the score to its music.",
        notes=[
            "A frame of <strong>0 means the layer is empty</strong> and should be omitted, "
            "matching a .musx, where an absent slot reads as &ldquo;this layer holds "
            "nothing&rdquo;.",
            "The format provides four layer slots. Only the first two are decoded here; "
            "no corpus document was found carrying a third or fourth.",
        ],
    )


def staff_spec() -> Struct:
    buf = bytearray(22)
    buf[20:22] = le16(0xFFF9)
    return Struct(
        name="StaffSpec",
        fields=[
            Field(20, 2, "transposition", "uint16", "written-to-sounding interval"),
        ],
        data=bytes(buf),
        caption="staffSpec &mdash; one per staff, keyed by staff number. 2011 tag 231; "
        "DCL tag <code>^IS</code>. Only the transposition field is decoded.",
        notes=[
            "The staff's <em>name</em> is not here &mdash; it lives in the text pool, "
            "which is why a .mus converts with positional part names unless that pool is "
            "resolved.",
        ],
    )


def tuplet_def() -> Struct:
    buf = bytearray(8)
    buf[0:2] = le16(3)  # symbolicNum
    buf[2:4] = le16(1024)  # symbolicDur
    buf[4:6] = le16(2)  # refNum
    buf[6:8] = le16(1024)  # refDur
    return Struct(
        name="TupletDef",
        fields=[
            Field(0, 2, "symbolicNum", "uint16", "printed count, the 3 of a triplet"),
            Field(2, 2, "symbolicDur", "uint16", "printed unit in EDU"),
            Field(4, 2, "refNum", "uint16", "count these replace"),
            Field(6, 2, "refDur", "uint16", "unit they replace, in EDU"),
        ],
        data=bytes(buf),
        caption="tupletDef &mdash; 2011 tag 1072. The example reads &ldquo;3 quarters in "
        "the time of 2 quarters&rdquo;.",
        notes=[
            "The sounded duration of an entry inside a tuplet is its written duration "
            "scaled by <code>(refNum &times; refDur) / (symbolicNum &times; symbolicDur)</code>.",
        ],
    )


def staff_group() -> Struct:
    buf = bytearray(24)
    buf[0:2] = le16(1)
    buf[2:4] = le16(4)
    buf[10:12] = le16(3)
    buf[21] = 0x01
    return Struct(
        name="StaffGroup",
        fields=[
            Field(0, 2, "startInst", "uint16", "first staff in the group"),
            Field(2, 2, "endInst", "uint16", "last staff, inclusive"),
            Field(10, 2, "bracketId", "uint16", "bracket shape"),
            Field(21, 1, "barlineFlags", "uint8", "bit 0: barlines cross the group"),
        ],
        data=bytes(buf),
        caption="staffGroup &mdash; the braces and brackets down the left edge. 2011 tag 1057.",
    )


def lyric_verse() -> Struct:
    stride = 20
    buf = bytearray(stride)
    buf[0:2] = le16(1)  # number
    buf[2:4] = le16(7)  # syll
    buf[8:10] = le16(0)  # wext
    return Struct(
        name="LyricVerseSlot",
        fields=[
            Field(0, 2, "number", "uint16", "verse number"),
            Field(2, 2, "syll", "uint16", "syllable index into the text pool"),
            Field(8, 2, "wext", "uint16", "non-zero: word extends with a melisma"),
        ],
        data=bytes(buf),
        caption=f"lyricVerse &mdash; 2011 tag 1108. The payload is an array of "
        f"{stride}-byte slots, one per entry that sings.",
    )


def artic_assign() -> Struct:
    buf = bytearray(4)
    buf[0:2] = le16(12)
    return Struct(
        name="ArticAssign",
        fields=[
            Field(0, 2, "definition", "uint16", "key of the articDef this uses"),
        ],
        data=bytes(buf),
        caption="articAssign &mdash; 2011 tag 1009. Points at an articDef (tag 121), "
        "which carries the glyph.",
    )


def inst_used() -> Struct:
    slot = 24
    buf = bytearray(slot * 2)
    buf[0:2] = le16(1)
    buf[slot : slot + 2] = le16(2)
    return Struct(
        name="InstUsedSlot",
        fields=[
            Field(0, 2, "staff", "uint16", "staff number, one per incidence"),
            Field(slot, 2, "staff[1]", "uint16", "the next slot, 24 bytes on"),
        ],
        data=bytes(buf),
        caption=f"instUsed &mdash; 2011 tag 159. A {slot}-byte slot per incidence, giving "
        "the score's staff order. This, not the staff number, is what a part list "
        "should follow.",
    )


CATALOGUE = [
    ("measSpec", OTH.TAG_MEAS_SPEC, "MS", meas_spec),
    ("frameSpec", OTH.TAG_FRAME_SPEC, "FR", frame_spec),
    ("gfhold", 1044, "GF", gfhold),
    ("staffSpec", OTH.TAG_STAFF_SPEC, "IS", staff_spec),
    ("tupletDef", 1072, "", tuplet_def),
    ("staffGroup", 1057, "", staff_group),
    ("lyricVerse", 1108, "", lyric_verse),
    ("articAssign", 1009, "", artic_assign),
    ("instUsed", OTH.TAG_INST_USED, "", inst_used),
]

PARTIAL = [
    ("articDef", 121, "the glyph an articAssign refers to; character offsets 0 and 2"),
    ("repeatBack", 203, "backward repeat barline; target measure"),
    ("repeatEndingStart", 204, "first and second ending brackets"),
    ("repeatPassList", 206, "which passes an ending applies to"),
    ("clefOptions", 109, "the clef definition table, read as a strided array"),
]


def render_catalogue() -> str:
    out: list[str] = []
    for name, tag, etf, fn in CATALOGUE:
        etf_txt = f", DCL <code>^{etf}</code>" if etf else ""
        out.append(f"<h3>{name} <span class=meta>&mdash; tag {tag}{etf_txt}</span></h3>")
        out.append(render_struct(fn(), "little-endian"))
    rows = "".join(
        f"<tr><td><code>{n}</code></td><td>{t}</td><td>{d}</td></tr>" for n, t, d in PARTIAL
    )
    out.append(
        "<h3>Recognised but only partly decoded</h3>"
        "<p>These records are read and their keys resolved, but their payload layouts are "
        "not fully established. They are listed so an implementer knows they exist rather "
        "than meeting them as unexplained bytes.</p>"
        "<table><thead><tr><th>Record</th><th>Tag</th><th>What it carries</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    return "".join(out)
