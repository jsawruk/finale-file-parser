"""The record catalog: one entry per decoded record type.

Offsets are not written here. Every layout below comes from
`finale_file_parser.formats.layouts`, which is what the parser and the
inspector read too, so this document cannot state an offset the code does not
use. What lives here is the document's own: example bytes and the prose that
explains them.

Where a record's payload is only partly decoded, that is stated rather than
padded out with guesses -- an invented offset in a format specification is
worse than an admitted gap.
"""

from __future__ import annotations

from finale_file_parser.formats import layouts as LAY
from finale_file_parser.formats import tags as TAGS

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
    return Struct.of(
        LAY.MEAS_SPEC,
        data=bytes(buf),
        caption="measSpec &mdash; one per measure, keyed by measure number. "
        "2011 tag 176; DCL tag <code>^MS</code>.",
        notes=[
            "<strong>A key of 0 is C major.</strong> The field packs a mode in its high "
            "byte (0 major, 1 minor) and a signed count of sharps or flats in its low "
            "byte, so 0 is major with no accidentals. A <code>.musx</code> expresses the "
            "same thing by <em>omitting</em> its key element: across 401 documents and "
            "19,644 key elements, not one is written as zero.",
            "<strong>Absence is not inheritance.</strong> A missing element reads "
            "naturally as &ldquo;same as the measure before&rdquo;, and it is not. One "
            "corpus document runs key=1 for measures 1&ndash;32, no element for "
            "33&ndash;52, then key=1 again from 53. Opened in Finale, measure 33 begins a "
            "new song with a natural cancelling the sharp and chords of C, G7 and F. It is "
            "a key change to C major, not a continuation of G.",
            "<strong>The corpus alone cannot settle this</strong>, which is worth knowing "
            "before trying. The obvious test is to look for accidentals: music in C stored "
            "under an inherited G would need a flat on every F. But <em>no absent-key run "
            "anywhere in the corpus contains a single accidental</em> &mdash; every one is "
            "purely diatonic, so both readings fit the notes equally well. What decided it "
            "was rendering the page.",
            "<strong>What a reader must not do</strong> is carry the previous key forward "
            "across a measure that states none. That silently keeps a piece in the key it "
            "started in through every passage returning to C. This project made exactly "
            "that mistake: 18 passages, 741 measures and 11,421 entries were spelled a "
            "step sharp, and every test passed either way.",
            "The barline style is the <strong>high nibble</strong> of that byte, whose "
            "low bits carry the repeat flags. Observed values: <strong>1</strong> an "
            "ordinary barline and <strong>2</strong> a double bar, agreeing with the "
            "paired <code>.musx</code> on 3,960 ordinary measures and all 11 double bars. "
            "<strong>3</strong> would be the obvious reading for a final barline and does "
            "not occur once in 4,427 measures across 99 documents, so either no file here "
            "ends with one or it is stored elsewhere; the corpus cannot say which.",
        ],
    )


def frame_spec() -> Struct:
    # Two slots, the shape 15 corpus records take: a startTime slot, then the
    # entry pair in the last one. The single-slot shape the other 10,275 take is
    # the second half of this on its own.
    slot = LAY.FRAME_SLOT
    buf = bytearray(slot * 2)
    buf[0:4] = le32(3584)  # startTime, EDU from the start of the measure
    buf[8:12] = le32(8)  # constant in all 15 records carrying a leading slot
    buf[slot : slot + 4] = le32(101)  # startEntry
    buf[slot + 4 : slot + 8] = le32(108)  # endEntry
    return Struct.of(
        LAY.FRAME_SPEC,
        data=bytes(buf),
        extra=[
            Field(slot, 4, "startEntry", "uint32", "first entry number in this frame"),
            Field(slot + 4, 4, "endEntry", "uint32", "last entry number, inclusive"),
        ],
        caption=f"frameSpec &mdash; a run of entries forming one layer of one measure. "
        f"2011 tag 146; DCL tag <code>^FR</code>. The payload is an array of "
        f"{slot}-byte slots; the example shows two.",
        notes=[
            "<strong>The entry pair is in the LAST slot, at +0 and +4.</strong> A reader "
            "takes it from <code>(incidences &minus; 1) &times; 12</code>. Where it sits "
            "therefore depends on the individual record's length, and not on the era.",
            "<strong>Measured, because this document previously said otherwise.</strong> "
            "Across 10,290 frameSpec records in paired documents, every candidate offset "
            "was compared against the <code>startEntry</code>/<code>endEntry</code> the "
            "paired <code>.musx</code> states. The pair matched at the last slot in all "
            "10,290 and at +6 in none. Two shapes occur &mdash; 12-byte single-slot "
            "(10,275) and 24-byte two-slot (15) &mdash; and the 2001&ndash;2005 cohort "
            "carries exactly the same two, 4,571 and 27, so the offset does not vary by "
            "era either.",
            "<strong>What this entry used to say, and why it was wrong.</strong> It drew a "
            "6-byte lead-in with <code>startEntry</code> at +6, and annotated it &ldquo;the "
            "base offset differs by era: 4 for 2001, 6 for 2005&rdquo;. Those two numbers "
            "are real and belong to <code>gfhold</code>, whose frame slots do sit at an era "
            "base &mdash; they had been attached to the wrong record. Nothing supported "
            "them here: the vendored ETF documentation does not describe this record at "
            "all. A specification stating an offset its own parser does not use is the "
            "failure this project moved its layouts into the library to prevent.",
            "When a spec has more than one slot, the leading one carries a "
            "<code>startTime</code> u32 at +0, in EDU from the start of the measure. Its "
            "remaining bytes are not decoded: +4 is zero and +8 holds a constant 8 in all "
            "15 records, too few to read anything into.",
            "The last slot's own +8 is zero in all 10,465 corpus records.",
        ],
    )


def gfhold() -> Struct:
    buf = bytearray(10)
    buf[0:2] = le16(1)  # clefID
    buf[6:8] = le16(41)  # frame1
    buf[8:10] = le16(0)  # frame2, empty
    return Struct.of(
        LAY.GF_HOLD,
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
    return Struct.of(
        LAY.STAFF_SPEC,
        data=bytes(buf),
        caption="staffSpec &mdash; one per staff, keyed by staff number. 2011 tag 231; "
        "DCL tag <code>^IS</code>. Only the transposition field is decoded.",
        notes=[
            "<strong>Transposition is the written-to-sounding interval</strong>, as a "
            "diatonic step count: a B-flat clarinet sounds a step below what is written, a "
            "horn in F a fifth below. It is applied on top of the harmonic value a note "
            "already carries, which is why a transposing part and a concert-pitch part "
            "store the same numbers.",
            "<strong>The octave is not in this field, and not anywhere else.</strong> "
            "Searching every byte of every staffSpec across the paired documents found no "
            "byte that separates staves transposing by an octave from staves transposing "
            "by the same interval within one. Finale does not need it stored: the "
            "instrument itself fixes the octave, and a reader without an instrument table "
            "must supply that knowledge from outside the file.",
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
    return Struct.of(
        LAY.TUPLET_DEF,
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
    return Struct.of(
        LAY.STAFF_GROUP,
        data=bytes(buf),
        caption="staffGroup &mdash; the braces and brackets down the left edge. 2011 tag 1057.",
    )


def lyric_verse() -> Struct:
    stride = LAY.LYRIC_VERSE.stride
    buf = bytearray(stride)
    buf[0:2] = le16(1)  # number
    buf[2:4] = le16(7)  # syll
    buf[8:10] = le16(0)  # wext
    return Struct.of(
        LAY.LYRIC_VERSE,
        data=bytes(buf),
        caption=f"lyricVerse &mdash; 2011 tag 1108. The payload is an array of "
        f"{stride}-byte slots, one per entry that sings.",
    )


def artic_assign() -> Struct:
    buf = bytearray(4)
    buf[0:2] = le16(12)
    return Struct.of(
        LAY.ARTIC_ASSIGN,
        data=bytes(buf),
        caption="articAssign &mdash; 2011 tag 1009. Points at an articDef (tag 121), "
        "which carries the glyph.",
    )


def text_expr_def() -> Struct:
    """The 2011 spelling. Every field confirmed against the 97 paired documents."""
    desc = b"mezzo forte (Vel. 80)\x00"
    buf = bytearray(LAY.TEXT_EXPR_DEF.fields[-1].offset)
    buf[0:2] = le16(19)  # textIDKey
    buf[4:6] = le16(80)  # value -- the velocity the marking plays at
    buf[8:10] = le16(0)  # playPass
    buf[12:14] = le16(13)  # horzMeasExprAlign: leftOfPrimaryNotehead
    buf[24:26] = le16(9)  # vertMeasExprAlign: belowStaffOrEntry
    buf[30:32] = le16(16)  # yAdjustBaseline
    return Struct.of(
        LAY.TEXT_EXPR_DEF,
        data=bytes(buf) + desc,
        caption="textExprDef &mdash; 2011 tag 241. One expression definition: what it "
        "plays back as, where it sits, and the marking in words. The description is a "
        "<strong>variable-length tail</strong> &mdash; it runs from <code>0x24</code> to "
        "the end of the payload, which is 48, 60 or 72 bytes depending on the record, so "
        "the field table gives its size as <code>var</code> rather than a number.",
    )


def text_expr_def_dcl() -> Struct:
    """The DCL era's `DT`, which is deliberately a *smaller* layout, not the same one."""
    desc = b"Below Staff (Vel. 62)\x00"
    buf = bytearray(LAY.TEXT_EXPR_DEF_DCL.fields[-1].offset)
    buf[0:2] = le16(11)  # counter
    buf[4:6] = le16(62)  # value -- stated in words by the description beside it
    return Struct.of(
        LAY.TEXT_EXPR_DEF_DCL,
        data=bytes(buf) + desc,
        caption="textExprDef, DCL era &mdash; ETF <code>^DT</code>. Three fields, not the "
        "nine above, and that is the point: only <code>+4</code> and the description "
        "carry across the eras. No offset in a <code>DT</code> payload separates the "
        "&ldquo;Below Staff&rdquo; descriptions from the rest, so the alignment enums are "
        "not evidenced here and are not claimed. <code>+4</code> is confirmed without any "
        "paired document at all: the description states the velocity in words, and it "
        "equals the <code>uint16</code> at <code>+4</code> in 434 records of 434. Read it "
        "in the document's own byte order &mdash; 37 corpus documents are big-endian, "
        "where a little-endian reading turns 127 into 32,512.",
    )


def meas_expr_assign() -> Struct:
    slot = LAY.MEAS_EXPR_ASSIGN.stride
    buf = bytearray(slot)
    buf[0:2] = le16(6)  # textExprID
    buf[4:6] = le16(24)  # horzEvpuOff
    buf[6:8] = le16(0xFFB8 & 0xFFFF)  # vertOff, -72
    buf[8:10] = le16(3)  # staffAssign
    return Struct.of(
        LAY.MEAS_EXPR_ASSIGN,
        data=bytes(buf),
        caption=f"measExprAssign &mdash; 2011 tag 177. Where a definition is actually "
        f"placed. One marking per {slot}-byte slot, so a measure carrying two dynamics is "
        f"one {slot * 2}-byte record &mdash; read every slot, not just the first. "
        "<code>staffAssign</code> of &minus;1 means a staff list rather than one staff. "
        "No DCL tag is claimed for this record: the era's <code>^DY</code> is undecoded, "
        f"and claiming this layout for it would assert a {slot}-byte slot nobody has "
        "looked at.",
    )


def inst_used() -> Struct:
    slot = LAY.INST_USED.stride
    buf = bytearray(slot * 2)
    buf[0:2] = le16(1)
    buf[slot : slot + 2] = le16(2)
    return Struct.of(
        LAY.INST_USED,
        data=bytes(buf),
        # A second slot, shown so the stride is visible. The layout describes one
        # slot; how many follow is a property of the record, not of the struct.
        extra=[Field(slot, 2, "staff[1]", "uint16", f"the next slot, {slot} bytes on")],
        caption=f"instUsed &mdash; 2011 tag 159. A {slot}-byte slot per incidence, giving "
        "the score's staff order. This, not the staff number, is what a part list "
        "should follow.",
    )


# Each entry pairs a layout with the function that gives it example bytes and
# prose. The record's name and tags are read off the layout, so this document
# and the parser name a record the same way or not at all.
CATALOG = [
    (LAY.MEAS_SPEC, meas_spec),
    (LAY.FRAME_SPEC, frame_spec),
    (LAY.GF_HOLD, gfhold),
    (LAY.STAFF_SPEC, staff_spec),
    (LAY.TUPLET_DEF, tuplet_def),
    (LAY.STAFF_GROUP, staff_group),
    (LAY.LYRIC_VERSE, lyric_verse),
    (LAY.ARTIC_ASSIGN, artic_assign),
    (LAY.INST_USED, inst_used),
    (LAY.TEXT_EXPR_DEF, text_expr_def),
    (LAY.TEXT_EXPR_DEF_DCL, text_expr_def_dcl),
    (LAY.MEAS_EXPR_ASSIGN, meas_expr_assign),
]


PARTIAL = [
    ("articDef", 121, "the glyph an articAssign refers to; character offsets 0 and 2"),
    ("repeatBack", 203, "backward repeat barline; target measure"),
    ("repeatEndingStart", 204, "first and second ending brackets"),
    ("repeatPassList", 206, "which passes an ending applies to"),
    ("clefOptions", 109, "the clef definition table, read as a strided array"),
]


def _tag_line(layout: LAY.Layout) -> str:
    """How a record's identity reads under its heading.

    A layout with `tag == 0` describes only the DCL spelling -- 0 is the
    "no 2011 number" marker, not a record number -- so writing "tag 0" would
    invent a record that does not exist.
    """
    etf_txt = f"DCL <code>^{layout.dcl}</code>" if layout.dcl else ""
    numeric = f"tag {layout.tag}" if layout.tag else ""
    return ", ".join(part for part in (numeric, etf_txt) if part)


def render_catalog() -> str:
    out: list[str] = []
    for layout, fn in CATALOG:
        out.append(f"<h3>{layout.record} <span class=meta>&mdash; {_tag_line(layout)}</span></h3>")
        out.append(render_struct(fn()))
    rows = "".join(
        f"<tr><td><code>{n}</code></td><td>{t}</td><td>{d}</td></tr>" for n, t, d in PARTIAL
    )
    out.append(
        "<h3>Recognized but only partly decoded</h3>"
        "<p>These records are read and their keys resolved, but their payload layouts are "
        "not fully established. They are listed so an implementer knows they exist rather "
        "than meeting them as unexplained bytes.</p>"
        "<table><thead><tr><th>Record</th><th>Tag</th><th>What it carries</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    return "".join(out)


# --------------------------------------------------------------------------
# The tag census. Three tiers, kept apart deliberately: conflating a
# payload-confirmed identification with a key-sequence guess is how a lead
# becomes a "fact" in someone else's document.
# --------------------------------------------------------------------------

UNKNOWN: list[tuple[str, str, str, str]] = [
    ("213", "2011", "others", "25,576"),
    ("215", "2011", "others", "25,576"),
    ("140", "2011", "others", "18,624"),
    ("214", "2011", "others", "12,681"),
    ("125", "2011", "others", "12,612"),
    ("148", "2011", "others", "11,887"),
    ("126", "2011", "others", "11,208"),
    ("183", "2011", "others", "10,114"),
    ("192", "2011", "others", "7,353"),
    ("241", "2011", "others", "7,353"),
    ("217", "2011", "others", "6,638"),
    ("1043", "2011", "details", "166,524"),
    ("1064", "2011", "details", "8,162"),
    ("1063", "2011", "details", "2,162"),
    ("1066", "2011", "details", "1,483"),
    ("1034", "2011", "details", "1,164"),
    ("1060", "2011", "details", "1,156"),
    ("^fb", "DCL", "details", "63,324"),
    ("^BC", "DCL", "others", "3,809"),
    ("^DA", "DCL", "others", "2,963"),
    ("^OC", "DCL", "others", "2,170"),
    ("^ls", "DCL", "others", "1,809"),
]


def render_unknown() -> str:
    rows = "".join(
        f"<tr><td><code>{tag}</code></td><td>{era}</td><td>{pool}</td><td class=sz>{n}</td></tr>"
        for tag, era, pool, n in UNKNOWN
    )
    return (
        "<table><thead><tr><th>Tag</th><th>Era</th><th>Pool</th>"
        f"<th>Records</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def render_tag_tables() -> str:
    # The `entry` record has no numeric tag: it is not in the numbered pools.
    a = "".join(
        f"<tr><td><code>{e.name}</code></td>"
        f"<td class=off>{e.tag if e.tag.isdigit() else '&mdash;'}</td>"
        f"<td><code>{'^' + (e.etf or e.tag) if not e.tag.isdigit() or e.etf else ''}</code></td>"
        f"<td>{e.pool}</td><td>{e.description}</td></tr>"
        for e in TAGS.TAG_NAMES
        if e.tier == TAGS.DECODED
    )
    b = "".join(
        f"<tr><td class=off>{e.tag}</td><td><code>{e.name}</code></td>"
        f"<td class=sz>{e.documents}</td></tr>"
        for e in TAGS.TAG_NAMES
        if e.tier == TAGS.MATCHED
    )
    return f"""
<h3>Known record tags</h3>
<p>One vocabulary in three spellings: ETF's two-character tags, the 2011 era's
numbers, and EnigmaXML's symbolic names.</p>

<h4>Tier A &mdash; decoded and payload-confirmed</h4>
<p>Parsed by this project, with fields verified against paired <code>.musx</code>
documents.</p>
<table><thead><tr><th>Name</th><th>Tag</th><th>ETF</th><th>Pool</th>
<th>Description</th></tr></thead><tbody>{a}</tbody></table>

{render_etf_tags()}

<h4>Tier B &mdash; numeric tags named by key-sequence matching only</h4>
<p>These names come from a different method, and it is worth being precise
about what it does and does not establish.</p>

<p>A <code>.musx</code> and a 2011 <code>.mus</code> of the same music contain
the same records. Reading the <code>.musx</code>, whose records are named,
gives the sequence of <code>(cmper, part)</code> keys belonging to each name.
Reading the <code>.mus</code> gives the same sequences against numeric tags.
Where a numeric tag's key sequence matches a name's exactly, across many
documents, the two are almost certainly the same record type. The
&ldquo;Docs&rdquo; column is how many paired documents agreed.</p>

<p><strong>What limits it is that a key sequence is not unique.</strong> Many
record types are keyed one per measure, or one per staff, and any two of those
produce identical sequences in a document. The match then says only &ldquo;this
tag has the same shape as that name&rdquo;, and two tags of the same shape can
be swapped without the evidence noticing. No conflicts were observed &mdash; no
tag matched two names, and no name matched two tags &mdash; but that is what
would be expected either way, since a swap between two same-shaped tags is
invisible to a test that only compares shapes.</p>

<p>So eighty documents agreeing that tag 124 has
<code>channelPlayData</code>'s key sequence is strong evidence that tag 124 is
<em>some</em> record keyed the way <code>channelPlayData</code> is keyed. It is
not evidence about the meaning of its bytes, which is what confirming a record
type requires. That is why Tier A, whose payload fields were read and checked
against a paired document, is a different kind of claim.</p>
<table><thead><tr><th>Tag</th><th>Name</th><th>Docs</th></tr></thead>
<tbody>{b}</tbody></table>
<div class=warn><code>fontName</code> (5 documents) and <code>shapeExprDef</code>
(10) rest on so few agreements that they are better read as guesses.</div>

<h4>Tier C &mdash; observed but unidentified</h4>
<p><strong>189 distinct tags appear in the 2011 <code>others</code> pool alone</strong>,
of which the tiers above account for roughly thirty. The rest are read, keyed and
carried, but their meaning is unknown. The most frequent, by record count across
the corpus:</p>
<div class="note review">{REVIEW_BADGE}<strong>Removed from this table:</strong>
<code>^DN</code> is now decoded as the percussion input-note name, and
<code>^fg</code> is identified by its chord-shape text. Their former Tier-C rows
were stale, so the deletion is called out here where absent rows cannot carry a
highlight of their own.</div>
{render_unknown()}
<div class=note><strong>Two hints from the counts.</strong> Several pairs share an
exact record count &mdash; 213/215, 192/241, and <code>sL</code>/<code>sb</code>
&mdash; which across a whole corpus usually means a definition-and-assignment
couple like <code>articDef</code>/<code>articAssign</code>. And details tag 1043,
at 166,524 records, is roughly sixteen times more common than
<code>gfhold</code>, which suggests something per entry or per note rather than
per measure.</div>

<div class=prov><strong>What this document covers.</strong> The tags named here
are the ones on the path from a file to its notes, which is where the work
started; they are not the most common ones.

<p>Counting distinct tags observed across the corpus:
<strong>34 of the 227</strong> numeric tags the 2011 era uses, and
<strong>34 of the 265</strong> ETF tags the 2001&ndash;2005 era uses. Together
<strong>68 of 492</strong>, about one in seven. What the remaining tags hold is
not known.</p></div>
"""


# --------------------------------------------------------------------------
# ETF tags named by Coda's own documentation. These are a stronger claim than
# the key-sequence matches below: the vendor named them.
# --------------------------------------------------------------------------

_SOURCE = {
    "spec": "ETF&nbsp;spec",
    "lily": "LilyPond",
    "cahill": "Cahill",
    "measured": "measured",
}

REVIEW_BADGE = "<span class=reviewbadge>CHANGED</span>"
"""Temporary marker for text changed since the previous PDF review."""


def _labelled_rows() -> str:
    """Tags named by the text in their own payloads."""
    return "".join(
        f"<tr class=review><td>{REVIEW_BADGE}<code>^{e.tag}</code></td><td>{e.name}</td>"
        f"<td>{e.description}</td><td class=sz>{e.documents}</td></tr>"
        for e in TAGS.TAG_NAMES
        if e.tier == TAGS.LABELLED
    )


def _etf_rows(pool: str) -> str:
    """The documented ETF tags of one pool, in catalogue order."""
    rows: list[str] = []
    for entry in TAGS.TAG_NAMES:
        if entry.tier != TAGS.DOCUMENTED or entry.pool != pool or not entry.source:
            continue
        changed = entry.tag == "DF"
        css = " class=review" if changed else ""
        badge = REVIEW_BADGE if changed else ""
        rows.append(
            f"<tr{css}><td>{badge}<code>^{entry.tag}</code></td><td>{entry.name}</td>"
            f"<td>{entry.description}</td><td class=sz>{_SOURCE[entry.source]}</td></tr>"
        )
    return "".join(rows)


def render_etf_tags() -> str:
    return f"""
<h4>Named ETF tags</h4>
<p>The 2001&ndash;2005 era uses ETF's two-character tags, and Coda documented
many of them. The source column says which document named each one.</p>

<div class=prov>In this table, <strong>ETF spec</strong> is Coda's <em>Enigma
Transportable File Specification</em> (reference 1); <strong>LilyPond</strong>
is the LilyPond project's ETF format notes (reference 8); and
<strong>Cahill</strong> is Cahill's thesis on Enigma and CPNView (reference 9).
No LilyPond source code was read or used.</div>

<div class=note><strong>Tag names are case sensitive.</strong> <code>^AC</code> is Tempo
and <code>^ac</code> is performance data; <code>^CH</code> is a chord and
<code>^hC</code> a learned one; <code>^FB</code> is the fretboard library while
<code>^fb</code> is an unrelated record with a different partner.</div>

<h4>others</h4>
<table><thead><tr><th>Tag</th><th>Name</th><th>Key (cmper)</th>
<th>Source</th></tr></thead><tbody>{_etf_rows("others")}</tbody></table>

<h4>details</h4>
<table><thead><tr><th>Tag</th><th>Name</th><th>Keys</th>
<th>Source</th></tr></thead><tbody>{_etf_rows("details")}</tbody></table>

<h4>entry details</h4>
<p>Keyed by an entry number rather than by position &mdash; the two cmpers hold
the high and low words of the entry number.</p>
<table><thead><tr><th>Tag</th><th>Name</th><th>Carries</th>
<th>Source</th></tr></thead><tbody>{_etf_rows("entries")}</tbody></table>

<h4>Tags that name themselves</h4>
<p>A record whose payload contains readable text often says what it is for. No
pairing and no inference is involved &mdash; the words are in the file, and the
only judgement is reading them. This is stronger evidence than the key-sequence
matching of Tier&nbsp;B, and it establishes what a record <em>holds</em> while
saying nothing about where its fields sit.</p>

<p class=review>{REVIEW_BADGE}
It matters most for the 2001&ndash;2005 era, which has <strong>no paired
<code>.musx</code> anywhere in this corpus</strong>, so the method that earned
Tier&nbsp;A elsewhere is unavailable. Counts are documents carrying the tag
across all 139 DCL files. An earlier census reported only 38 because it matched
lowercase <code>.mus</code> and silently omitted 101 uppercase
<code>.MUS</code> paths.</p>
<table><thead><tr><th>Tag</th><th>Holds</th><th>Text found in the payload</th>
<th>Docs</th></tr></thead><tbody>{_labelled_rows()}</tbody></table>

<div class="note review">{REVIEW_BADGE}<strong><code>^RT</code> corrects a claim this project
published.</strong> The reader's own list of gaps stated that the corpus offered
no evidence at all for identifying the text-repeat tag &mdash; &ldquo;not a
little, none&rdquo;. It had reasoned entirely about paired documents, found the
candidates were mispairings, and concluded the corpus was silent. The DCL cohort
was never searched, and 1,253 <code>^RT</code> records across 137 of its
documents carry the text verbatim. What remains missing is narrower: the
assignment attaching a repeat to a measure, and the action telling a player
where to go.</div>

<div class=note><strong><code>^FB</code> and <code>^GT</code> were identified by
structure, not by a document.</strong> Neither appears in any source consulted.
They were matched because <code>FB</code> holds <strong>exactly 192 records in
every document that has it</strong>, keyed contiguously 1&ndash;192 &mdash; a
fixed table rather than per-score data &mdash; and EnigmaXML's
<code>fretboardSymbol</code> holds exactly 192 in every document too. An
invariant of that kind survives the two corpora being different sizes and
different repertoire, which ordinary frequency comparisons do not.

<p><code>GT</code> is its index: twelve records keyed 60&ndash;71, the chromatic
pitch classes from middle C, with sixteen incidences each. Twelve roots times
sixteen shapes is 192. <code>FB</code> and <code>GT</code> appear in exactly the
same 44 of 139 documents and in no others, and nothing else shares that set.</p>

<p>The fretboard library is written only when the feature is used: 44 of 139
DCL documents
carry it, against 149 of 150 <code>.musx</code> documents, later versions
shipping the defaults regardless.</p></div>

<div class="note review">{REVIEW_BADGE}<strong><code>^DL</code>, <code>^DF</code> and
<code>^DN</code> form the DCL percussion-map palette.</strong>
<code>^DL(map)</code> names the map. <code>^DF(map,input)</code> is one
10-byte appearance row, and <code>^DN(map,input)</code> names that same input.
All 18,647 <code>^DN</code> records have an exact <code>^DF</code> partner;
the typed reader is <code>enigma.dcl_percussion_maps</code>.

<p>The second key is an <em>input</em> note, not the playback MIDI note this
document previously called it. The first payload word is playback MIDI and the
second is staff position. The distinction is visible 3,717 times among the
18,647 named entries. For example, &ldquo;Hi-Hat Foot&rdquo; in the bass-clef
entry map is input 41 but playback 44; its treble-clef sibling is input 62 and
playback 44, while both store staff position 1. A field that changes with the
entry clef cannot be the playback note.</p>

<p>The final three words are preserved as two raw notehead values and one raw
trailing value. Their order and meaning are not named: neither the ETF
specification nor Cahill's thesis documents this record, and the unpaired
corpora do not justify transferring the four-notehead EnigmaXML layout onto
two DCL fields.</p>

<p>Names follow the platform encoding. Every one of the 37 big-endian DCL files
is Mac-origin and uses Mac Roman; every one of the 102 little-endian files is
Windows-origin and uses CP1252.</p>

<p>This is still a palette, not score usage: the DCL record selecting a map for
a staff is not decoded. Across the full cohort there are 1,282 maps, 74,730
<code>^DF</code> rows, and 18,647 named rows.</p></div>

<div class=warn><strong>Not every DCL tag is two printable characters.</strong>
Alongside the character tags, the details pool holds thirty
<strong>numeric</strong> tags in three regular runs &mdash;
<code>0x8001</code>&ndash;<code>0x800a</code>,
<code>0x9001</code>&ndash;<code>0x900a</code> and
<code>0xa001</code>&ndash;<code>0xa00a</code> &mdash; each appearing about once
per document in all 139 DCL documents, and in both byte orders. Their meaning is
not established here; what matters for an implementer is that the field is a
u16, and only sometimes a pair of letters.</div>



<div class=warn><strong>A variant described in a third-party document and not
observed.</strong> The LilyPond format notes describe a second form of
<code>^GF</code> occupying a single row, laid out <code>frame, clef, ...</code>
rather than <code>clef, flags, frames</code>. A reader assuming the two-row form
would take a frame id for a clef.

<p>Measured across all 139 DCL corpus documents: every one of the 14,191
<code>GF</code> records has exactly two incidences and a 20-byte payload. The
single-row form occurs in none of them.</p>

<p>Two readings fit. The variant may be real and simply absent from this corpus,
in which case it is a gap. Or the note may be mistaken: it is one person's
reverse-engineering write-up rather than vendor documentation, and being written
down does not make it correct. It is recorded so a reader meeting such a file
knows the possibility exists, not as an established part of the format.</p></div>


"""


NOTE_FLAGS: list[tuple[str, str, str]] = [
    ("0x80000000", "SETBIT", "legality; set on every real note"),
    ("0x40000000", "TSBIT", "tie start"),
    ("0x20000000", "TEBIT", "tie end"),
    ("0x10000000", "CROSSBIT", "cross-staff: the note is drawn on another staff"),
    ("0x08000000", "UPSECBIT", "upstem second"),
    ("0x04000000", "DWSECBIT", "downstem second"),
    ("0x02000000", "UPSPBIT", "on the upper stem, where stems are split"),
    ("0x01000000", "ACCIBIT", "show an accidental; recomputed while editing unless frozen"),
    ("0x00800000", "PARENACCI", "parenthesize that accidental"),
    ("0x001F0000", "TGFNID", "mask: the note's id, 1&ndash;12, within its entry"),
    ("0x00000002", "FREEZEACCI", "freeze the accidental bit in place"),
]

DURATIONS: list[tuple[int, str, int]] = [
    (8192, "breve", 47),
    (6144, "dotted whole", 17),
    (4096, "whole", 1043),
    (3584, "double-dotted half", 3),
    (3072, "dotted half", 977),
    (2048, "half", 5266),
    (1792, "double-dotted quarter", 14),
    (1536, "dotted quarter", 2318),
    (1024, "quarter", 34960),
    (768, "dotted eighth", 2121),
    (512, "eighth", 38046),
    (384, "dotted 16th", 89),
    (256, "16th", 22651),
    (192, "dotted 32nd", 6),
    (128, "32nd", 874),
    (64, "64th", 34),
]


def render_note_flags() -> str:
    rows = "".join(
        f"<tr><td><code>{h}</code></td><td><code>{n}</code></td><td>{d}</td></tr>"
        for h, n, d in NOTE_FLAGS
    )
    return (
        "<table><thead><tr><th>Bit</th><th>Coda's name</th><th>Meaning</th></tr>"
        f"</thead><tbody>{rows}</tbody></table>"
    )


def render_durations() -> str:
    rows = "".join(
        f"<tr><td class=off>{e:,}</td><td>{n}</td><td class=sz>{c:,}</td></tr>"
        for e, n, c in DURATIONS
    )
    return (
        "<table><thead><tr><th>EDU</th><th>Note value</th><th>Count</th></tr>"
        f"</thead><tbody>{rows}</tbody></table>"
    )
