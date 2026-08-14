"""What each record tag is called, and how strongly that is known.

A tag is a number in the 2011 era and two characters before it, and on its own
it says nothing: `others/48` names a record only to someone holding a table.
This is that table.

**The tiers are the point, and they are kept apart deliberately.** A record
whose payload was read and checked against a paired document is a different
kind of claim from one named because its keys appear in the same order as a
named record's. Both are useful; conflating them is how a lead becomes a fact
in someone else's document. Every entry therefore carries the evidence behind
it, and anything showing a name is expected to show that too.

This covers 68 of the 492 tags the two eras use between them -- the ones on the
path from a file to its notes. What the rest hold is not known.
"""

from __future__ import annotations

from dataclasses import dataclass

DECODED = "decoded"
"""Payload read, fields checked against a paired `.musx`. The strongest claim
here: it is about what the bytes mean, not only about which record they are."""

DOCUMENTED = "documented"
"""Named by Coda's own ETF specification, or by published research. The vendor
named it, so the name is reliable; the payload may still be undecoded."""

MATCHED = "matched"
"""Named only because its key sequence matches a named record's, across paired
documents.

This is evidence about a record's *shape*, not its meaning. Many record types
are keyed one per measure or one per staff, so any two of those produce
identical sequences and could be swapped without the evidence noticing. A name
carrying this tier is a lead worth following, not a fact to build on.
"""

SOURCES = {
    "spec": "the ETF specification",
    "lily": "the LilyPond project's ETF notes",
    "cahill": "Cahill's thesis on Enigma and CPNView",
    "measured": "measurement against this corpus",
}
"""Where a `DOCUMENTED` name came from. No LilyPond source code was read."""


@dataclass(frozen=True)
class TagName:
    """What one record tag is called, in one pool of one era."""

    tag: str
    """The tag as the readers spell it: `"176"` or `"MS"`."""

    pool: str
    name: str
    description: str = ""
    tier: str = DECODED
    documents: int = 0
    """`MATCHED` only: how many paired documents agreed on this name."""

    source: str = ""
    """`DOCUMENTED` only: a key into `SOURCES`."""

    etf: str = ""
    """`DECODED` only: the two-character spelling of the same record, if any."""


# Decoded and payload-confirmed. Both spellings of each are registered below,
# so a document of either era finds the same name.
_DECODED: tuple[TagName, ...] = (
    TagName("109", "others", "clefOptions", "Clef definition table, read as a strided array"),
    TagName("121", "others", "articDef", "An articulation's definition; charMain is the glyph"),
    TagName("146", "others", "frameSpec", "Entry range for one layer of one measure", etf="FR"),
    TagName("159", "others", "instUsed", "The staves the score lays out, in layout order"),
    TagName(
        "176", "others", "measSpec", "Per measure: width, key, beats, divbeat, barline", etf="MS"
    ),
    TagName("203", "others", "repeatBack", "Backward repeat barline, keyed by measure"),
    TagName("204", "others", "repeatEndingStart", "Ending bracket, keyed by measure"),
    TagName("206", "others", "repeatPassList", "Which passes an ending is taken on"),
    TagName("231", "others", "staffSpec", "Per staff; transposition at +0x14", etf="IS"),
    TagName("1009", "details", "articAssign", "The articulation on an entry; names an articDef"),
    TagName(
        "1044", "details", "gfhold", "(staff, measure) to clef and up to four frames", etf="GF"
    ),
    TagName("1057", "details", "staffGroup", "Brace or bracket over a run of staves"),
    TagName("1072", "details", "tupletDef", "Keyed by entry, not by (staff, measure)"),
    TagName("1108", "details", "lyrDataVerse", "Verse lyrics"),
    # No numeric tag: entries are not in the numbered pools.
    TagName("eE", "entries", "entry", "The notes; fixed 38-byte slots"),
)

# Named by key-sequence matching only. `documents` is how many paired documents
# agreed -- and see MATCHED for what agreement does and does not establish.
_MATCHED: tuple[TagName, ...] = (
    TagName("124", "others", "channelPlayData", tier=MATCHED, documents=80),
    TagName("126", "others", "chordSuffixPlay", tier=MATCHED, documents=85),
    TagName("131", "others", "drumLibName", tier=MATCHED, documents=86),
    TagName("134", "others", "durAllot", tier=MATCHED, documents=91),
    TagName("136", "others", "execShape", tier=MATCHED, documents=85),
    TagName("140", "others", "fretboardSymbol", tier=MATCHED, documents=91),
    TagName("144", "others", "fontName", tier=MATCHED, documents=5),
    TagName("147", "others", "lockMeas", tier=MATCHED, documents=81),
    TagName("149", "others", "fretInst", tier=MATCHED, documents=90),
    TagName("163", "others", "layerAtts", tier=MATCHED, documents=85),
    TagName("165", "others", "metaArtic", tier=MATCHED, documents=80),
    TagName("168", "others", "metaDynam", tier=MATCHED, documents=81),
    TagName("169", "others", "metaKeySig", tier=MATCHED, documents=80),
    TagName("170", "others", "metaRepeat", tier=MATCHED, documents=81),
    TagName("171", "others", "metaShape", tier=MATCHED, documents=80),
    TagName("172", "others", "metaStaffStyle", tier=MATCHED, documents=80),
    TagName("173", "others", "metaTimeSig", tier=MATCHED, documents=81),
    TagName("235", "others", "shapeExprDef", tier=MATCHED, documents=10),
    TagName("242", "others", "textExpressionEnclosure", tier=MATCHED, documents=14),
    TagName("315", "others", "volumeValue", tier=MATCHED, documents=14),
)

WEAK_MATCH = 11
"""Below this many agreeing documents, a `MATCHED` name is better read as a
guess.

The threshold is the one the specification document already publishes: it warns
about `fontName` (5 agreements) and `shapeExprDef` (10), and does not warn about
the 14-document matches. Raising it here would have the tool contradict the
document about which names are guesses, which is a judgement to change in both
places or neither.
"""

# ETF's two-character tags, named by Coda's documentation or by research.
# `description` is the record's key, which is how these tables name a record.
_DOCUMENTED: tuple[TagName, ...] = (
    TagName("MS", "others", "Measure Spec", "measure number", DOCUMENTED, source="spec"),
    TagName("IS", "others", "Staff Spec", "instrument (staff) number", DOCUMENTED, source="spec"),
    TagName(
        "IU",
        "others",
        "Instrument Used",
        "IUList id; one incidence per slot",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "FR", "others", "Frame", "frame id; the entry span of one layer", DOCUMENTED, source="lily"
    ),
    TagName("AC", "others", "Tempo", "measure", DOCUMENTED, source="spec"),
    TagName("DY", "others", "Score Expression", "measure", DOCUMENTED, source="spec"),
    TagName(
        "DI",
        "others",
        "Separate Placement",
        "measure of the score expression",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "DT",
        "others",
        "Text Expression",
        "dynumber in staff/score expression",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "DO",
        "others",
        "Shape Expression",
        "dynumber in staff/score expression",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "PD", "others", "Play Dump", "value in text/shape expression", DOCUMENTED, source="spec"
    ),
    TagName("SD", "others", "Shape", "shapedef in a shape expression", DOCUMENTED, source="spec"),
    TagName(
        "SL",
        "others",
        "Shape Instructions",
        "instlist; 3 instructions per record",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "SB",
        "others",
        "Shape Data",
        "datalist; the data those instructions use",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "TX",
        "others",
        "Text Block",
        "text block id; layout of a block of text",
        DOCUMENTED,
        source="spec",
    ),
    TagName("pT", "others", "Page Text Block", "page", DOCUMENTED, source="spec"),
    TagName("PS", "others", "Page Spec", "page number", DOCUMENTED, source="spec"),
    TagName("SS", "others", "Staff System Spec", "system number", DOCUMENTED, source="spec"),
    TagName(
        "MN", "others", "MeasNumberRegion", "which measure-number region", DOCUMENTED, source="spec"
    ),
    TagName("IV", "others", "Chord Suffix", "which chord suffix", DOCUMENTED, source="spec"),
    TagName(
        "IK", "others", "Chord Playback", "matches the cmper of its IV", DOCUMENTED, source="spec"
    ),
    TagName(
        "IX", "others", "Articulation Definition", "referenced by an IM", DOCUMENTED, source="spec"
    ),
    TagName("Sx", "others", "Slur", "slur number; four rows per slur", DOCUMENTED, source="lily"),
    TagName(
        "FB",
        "others",
        "Fretboard library",
        "1–192; a fixed table, see below",
        DOCUMENTED,
        source="measured",
    ),
    TagName("GF", "details", "Frame Hold", "(staff, measure)", DOCUMENTED, source="lily"),
    TagName("NG", "details", "Group Spec", "(iuList, groupID)", DOCUMENTED, source="spec"),
    TagName(
        "FL",
        "details",
        "Floats: independent key and time",
        "(instrument, measure)",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "mt", "details", "Measure Text Block", "(instrument, measure)", DOCUMENTED, source="spec"
    ),
    TagName(
        "LP", "details", "Staff Enduction", "(staff system, instrument)", DOCUMENTED, source="spec"
    ),
    TagName(
        "MI", "details", "MeasNumberSeparate", "(instrument, measure)", DOCUMENTED, source="spec"
    ),
    TagName("ME", "details", "Midi Expression", "(instrument, measure)", DOCUMENTED, source="spec"),
    TagName("hC", "details", "Learned Chord", "(root, alternate bass)", DOCUMENTED, source="spec"),
    TagName(
        "Ex",
        "details",
        "Slur detail",
        "two rows per slur, paired with Sx",
        DOCUMENTED,
        source="cahill",
    ),
    TagName(
        "GT",
        "details",
        "Fretboard index",
        "root as MIDI 60–71; 16 incidences each",
        DOCUMENTED,
        source="measured",
    ),
    TagName(
        "DF",
        "details",
        "Percussion map",
        "(map id 1–26, MIDI note 0–127)",
        DOCUMENTED,
        source="measured",
    ),
    TagName(
        "ac",
        "entries",
        "Performance data",
        "MIDI velocity and duration, per note",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "ED",
        "entries",
        "Staff Expression",
        "one per expression on the entry",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "CD", "entries", "Cross Staffing", "note moved to another staff", DOCUMENTED, source="spec"
    ),
    TagName(
        "IM", "entries", "Articulation", "positions a mark; names an IX", DOCUMENTED, source="spec"
    ),
    TagName("CH", "entries", "Chord", "chord symbol on the entry", DOCUMENTED, source="spec"),
    TagName(
        "CN", "entries", "Notehead Mods", "per-note custom attributes", DOCUMENTED, source="spec"
    ),
    TagName(
        "ve",
        "entries",
        "Lyric: verse",
        "syllable offset into a raw text record",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "ch",
        "entries",
        "Lyric: chorus",
        "syllable offset, as for a verse",
        DOCUMENTED,
        source="spec",
    ),
    TagName(
        "se",
        "entries",
        "Lyric: section",
        "syllable offset, as for a verse",
        DOCUMENTED,
        source="spec",
    ),
)

TAG_NAMES: tuple[TagName, ...] = _DECODED + _MATCHED + _DOCUMENTED


def _index() -> dict[tuple[str, str], TagName]:
    """Every tag by pool and spelling, strongest claim winning.

    A decoded record is registered under its ETF spelling too, so a 2001-2005
    document naming a record `MS` gets `measSpec` rather than the weaker entry
    the ETF table would give it. The order of `TAG_NAMES` puts the decoded
    entries first and nothing later overwrites them.
    """
    index: dict[tuple[str, str], TagName] = {}
    for entry in TAG_NAMES:
        for spelling in (entry.tag, entry.etf):
            if spelling and (entry.pool, spelling) not in index:
                index[(entry.pool, spelling)] = entry
    return index


_INDEX = _index()


def name_for(pool: str, tag: str) -> TagName | None:
    """What this tag is called, or None where this project cannot say.

    `tag` is spelled as the readers spell it: `"176"` or `"MS"`.
    """
    return _INDEX.get((pool, tag))
