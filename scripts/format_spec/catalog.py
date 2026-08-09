"""The record catalog: one entry per decoded record type.

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


CATALOG = [
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


def render_catalog() -> str:
    out: list[str] = []
    for name, tag, etf, fn in CATALOG:
        etf_txt = f", DCL <code>^{etf}</code>" if etf else ""
        out.append(f"<h3>{name} <span class=meta>&mdash; tag {tag}{etf_txt}</span></h3>")
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

TIER_A: list[tuple[str, str, str, str, str]] = [
    ("109", "", "clefOptions", "others", "Clef definition table, read as a strided array"),
    ("121", "", "articDef", "others", "An articulation's definition; charMain is the glyph"),
    ("146", "^FR", "frameSpec", "others", "Entry range for one layer of one measure"),
    ("159", "", "instUsed", "others", "The staves the score lays out, in layout order"),
    ("176", "^MS", "measSpec", "others", "Per measure: width, key, beats, divbeat, barline"),
    ("203", "", "repeatBack", "others", "Backward repeat barline, keyed by measure"),
    ("204", "", "repeatEndingStart", "others", "Ending bracket, keyed by measure"),
    ("206", "", "repeatPassList", "others", "Which passes an ending is taken on"),
    ("231", "^IS", "staffSpec", "others", "Per staff; transposition at +0x14"),
    ("1009", "", "articAssign", "details", "The articulation on an entry; names an articDef"),
    ("1044", "^GF", "gfhold", "details", "(staff, measure) to clef and up to four frames"),
    ("1057", "", "staffGroup", "details", "Brace or bracket over a run of staves"),
    ("1072", "", "tupletDef", "details", "Keyed by entry, not by (staff, measure)"),
    ("1108", "", "lyrDataVerse", "details", "Verse lyrics"),
    ("&mdash;", "^eE", "entry", "entries", "The notes; fixed 38-byte slots"),
]

TIER_B: list[tuple[str, str, str]] = [
    ("124", "channelPlayData", "80"),
    ("126", "chordSuffixPlay", "85"),
    ("131", "drumLibName", "86"),
    ("134", "durAllot", "91"),
    ("136", "execShape", "85"),
    ("140", "fretboardSymbol", "91"),
    ("144", "fontName", "5"),
    ("147", "lockMeas", "81"),
    ("149", "fretInst", "90"),
    ("163", "layerAtts", "85"),
    ("165", "metaArtic", "80"),
    ("168", "metaDynam", "81"),
    ("169", "metaKeySig", "80"),
    ("170", "metaRepeat", "81"),
    ("171", "metaShape", "80"),
    ("172", "metaStaffStyle", "80"),
    ("173", "metaTimeSig", "81"),
    ("235", "shapeExprDef", "10"),
    ("242", "textExpressionEnclosure", "14"),
    ("315", "volumeValue", "14"),
]

TIER_C_OTHERS = "213 and 215 (25,576 each), 140 (18,624), 214 (12,681), 125 (12,612), \
148 (11,887), 126 (11,208), 183 (10,114), 192 and 241 (7,353 each), 217 (6,638)"
TIER_C_DETAILS = "1043 (166,524), 1064 (8,162), 1063 (2,162), 1066 (1,483), \
1034 (1,164), 1060 (1,156)"
TIER_C_ETF = "<code>BC</code> (3,809), \
<code>DA</code> (2,963), <code>fg</code> (2,884), <code>OC</code> (2,170), \
<code>ls</code> (1,809), and the <code>&amp;a</code>/<code>&amp;d</code>/\
<code>&amp;f</code> family; in details <code>DF</code> (74,730), \
<code>fb</code> (63,324) and <code>DN</code> (18,647) &mdash; the two most \
common records in a DCL document are among them"


def render_tag_tables() -> str:
    a = "".join(
        f"<tr><td class=off>{t}</td><td><code>{e}</code></td><td><code>{n}</code></td>"
        f"<td>{p}</td><td>{d}</td></tr>"
        for t, e, n, p, d in TIER_A
    )
    b = "".join(
        f"<tr><td class=off>{t}</td><td><code>{n}</code></td><td class=sz>{c}</td></tr>"
        for t, n, c in TIER_B
    )
    return f"""
<h3>Known record tags</h3>
<p>One vocabulary in three spellings: ETF's two-character tags, the 2011 era's
numbers, and EnigmaXML's symbolic names. The three tiers below are kept apart on
purpose &mdash; a payload-confirmed identification and a key-sequence guess are
not the same claim.</p>

<h4>Tier A &mdash; decoded and payload-confirmed</h4>
<p>Parsed by this project, with fields verified against paired <code>.musx</code>
documents.</p>
<table><thead><tr><th>Tag</th><th>ETF</th><th>Name</th><th>Pool</th>
<th>Description</th></tr></thead><tbody>{a}</tbody></table>

{render_etf_tags()}

<h4>Tier B &mdash; numeric tags named by key-sequence matching only</h4>
<p>Identified by matching each tag's <code>(cmper, part)</code> sequence against
the <code>.musx</code> <code>others</code> pool. <strong>Treat these as leads,
not facts</strong>: a tag whose record count collides with another's could be
mismatched, and none has been confirmed by payload content. &ldquo;Docs&rdquo; is
how many corpus documents agreed.</p>
<table><thead><tr><th>Tag</th><th>Name</th><th>Docs</th></tr></thead>
<tbody>{b}</tbody></table>
<div class=warn><code>fontName</code> (5 documents) and <code>shapeExprDef</code>
(10) rest on so few agreements that they are better read as guesses.</div>

<h4>Tier C &mdash; observed but unidentified</h4>
<p><strong>189 distinct tags appear in the 2011 <code>others</code> pool alone</strong>,
of which the tiers above account for roughly thirty. The rest are read, keyed and
carried, but their meaning is unknown. The most frequent, by record count across
the corpus:</p>
<dl>
<dt>others</dt><dd>{TIER_C_OTHERS}</dd>
<dt>details</dt><dd>{TIER_C_DETAILS}</dd>
<dt>DCL (ETF)</dt><dd>{TIER_C_ETF}</dd>
</dl>
<div class=note><strong>Two hints from the counts.</strong> Several pairs share an
exact record count &mdash; 213/215, 192/241, and <code>sL</code>/<code>sb</code>
&mdash; which across a whole corpus usually means a definition-and-assignment
couple like <code>articDef</code>/<code>articAssign</code>. And details tag 1043,
at 166,524 records, is roughly sixteen times more common than
<code>gfhold</code>, which suggests something per entry or per note rather than
per measure.</div>

<div class=prov><strong>What this means for scope.</strong> The tags decoded here
are not the common ones; they are the ones on the path from file to notes.
Everything above is largely layout, spacing, fonts, page format and text blocks.
By tag count this specification covers under a fifth of the vocabulary, and by
record count rather less &mdash; it is a specification for extracting the music,
not a complete description of the file.</div>
"""


# --------------------------------------------------------------------------
# ETF tags named by Coda's own documentation. These are a stronger claim than
# the key-sequence matches below: the vendor named them.
# --------------------------------------------------------------------------

ETF_OTHERS: list[tuple[str, str, str, str]] = [
    ("MS", "Measure Spec", "measure number", "spec"),
    ("IS", "Staff Spec", "instrument (staff) number", "spec"),
    ("IU", "Instrument Used", "IUList id; one incidence per slot", "spec"),
    ("FR", "Frame", "frame id; the entry span of one layer", "lily"),
    ("AC", "Tempo", "measure", "spec"),
    ("DY", "Score Expression", "measure", "spec"),
    ("DI", "Separate Placement", "measure of the score expression", "spec"),
    ("DT", "Text Expression", "dynumber in staff/score expression", "spec"),
    ("DO", "Shape Expression", "dynumber in staff/score expression", "spec"),
    ("PD", "Play Dump", "value in text/shape expression", "spec"),
    ("SD", "Shape", "shapedef in a shape expression", "spec"),
    ("SL", "Shape Instructions", "instlist; 3 instructions per record", "spec"),
    ("SB", "Shape Data", "datalist; the data those instructions use", "spec"),
    ("TX", "Text Block", "text block id; layout of a block of text", "spec"),
    ("pT", "Page Text Block", "page", "spec"),
    ("PS", "Page Spec", "page number", "spec"),
    ("SS", "Staff System Spec", "system number", "spec"),
    ("MN", "MeasNumberRegion", "which measure-number region", "spec"),
    ("IV", "Chord Suffix", "which chord suffix", "spec"),
    ("IK", "Chord Playback", "matches the cmper of its IV", "spec"),
    ("IX", "Articulation Definition", "referenced by an IM", "spec"),
    ("Sx", "Slur", "slur number; four rows per slur", "lily"),
    ("FB", "Fretboard library", "1&ndash;192; a fixed table, see below", "measured"),
]

ETF_DETAILS: list[tuple[str, str, str, str]] = [
    ("GF", "Frame Hold", "(staff, measure)", "lily"),
    ("NG", "Group Spec", "(iuList, groupID)", "spec"),
    ("FL", "Floats: independent key and time", "(instrument, measure)", "spec"),
    ("mt", "Measure Text Block", "(instrument, measure)", "spec"),
    ("LP", "Staff Enduction", "(staff system, instrument)", "spec"),
    ("MI", "MeasNumberSeparate", "(instrument, measure)", "spec"),
    ("ME", "Midi Expression", "(instrument, measure)", "spec"),
    ("hC", "Learned Chord", "(root, alternate bass)", "spec"),
    ("Ex", "Slur detail", "two rows per slur, paired with Sx", "thesis"),
    ("GT", "Fretboard index", "root as MIDI 60&ndash;71; 16 incidences each", "measured"),
]

ETF_ENTRY: list[tuple[str, str, str, str]] = [
    ("ac", "Performance data", "MIDI velocity and duration, per note", "spec"),
    ("ED", "Staff Expression", "one per expression on the entry", "spec"),
    ("CD", "Cross Staffing", "note moved to another staff", "spec"),
    ("IM", "Articulation", "positions a mark; names an IX", "spec"),
    ("CH", "Chord", "chord symbol on the entry", "spec"),
    ("CN", "Notehead Mods", "per-note custom attributes", "spec"),
    ("ve", "Lyric: verse", "syllable offset into a raw text record", "spec"),
    ("ch", "Lyric: chorus", "as ve", "spec"),
    ("se", "Lyric: section", "as ve", "spec"),
]

_SOURCE = {
    "spec": "ETF&nbsp;spec",
    "lily": "LilyPond",
    "thesis": "thesis",
    "measured": "measured",
}


def _etf_rows(rows: list[tuple[str, str, str, str]]) -> str:
    return "".join(
        f"<tr><td><code>^{t}</code></td><td>{n}</td><td>{k}</td>"
        f"<td class=sz>{_SOURCE[src]}</td></tr>"
        for t, n, k, src in rows
    )


def render_etf_tags() -> str:
    return f"""
<h4>ETF tags named by their vendor</h4>
<p>The 2001&ndash;2005 era uses ETF's two-character tags, and Coda documented
many of them. These are a <strong>stronger claim than the numeric tags
below</strong>: the vendor named them, rather than this project inferring a name
by matching key sequences. The source column says which document.</p>

<h4>others</h4>
<table><thead><tr><th>Tag</th><th>Name</th><th>Key (cmper)</th>
<th>Source</th></tr></thead><tbody>{_etf_rows(ETF_OTHERS)}</tbody></table>

<h4>details</h4>
<table><thead><tr><th>Tag</th><th>Name</th><th>Keys</th>
<th>Source</th></tr></thead><tbody>{_etf_rows(ETF_DETAILS)}</tbody></table>

<h4>entry details</h4>
<p>Keyed by an entry number rather than by position &mdash; the two cmpers hold
the high and low words of the entry number.</p>
<table><thead><tr><th>Tag</th><th>Name</th><th>Carries</th>
<th>Source</th></tr></thead><tbody>{_etf_rows(ETF_ENTRY)}</tbody></table>

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

<p>The library is written only when the feature is used: 44 of 139 DCL documents
carry it, against 149 of 150 <code>.musx</code> documents, later versions
shipping the defaults regardless.</p></div>

<div class=warn><strong>Not every DCL tag is two characters.</strong> A reader
that assumes the tag field always holds printable ASCII will mishandle a family
that every document carries. Alongside the character tags, the details pool
holds thirty <strong>numeric</strong> tags in three regular runs &mdash;
<code>0x8001</code>&ndash;<code>0x800a</code>,
<code>0x9001</code>&ndash;<code>0x900a</code> and
<code>0xa001</code>&ndash;<code>0xa00a</code> &mdash; each appearing about once
per document in all 139 DCL documents, and in both byte orders. Their meaning is
not established here; what matters for an implementer is that the field is a
u16, and only sometimes a pair of letters.</div>

<div class=note><strong>Case is significant.</strong> <code>^AC</code> is Tempo
and <code>^ac</code> is performance data; <code>^CH</code> is a chord and
<code>^hC</code> a learned one. A reader that upper-cases a tag before comparing
it will conflate unrelated records.</div>

<div class=warn><strong>A documented variant this project has never seen.</strong>
The LilyPond notes describe a second form of <code>^GF</code> occupying a single
row, laid out <code>frame, clef, ...</code> rather than <code>clef, flags,
frames</code>. A reader assuming the two-row form would take a frame id for a
clef. Measured across all 139 DCL corpus documents: every one of the 14,191
<code>GF</code> records has exactly two incidences and a 20-byte payload, so the
single-row form does not occur here. It is recorded as a known gap rather than a
defect.</div>

<div class=note><strong>Pairs travel together.</strong> Several of these are two
halves of one thing, which is why their record counts match almost exactly
across the corpus: <code>SL</code> and <code>SB</code> are a shape's
instructions and its data; <code>IV</code> and <code>IK</code> are a chord
suffix and its playback; <code>Sx</code> and <code>Ex</code> are a slur's
others-half and details-half.</div>
"""
