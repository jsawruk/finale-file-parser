"""Build an `EnigmaDocument` from a legacy `.mus` file.

The adapter that closes the loop on `docs/DECISIONS.md`'s hub-and-shape: the
`.mus` pools hold the same record model `parse_enigma` builds from a `.musx`, so
translating them into `Record`s makes every module downstream -- `locate_entries`,
`read_entry`, `time_signatures`, `build_score`, `to_musicxml` -- work on a `.mus`
without a line of change. There is no second pipeline to keep in step.

    read_mus_document(path) -> EnigmaDocument -> build_score -> to_musicxml

**This is an MVP: it translates only the record types whose payloads are
decoded.** What that covers, and what it does not, is the whole of
`UNTRANSLATED` below -- read it before trusting a `.mus`-derived score. Nothing
here guesses at an undecoded layout; a record type this module does not
understand is absent from the document rather than present and wrong, because a
missing part name is obvious and a fabricated one is not.

Translated:

| pool | tag | fields |
| --- | --- | --- |
| entries | `entry` | via `read_mus_entry_records` |
| others | `frameSpec` (146) | `startEntry`, `endEntry` |
| others | `measSpec` (176) | `keySig.key`, `beats`, `divbeat`, the +10 flags byte |
| details | `gfhold` (1044) | `clefID`, `frame1`, `frame2` |
| options | `clefOptions` (109) | the clef table: `adjust`, `clefChar`, `clefYDisp`, `shapeID` |
| details | `tupletDef` (1072) | `symbolicNum`, `symbolicDur`, `refNum`, `refDur` |
| others | `staffSpec` (231) | `transposition.keysig.adjust` only — see below |
| others | `instUsed` (159) | `inst` per 24-byte slot — the staff layout order |
| details | `lyrDataVerse` (1108) | `lyricNumber`, `syll`, `wext`, per 20-byte group |
| details | `articAssign` (1009) | `articDef` |
| others | `articDef` (121) | `charMain` — at +0 (2011) or +2 (2012) |
| others | `repeatBack` (203) | `actuate` — Finale's "Total Passes" |
| others | `repeatEndingStart` (204) | presence only; the bracket's extent comes from `barEnding` |
| others | `repeatPassList` (206) | `act` — the passes the ending is taken on, a u16 array |
| details | `staffGroup` (1057) | `startInst`, `endInst`, `bracket.id`, `fullID`, the barline bit |
| texts | `verse` | the `^verse(N)…^end` sections of the text stream |

Every field above is confirmed against paired `.musx` files; see
`docs/formats/mus-binary-notes.md` for the evidence behind each.
"""

from __future__ import annotations

import os
import re

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
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_details import (
    TAG_ARTIC_ASSIGN,
    TAG_GFHOLD,
    TAG_LYRIC_VERSE,
    TAG_STAFF_GROUP,
    TAG_TUPLET_DEF,
    MusDetailRecord,
    entry_key,
    read_mus_details,
)
from finale_file_parser.enigma.mus_entries import read_mus_entry_records
from finale_file_parser.enigma.mus_others import (
    OPTIONS_CMPER,
    TAG_ARTIC_DEF,
    TAG_CLEF_OPTIONS,
    TAG_FRAME_SPEC,
    TAG_INST_USED,
    TAG_MEAS_SPEC,
    TAG_REPEAT_BACK,
    TAG_REPEAT_ENDING_START,
    TAG_REPEAT_PASS_LIST,
    TAG_STAFF_SPEC,
    MusOther,
    read_mus_others,
)
from finale_file_parser.enigma.mus_payload import ByteOrder, read_mus_pools, read_mus_streams
from finale_file_parser.enigma.mus_rows import MusRows, read_mus_rows
from finale_file_parser.version import mus as mus_header

__all__ = ["UNTRANSLATED", "read_mus_document"]

UNTRANSLATED = (
    "staffSpec part names: the names ARE in the file -- text stream 3 carries "
    "them as ^block(N) sections, and staffSpec +30 selects one. What is missing "
    "is the FIXED TABLE from that id to the block number. This entry has twice "
    "described the unknown as a per-document base; that was wrong both times. "
    "The mapping does not vary by document: name id 2 selects block 30 in ten "
    "documents of ten different pieces, and across 25 anchors no id ever "
    "selects two blocks. The delta looked document-dependent only because "
    "different documents use different ids. Nine ids are known (2->30, 89->20, "
    "91/92/93->22, 94/95->24, 97->26, 98->37), which is enough to show the "
    "answer is a many-to-one table and far too few to ship one -- fitting a "
    "formula to nine points would repeat the palette trap. This closes when "
    "more paired documents cover more ids, or Finale's own table is obtained "
    "from outside this corpus; it does not close by looking harder at these "
    "files. Parts still fall back to positional names. See "
    "docs/formats/mus-staff-names.md.",
    "Instrument-derived clefs: where a gfhold stores clefID 0 it means 'use the "
    "staff's defaultClef', and for some staves the .mus stores 0 there too while "
    "the .musx materialises a real clef. Those measures come out treble. Same "
    "root cause as the transposition gap above -- the value lives with the "
    "instrument, not in the file.",
    "measSpec display time signatures (useDisplayTimesig, dispBeats, dispDivbeat).",
    "Final barlines: measSpec's flags byte at +10 holds the barline style in its "
    "high nibble, and 1 (normal) and 2 (double) ARE read -- see enigma.barlines. "
    "A final bar is not: nibble 3 is the obvious reading and it does not occur "
    "once in 8,540 measures across all 238 corpus .mus documents -- re-derived, "
    "and the DCL cohort's 4,113 measures had never been measured for it -- so "
    "nothing checks a guess. A .mus therefore ends a piece with an ordinary barline where the "
    ".musx draws a final one.",
    "Staff group names: a staffGroup's fullID IS recovered, but resolving it "
    "needs the textBlock -> blockText chain, which a .mus does not supply -- "
    "the same missing chain as staffSpec part names. Groups therefore come out "
    "unnamed rather than labelled with a raw block number. 26 of the 95 paired "
    "documents carry a group, and the ones differing from their .musx in "
    "nothing but the name are pinned as GROUP_NAME_ONLY_DIFFERENCES.",
    "Staff layout order in a 2001-2005 .mus: the 2011 tag IS identified (159, "
    "see mus_others.TAG_INST_USED) and read, so a 2011 .mus now lays its staves "
    "out in score order rather than numeric order. The DCL era carries an ETF "
    "^Iu row, which is very likely the same record, but that cohort has no "
    "paired .musx anywhere -- so there is nothing to check a slot layout "
    "against, and this reader does not guess at one. A 2001-2005 document whose "
    "staves are laid out out of order therefore still comes out numerically.",
    "Mirror transposition: Finale's Mirror Tool appears to let a mirrored "
    "staff carry its own transposition or octave displacement. Mirrors "
    "themselves ARE read -- an entry holds a location per placement and the "
    "music is built onto every staff that displays it -- but no field carrying "
    "a per-mirror offset has been identified, and the only corpus document "
    "where a mirror reaches the score has both staves transposing by zero. So "
    "nothing here can test one, and fitting an offset to a single point would "
    "be a guess. A mirror is therefore read as the same music in both places, "
    "which is right for this corpus and may be incomplete in general. "
    "Pinned as MIRRORED_ENTRIES.",
    "Text repeats (Fine, D.C. al Coda): the .musx reading is implemented and the "
    ".mus one is not, so a .mus still exports no markings. What is missing is "
    "narrower than this entry twice claimed. **The DCL tag is ^RT**, and its "
    "payload spells itself out: 411 records across all 38 DCL documents carry "
    "'D.C. al Fine', 'D.C. al Coda', 'D.S. al Fine' and 'D.S. al Coda' as text. "
    "This entry previously said the corpus offers NO evidence to identify the "
    "tag from, 'not a little, none'. That was wrong, and wrong in a specific "
    "way worth naming: it reasoned only about PAIRED documents, found the three "
    "candidate pairs were mispairings (entry counts 172 vs 189, 192 vs 89, 76 "
    "vs 719/294/165 -- different arrangements sharing a filename), and "
    "concluded the corpus was silent. The DCL cohort was never searched, and it "
    "was not silent. A record naming itself needs no pair to be recognised. "
    "What genuinely remains: ^RT is the DEFINITION, giving the text of a jump; "
    "the assignment that attaches one to a measure, and the action telling a "
    "player where to go, are still unidentified, and the 2001-2005 cohort has "
    "no paired .musx anywhere to verify a payload layout against. See "
    "enigma.jumps and formats.tags.",
    "Repeat jumps: repeatBack's target/trigger/action, and textRepeatAssign's "
    "action/target, describe where a repeat sends the player rather than what is "
    "printed. Neither container reads them, so both are equally silent -- a "
    "missing feature rather than a .mus gap.",
    "Fingering fonts: articDef's fontMain cannot be read from a .mus -- its "
    "offset moves within the 2011 era, and the best single offset matches only "
    "363 of 373 paired records. Fingerings themselves ARE read, from the "
    "character alone; see enigma.fingerings for why that is sufficient.",
    "Chorus and section lyrics: the .mus tag for lyrDataVerse is identified, but "
    "no paired corpus document uses a chorus or section track, so their tags are "
    "unknown and those lyrics are absent from a .mus-derived score.",
    "gfhold frame3-4 in a 2011 .mus: layers 3 and 4. Frames 1 and 2 are at "
    "payload +6 and +8, confirmed against the corpus. This entry used to say no "
    "corpus .musx carries a frame3 or frame4; that is wrong -- 141 frame3 and "
    "147 frame4 slots exist. What is true, and is the reason the next two slots "
    "stay a guess, is that NONE of them is in a PAIRED document: 0 of 95. A "
    ".musx with no .mus cannot verify a .mus offset. A 2011 document using "
    "layer 3 or 4 therefore leaves those entries "
    "unplaced, which locate_entries rejects as orphans -- a loud failure rather "
    "than a silent misplacement. The 2001-2005 rows reader does read all four "
    "slots; see _FRAME_LAYERS for why the number is the format's, not a guess.",
)
"""What a `.mus`-derived score does not yet carry, and the consequence of each.

Kept as data rather than prose so a caller can surface it, and so closing one
gap is a visible deletion here.
"""

_VERSION = "mus"
"""`EnigmaDocument.version` is the EnigmaXML schema version, which a `.mus` has
no equivalent of. A distinct value is better than a plausible-looking lie."""

_CLEF_ENTRY_STRIDE = {2011: 18, 2012: 20}
"""Bytes per clef-table entry, by the banner year that wrote the file.

The two eras lay the entry out differently, and the file says which it is --
the same era split `mus_payload` already uses to choose a codec. Deriving the
stride from the payload length instead would need the entry count assumed, and
324 and 360 are both divisible by 18 and 20, so the ambiguity is real.
"""

_CLEF_FIELD_OFFSETS = {
    18: {"adjust": 0, "clefChar": 2, "clefYDisp": 4, "shapeID": 8},
    20: {"adjust": 0, "clefChar": 2, "clefYDisp": 6, "shapeID": 10},
}
"""Field offsets within a clef entry, per stride. 2012 inserts two bytes after
`clefChar` and two more before `shapeID`; everything else is shared."""

_ARTIC_CHAR_OFFSET = {48: 0, 60: 2}
"""Where `charMain` sits in an `articDef` payload, by payload length.

The same era split as the clef table: 2011 writes 48 bytes with the character
first, 2012 writes 60 with two bytes ahead of it. Keyed by length rather than by
banner year because the length is right there and the two agree on every corpus
record -- 4,841 at 48 bytes, all 2011, and 311 at 60, all 2012.
"""

_ARTIC_DEF_REFERENCE = 0
"""Where an `articAssign` payload names its definition."""

_LYRIC_GROUP = 20
"""Bytes per verse assignment inside a `lyrDataVerse` payload."""

_LYRIC_NUMBER = 0
_LYRIC_SYLL = 2
_LYRIC_WEXT = 8
"""Word-extension flag; matches the `.musx` `wext` on every corpus assignment."""

_TEXT_STREAM = 3
"""The payload stream holding ETF tagged text (`^verse(1)...^end`)."""

_TEXT_SECTION = re.compile(rb"\^(verse|chorus|section)\((\d+)\)(.*?)\^end", re.DOTALL)
"""One tagged text section. The body keeps its markup; `plain_text` strips it."""

_FALLBACK_ENCODING = {"MAC": "mac_roman", "WIN": "cp1252"}
"""What a text section is if it is not UTF-8.

Most corpus sections decode as UTF-8, but not all -- five verses in the paired
corpus are legacy 8-bit text -- and which legacy encoding depends on the
platform that wrote the file, which its header records.
"""

_STAFF_TRANSPOSITION = 20
"""Offset of `staffSpec`'s `transposition` field, per ETF's documented field
order (`... topBarlineOffset transposition instflag dw_wRest ...`)."""

_GROUP_BRACKET_ID = 10
_GROUP_ABBRV_ID = 22
_GROUP_BARLINE_BYTE = 21
_GROUP_BARLINE_BIT = 0x04
"""`staffGroup`'s "barlines run through the group" bit -- 0x0400 of the flag
word at +20.

Found by testing every (byte, bit) against the paired `.musx`, where it is the
only exact candidate. One negative example is thin on its own, but
`etfspec.pdf` corroborates it independently: its worked example reads
`flag: 1088 = 0x0440 (barline through all staves, connecting; normal barline
style)`, and 0x0400 is the bit that example sets."""

_MEAS_FLAGS = 10
_MEAS_BARLINE_STYLES = {1: "normal", 2: "double"}
"""The flags byte's **high nibble** is the barline style, as `.musx` names it.

Paired documents agree on 3,960 ordinary measures and all 11 double bars, with
no counterexample. **`final` is deliberately absent**: nibble 3 would be the
obvious reading and it does not occur once in 4,427 measures across 99 `.mus`
documents, so there is nothing to check it against. See `enigma.barlines`."""

_MEAS_REPEAT_BITS = {"barEnding": 0x02, "bacRepBar": 0x04, "forRepBar": 0x08}
"""`measSpec`'s repeat-barline flags, all in the byte at +10.

Found by testing every (byte, bit) in the payload against the paired `.musx`:
each of the three has exactly one candidate that agrees on all 1,025 measures of
the 20 paired documents that use repeats, with no second candidate anywhere
close. That they land on three adjacent bits of one byte is the corroboration
the correlation alone would not give -- this is a flags byte, not three
coincidences. Its high nibble is the barline style (1 normal, 2 double), which
is deliberately not read: the paired corpus holds 11 double barlines and no
final one, which is too thin to commit to."""

_ALTERATION_MAGNITUDE = 0x07
_ALTERATION_SIGN = 0x08
"""The transposition's key alteration is its low nibble, read the way
`eeppd.txt` documents a note TCD's alteration: sign and magnitude, bit 3 being
the sign, not two's complement. Every corpus value is positive, so the two
readings agree here -- the TCD is what decides which to use, not the corpus."""

_CLEF_SIGNED = {"adjust", "clefYDisp"}
"""`clefChar` and `shapeID` are unsigned; the two displacements are not."""

_EMPTY: tuple[Record, ...] = ()


def read_mus_document(path: str | os.PathLike[str]) -> EnigmaDocument:
    """Read the `.mus` file at `path` as an `EnigmaDocument`.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode, or a pool is missing or
            malformed.
    """
    try:
        others = read_mus_others(path)
        details = read_mus_details(path)
    except CorruptScoreError:
        # A 2001-2005 file stores its pools as ETF-tagged rows, which those two
        # readers refuse by design. Checked here rather than up front so the
        # common path stays one decode, and so the error a genuinely corrupt
        # 2011 file raises is still the one the caller sees.
        if any(pool.kind is not None for pool in read_mus_pools(path)):
            return _rows_document(path)
        raise
    return EnigmaDocument(
        version=_VERSION,
        header=Pool(records=_EMPTY),
        mappings=Pool(records=_EMPTY),
        options=OptionsPool(records=tuple(_options_records(others, _banner_year(path)))),
        others=OthersPool(records=tuple(_others_records(others))),
        details=DetailsPool(records=tuple(_details_records(details))),
        entries=EntriesPool(records=read_mus_entry_records(path)),
        texts=TextsPool(records=tuple(_texts_records(path))),
    )


_FRAME_BASE_2001 = 4
_FRAME_BASE_2005 = 6
"""Where a `GF` record's frame array starts. The 2005 layout carries two more
bytes ahead of it, and the staff spec's incidence count is what tells the eras
apart -- three in a 2001 file, six in a 2005 one. See
`docs/formats/mus-dcl-container.md`."""

_FRAME_LAYERS = 4
"""Frame slots per `GF` record, one per Finale layer.

Four, not the two the 2011 reader takes: a fifth slot never resolves to a frame
in any corpus document, and reading the third and fourth reaches 1,058 entries
that two leave orphaned. Finale has four layers, so this is the format's own
number rather than a fitted one."""

_ROW_DATA = 12
"""Bytes of data in one `others` row, so `incidences` gives the payload's shape."""

_FRAME_START_TIME = "startTime"
"""The field the leading incidence carries.

**The entry pair sits in a frame's LAST incidence.** Most `FR` records have one
incidence and the pair is the whole of it. 114 of 13,322 have two, and the first
holds a `startTime` in EDU -- a frame whose entries do not begin at the start of
its measure.

That is the format's own shape, not a reading of this corpus: a `.musx` does the
same thing. Exactly 15 `.musx` frameSpec cmpers carry more than one incidence and
exactly 15 records carry a `startTime`, its values 2048/3072/3584 all appearing
among the DCL leading blocks (1024, 1536, 2048, 2560, 3072, 3584, 5632 -- every
one a multiple of 512). `enigma.location` already reads that shape for the 2011
era: "a frame cmper can carry two, where the first is empty and the second holds
the entry chain".

This replaced a fallback that tried +0, then +12, and kept whichever named
entries the pool held. The two agree on all 13,306 frames the fallback resolved
and drop the same 16 -- so nothing moved, but the reader can now say which
reading is right rather than only which one worked.
"""


def _rows_document(path: str | os.PathLike[str]) -> EnigmaDocument:
    """Build a document from a 2001-2005 file's ETF-tagged rows.

    Its pools hold the same records as the 2011 era at the same offsets -- the
    2011 binary *is* the ETF layout -- so only the byte order and the framing
    differ, and the field decoders above are shared rather than reimplemented.
    """
    rows = read_mus_rows(path)
    if not any(tag == "GF" for tag, _, _ in rows.details):
        # No frame holds means nothing places music on a staff. Three corpus
        # documents are like this, and all three also carry an empty entry pool:
        # they are blank scores. Building one yields a Score with no parts,
        # which is not valid MusicXML and is worse than saying so.
        raise CorruptScoreError(f"{path} has no frame holds; the document carries no music")
    entries = read_mus_entry_records(path)
    live = {int(record.attrs["entnum"]) for record in entries}
    frames, dropped = _rows_frames(rows, live)
    gfholds = _rows_details(rows, dropped)
    kept = _live_entries(entries, frames, gfholds)
    if entries and not kept:
        # The pool holds music but no frame reaches any of it. Pruning would
        # leave an empty pool and `build_score` would return a Score with no
        # parts -- a silent nothing, which is worse than saying so. Three corpus
        # documents are like this: they carry a frame hold, so they do not fall
        # to the check above, but nothing it names resolves.
        raise CorruptScoreError(
            f"{path} has {len(entries)} entries but no frame reaches any of them"
        )
    return EnigmaDocument(
        version=_VERSION,
        header=Pool(records=_EMPTY),
        mappings=Pool(records=_EMPTY),
        options=OptionsPool(records=tuple(_rows_options(rows))),
        others=OthersPool(records=tuple(_rows_others(rows, frames))),
        details=DetailsPool(records=tuple(gfholds)),
        entries=EntriesPool(records=kept),
        texts=TextsPool(records=tuple(_texts_records(path))),
    )


def _live_entries(
    entries: tuple[Record, ...],
    frames: dict[int, tuple[int, int, int | None]],
    gfholds: list[Record],
) -> tuple[Record, ...]:
    """The entries some frame reaches, in pool order.

    **The entry pool is a live database, not a list of the music.** A `.mus` is
    written in place, so an entry deleted in Finale keeps its slot until the file
    is compacted, and the pool holds both the current music and whatever earlier
    music has not been overwritten. The frames are what say which is which.

    That this is dead space rather than music the reader fails to place is the
    corpus's verdict, not an assumption: of the entries no frame reaches, 88% are
    *exact duplicates of passages the frames do reach* -- matched as whole
    `next`-chains, so shape-for-shape coincidence in tonal music is not the
    explanation. One document keeps entries 1-858 as a stale copy of the live
    859-1717, 824 of them identical field for field.

    Dropping them here rather than tolerating them downstream keeps
    `locate_entries`' orphan check meaning what it says in both eras: an entry no
    frame places is still an error there, and it still fires for `.musx` and for
    2011 `.mus`. What stops this from hiding a real misplacement is that the
    corpus sweep pins how many entries it discards -- a reader that stopped
    reaching music would discard more, and the pin only permits fewer. See
    `docs/formats/mus-dcl-container.md`.
    """
    by_num = {int(record.attrs["entnum"]): record for record in entries}
    reached: set[int] = set()
    for gfhold in gfholds:
        for layer in range(_FRAME_LAYERS):
            value = gfhold.fields.get(f"frame{layer + 1}")
            if not isinstance(value, str):
                continue
            span = frames.get(int(value))
            if span is None:
                continue
            start, end, _ = span
            entnum = start
            # Bounded by the pool: every step consumes an unvisited entry, so a
            # chain that cycles or never meets its endEntry still terminates.
            for _ in range(len(by_num)):
                record = by_num.get(entnum)
                if record is None or entnum in reached:
                    break
                reached.add(entnum)
                if entnum == end:
                    break
                entnum = int(record.attrs.get("next", 0))
    return tuple(record for record in entries if int(record.attrs["entnum"]) in reached)


def _rows_frame_base(rows: MusRows) -> int:
    specs = [record for (tag, _), record in rows.others.items() if tag == "IS"]
    return _FRAME_BASE_2001 if specs and specs[0].incidences == 3 else _FRAME_BASE_2005


def _rows_frames(
    rows: MusRows, live: set[int]
) -> tuple[dict[int, tuple[int, int, int | None]], set[int]]:
    """Each `FR` record's entry span, and the frames that could not be read.

    A frame naming entries the pool does not hold is dropped rather than
    emitted: `build_score` rejects a chain it cannot walk, so keeping one would
    cost the whole document instead of one frame's music.
    """
    found: dict[int, tuple[int, int, int | None]] = {}
    dropped: set[int] = set()
    for (tag, cmper), record in rows.others.items():
        if tag != "FR":
            continue
        span = _frame_span(record.payload, record.incidences, rows.byte_order)
        if span is None or span[0] not in live or span[1] not in live:
            dropped.add(cmper)
            continue
        found[cmper] = span
    return found, dropped


def _frame_span(
    payload: bytes, incidences: int, order: ByteOrder
) -> tuple[int, int, int | None] | None:
    """A frame's `startEntry`, `endEntry` and `startTime`, or None if malformed.

    The pair is in the last incidence; a leading one carries the start time. See
    `_FRAME_START_TIME`.
    """
    if incidences < 1 or len(payload) < incidences * _ROW_DATA:
        return None
    base = (incidences - 1) * _ROW_DATA
    start = _u32(payload, base, order)
    end = _u32(payload, base + 4, order)
    # A stored 0 is written as no startTime at all, the same omission convention
    # as measSpec.key and gfhold.clefID.
    start_time = _u32(payload, 0, order) if incidences > 1 else 0
    return start, end, start_time or None


_ROWS_CLEF_OPTIONS = "95"
"""The 2001-2005 tag holding the clef table -- `clefOptions` in the later era.

Identified by its bytes, not by inference. The payload of this record is
**byte-for-byte identical** to the 2011 era's `clefOptions` (tag 176's
neighbour, 109) in 98 of the 102 little-endian corpus documents that carry it,
over all 288 bytes; and identical again in 24 of the 37 big-endian ones once
each field is read in the document's own order, with the rest differing in a
handful of bytes as one document's table differs from another's.

The 288-byte payload is 16 entries of the 18-byte stride the 2011 era uses, and
the 324-byte one is 18 of them -- the same entries, the same layout, one era
earlier. Without this the whole 2001-2005 cohort exported no clef at all: 132
documents and 416 parts, where a consumer given no clef assumes treble and a
bass staff reads an octave and a half wrong.
"""

_ROWS_CLEF_STRIDE = 18
"""Bytes per clef entry in a 2001-2005 table. Not derived from the payload
length -- 288 and 324 are both divisible by 18 and by 12 -- but from the byte
identity above: these are the 2011 era's own 18-byte entries."""


def _rows_options(rows: MusRows) -> list[Record]:
    """The document-wide options the 2001-2005 reader can translate: the clef
    table, so far -- and, until this, nothing at all."""
    record = rows.others.get((_ROWS_CLEF_OPTIONS, OPTIONS_CMPER))
    if record is None or not record.payload:
        return []
    if len(record.payload) % _ROWS_CLEF_STRIDE:
        # The stride is known; a payload that is not a whole number of entries
        # means this is not the table after all. Emit nothing rather than a
        # mis-strided one, which would produce plausible wrong clefs.
        return []
    definitions = tuple(
        _clef_def(record.payload[at : at + _ROWS_CLEF_STRIDE], _ROWS_CLEF_STRIDE, rows.byte_order)
        for at in range(0, len(record.payload), _ROWS_CLEF_STRIDE)
    )
    return [Record(tag="clefOptions", attrs={}, text="", fields={"clefDef": definitions})]


def _rows_others(rows: MusRows, frames: dict[int, tuple[int, int, int | None]]) -> list[Record]:
    out: list[Record] = []
    for (tag, cmper), record in rows.others.items():
        attrs = {"cmper": str(cmper)}
        if tag == "MS":
            out.append(
                Record(
                    tag="measSpec",
                    attrs=attrs,
                    text="",
                    fields=_meas_spec(record.payload, rows.byte_order),
                )
            )
        elif tag == "IS":
            out.append(
                Record(
                    tag="staffSpec",
                    attrs=attrs,
                    text="",
                    fields=_staff_spec(record.payload, rows.byte_order),
                )
            )
        elif tag == "FR" and cmper in frames:
            start, end, start_time = frames[cmper]
            fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
                "startEntry": str(start),
                "endEntry": str(end),
            }
            if start_time is not None:
                fields[_FRAME_START_TIME] = str(start_time)
            out.append(Record(tag="frameSpec", attrs=attrs, text="", fields=fields))
    return out


def _rows_details(rows: MusRows, dropped: set[int]) -> list[Record]:
    base = _rows_frame_base(rows)
    out: list[Record] = []
    for (tag, cmper1, cmper2), record in rows.details.items():
        if tag != "GF":
            continue
        fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
            "clefID": str(_u16(record.payload, 0, rows.byte_order))
        }
        for layer in range(_FRAME_LAYERS):
            frame = _u16(record.payload, base + 2 * layer, rows.byte_order)
            # A dropped frame's reference goes too: a gfhold naming a frameSpec
            # that is not there is rejected the same way a broken chain is.
            if frame and frame not in dropped:
                fields[f"frame{layer + 1}"] = str(frame)
        out.append(
            Record(
                tag="gfhold",
                attrs={"cmper1": str(cmper1), "cmper2": str(cmper2)},
                text="",
                fields=fields,
            )
        )
    return out


def _u16(payload: bytes, offset: int, order: ByteOrder = "little") -> int:
    return int.from_bytes(payload[offset : offset + 2], order)


def _u32(payload: bytes, offset: int, order: ByteOrder = "little") -> int:
    return int.from_bytes(payload[offset : offset + 4], order)


def _texts_records(path: str | os.PathLike[str]) -> list[Record]:
    """The text stream's tagged sections, as `verse`/`chorus`/`section` Records.

    A `.mus` keeps these as ETF tagged text rather than as binary records, so
    they are read straight out of the stream. The body keeps its markup, exactly
    as the `.musx` texts pool does, and `plain_text` handles both dialects.
    """
    streams = read_mus_streams(path)
    if len(streams) <= _TEXT_STREAM:
        return []
    fallback = _FALLBACK_ENCODING.get(_banner_platform(path) or "", "cp1252")
    out: list[Record] = []
    seen: set[tuple[str, str]] = set()
    for match in _TEXT_SECTION.finditer(streams[_TEXT_STREAM]):
        tag = match.group(1).decode("ascii")
        number = match.group(2).decode("ascii")
        if (tag, number) in seen:
            # TextsPool rejects a duplicate identity, and a repeated section is
            # the writer's business rather than something to fail a read over.
            continue
        seen.add((tag, number))
        out.append(
            Record(
                tag=tag, attrs={"number": number}, text=_decode(match.group(3), fallback), fields={}
            )
        )
    return out


def _decode(raw: bytes, fallback: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(fallback, errors="replace")


def _banner_platform(path: str | os.PathLike[str]) -> str | None:
    with open(path, "rb") as handle:
        stamp = mus_header.parse(handle.read(mus_header.MUS_METADATA_SIZE))
    return stamp.created.platform if stamp.created else None


def _banner_year(path: str | os.PathLike[str]) -> int | None:
    """The Finale version that wrote the file, which fixes the clef-entry width.

    Read from the plaintext header rather than guessed from a payload length --
    see `_CLEF_ENTRY_STRIDE`.
    """
    with open(path, "rb") as handle:
        return mus_header.parse(handle.read(mus_header.MUS_METADATA_SIZE)).year


def _options_records(records: tuple[MusOther, ...], year: int | None) -> list[Record]:
    """The document-wide options this can translate: the clef table, so far."""
    stride = _CLEF_ENTRY_STRIDE.get(year or 0)
    if stride is None:
        return []
    for record in records:
        if record.tag != TAG_CLEF_OPTIONS or record.cmper != OPTIONS_CMPER:
            continue
        if not record.payload or len(record.payload) % stride:
            # The era says how wide an entry is; a payload that is not a whole
            # number of them means one of the two is wrong. Emit no table rather
            # than a mis-strided one, which would produce plausible wrong clefs.
            continue
        definitions = tuple(
            _clef_def(record.payload[at : at + stride], stride)
            for at in range(0, len(record.payload), stride)
        )
        return [Record(tag="clefOptions", attrs={}, text="", fields={"clefDef": definitions})]
    return []


def _clef_def(entry: bytes, stride: int, order: ByteOrder = "little") -> Record:
    """One clef-table entry.

    A zero `clefChar` or `shapeID` is written as an absent field, not as "0":
    `clef_definitions` reads absent as "there is no character/shape", and a
    clef with neither is what makes `Clef.sign` report UNKNOWN rather than
    inventing a G clef.

    `order` is the document's, not a constant: the 2001-2005 era carries this
    same table big-endian in 37 corpus documents, where reading it little-endian
    turns every clef character into a different one.
    """
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {}
    for name, offset in _CLEF_FIELD_OFFSETS[stride].items():
        raw = entry[offset : offset + 2]
        value = int.from_bytes(raw, order, signed=name in _CLEF_SIGNED)
        if value or name in _CLEF_SIGNED:
            fields[name] = str(value)
    return Record(tag="clefDef", attrs={}, text="", fields=fields)


_INST_SLOT = 24
"""Bytes per `instUsed` slot, one slot per staff, staff number in the first u16.

The slot size is not inferred from one document: the record's length is exactly
`24 x` the staff count in all 95 paired documents, which is what distinguishes
this record from a sequence that merely happens to fit. The remaining 22 bytes of
a slot are not decoded. See `mus_others.TAG_INST_USED`.
"""


def _others_records(records: tuple[MusOther, ...]) -> list[Record]:
    out: list[Record] = []
    for record in records:
        attrs = {"cmper": str(record.cmper)}
        if record.part:
            # A part-variant record; `part` absent means the score record, which
            # is the convention every downstream module filters on.
            attrs["part"] = str(record.part)
        if record.tag == TAG_FRAME_SPEC and len(record.payload) >= _ROW_DATA:
            # The pair is in the record's LAST incidence, exactly as in the
            # 2001-2005 era: a frameSpec carrying a `startTime` is 24 bytes, the
            # start time block first. Reading +0 regardless took the start time
            # as the entry pair -- "chain references missing entry 3584", 3584
            # EDU being a start time. 15 of the 10,465 corpus records are this
            # shape. See `_FRAME_START_TIME`.
            span = _frame_span(record.payload, len(record.payload) // _ROW_DATA, "little")
            if span is not None:
                start, end, start_time = span
                frame_fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
                    "startEntry": str(start),
                    "endEntry": str(end),
                }
                if start_time is not None:
                    frame_fields[_FRAME_START_TIME] = str(start_time)
                out.append(Record(tag="frameSpec", attrs=attrs, text="", fields=frame_fields))
        elif record.tag == TAG_MEAS_SPEC and len(record.payload) >= 8:
            out.append(
                Record(tag="measSpec", attrs=attrs, text="", fields=_meas_spec(record.payload))
            )
        elif record.tag == TAG_ARTIC_DEF:
            offset = _ARTIC_CHAR_OFFSET.get(len(record.payload))
            if offset is not None:
                out.append(
                    Record(
                        tag="articDef",
                        attrs=attrs,
                        text="",
                        fields={"charMain": str(_u16(record.payload, offset))},
                    )
                )
        elif record.tag == TAG_STAFF_SPEC and len(record.payload) >= _STAFF_TRANSPOSITION + 2:
            out.append(
                Record(tag="staffSpec", attrs=attrs, text="", fields=_staff_spec(record.payload))
            )
        elif record.tag == TAG_REPEAT_BACK and len(record.payload) >= 4:
            out.append(
                Record(tag="repeatBack", attrs=attrs, text="", fields=_repeat_back(record.payload))
            )
        elif record.tag == TAG_REPEAT_ENDING_START:
            # The bracket's geometry is not read; its presence is what says an
            # ending opens here, and `measSpec.barEnding` says where it closes.
            out.append(Record(tag="repeatEndingStart", attrs=attrs, text="", fields={}))
        elif record.tag == TAG_INST_USED and len(record.payload) >= _INST_SLOT:
            # One Record per slot, keyed by `inci`, because that is the shape
            # `groups.staff_order` reads -- and the shape a `.musx` writes.
            for inci in range(len(record.payload) // _INST_SLOT):
                staff = _u16(record.payload, inci * _INST_SLOT)
                out.append(
                    Record(
                        tag="instUsed",
                        attrs={**attrs, "inci": str(inci)},
                        text="",
                        fields={"inst": str(staff)},
                    )
                )
        elif record.tag == TAG_REPEAT_PASS_LIST and len(record.payload) >= 2:
            acts = _pass_list(record.payload)
            if acts:
                out.append(
                    Record(
                        tag="repeatPassList",
                        attrs=attrs,
                        text="",
                        # One pass stays a scalar, which is the shape the `.musx`
                        # reader writes too; `repeats._acts` accepts either.
                        fields={"act": acts[0] if len(acts) == 1 else acts},
                    )
                )
    return out


def _pass_list(payload: bytes) -> tuple[str, ...]:
    """Which passes an ending is taken on: a u16 array from +0, ended by a zero.

    **An array, not a value.** An ending marked "1., 2." is taken on both, and
    Finale stores one entry per pass; reading only +0 turns it into a "1."
    ending -- the same notes under a different repeat structure. The `.musx`
    reader has always allowed for this (`repeats._acts` accepts a tuple because
    "an ending taken on both the first and second pass writes it twice"); only
    the `.mus` side read a single value.

    The array reading agrees with the paired `.musx` on 40 of 40 records, where
    reading +0 alone agrees on 38. The two it fixes were invisible until oracle
    pairing stopped discarding the document that contains them.
    """
    out: list[str] = []
    for offset in range(0, len(payload) - 1, 2):
        value = _u16(payload, offset)
        if not value:
            break
        out.append(str(value))
    return tuple(out)


def _repeat_back(payload: bytes) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """`actuate` -- Finale's "Total Passes" -- at +2.

    A stored 0 is written as **no `actuate` at all**, the same omission
    convention as `measSpec.key` and `gfhold.clefID`: a `.musx` omits the
    element where the value is the default rather than writing it out. Across
    the paired corpus the two agree on every record that has one, and the `.mus`
    holds 0 exactly where the `.musx` omits it.
    """
    actuate = _u16(payload, 2)
    return {"actuate": str(actuate)} if actuate else {}


def _staff_spec(
    payload: bytes, order: ByteOrder = "little"
) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """Only the transposition's key alteration -- which is all written pitch needs.

    `transpose_key` uses `adjust` alone; `interval` is accepted "for symmetry
    with transpose_pitch and does not affect the key". So recovering `adjust`
    fixes the written key, and with it every transposing staff's note letters,
    without the octave the `.mus` does not store.

    **`interval` is deliberately left absent, which reads as 0.** That is
    correct for the written pitch the IR uses and *wrong* for the concert pitch
    `spell_note` also returns -- a `.mus` cannot supply it. See UNTRANSLATED.
    """
    raw = _u16(payload, _STAFF_TRANSPOSITION, order)
    magnitude = raw & _ALTERATION_MAGNITUDE
    adjust = -magnitude if raw & _ALTERATION_SIGN else magnitude
    if not adjust:
        return {}
    keysig = Record(tag="keysig", attrs={}, text="", fields={"adjust": str(adjust)})
    return {
        "transposition": Record(tag="transposition", attrs={}, text="", fields={"keysig": keysig})
    }


def _meas_spec(
    payload: bytes, order: ByteOrder = "little"
) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """`width, key, beats, divbeat` from offset zero, as `.musx` names them.

    A stored key of 0 is written as **no `keySig` at all**, which is what a
    `.musx` does: it omits the element rather than writing zero, and
    `locate_entries` reads an absent key as "inherit the previous measure's".
    Emitting `key="0"` instead would silently turn every inheriting measure into
    C major. Verified over the corpus: a `.musx` never writes `key="0"`, and
    `.mus` stores 0 exactly where the `.musx` omits the element.
    """
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        "beats": str(_u16(payload, 4, order)),
        "divbeat": str(_u16(payload, 6, order)),
    }
    key = _u16(payload, 2, order)
    if key:
        fields["keySig"] = Record(tag="keySig", attrs={}, text="", fields={"key": str(key)})
    if len(payload) > _MEAS_FLAGS + 1:
        # The **low byte of the u16 at +10**, not the byte at +10. ETF stores
        # `others` data as two-byte values, so the flags sit at +10 in a
        # little-endian file and +11 in a big-endian one. Reading +10 either way
        # took the high byte from all 37 big-endian DCL documents: their barline
        # nibble came out {0, 4, 6, 8, 12} where every little-endian file shows
        # {1, 2} -- normal and double -- and where those same documents show
        # {1, 2} at +11.
        flags = _u16(payload, _MEAS_FLAGS, order) & 0xFF
        for name, bit in _MEAS_REPEAT_BITS.items():
            if flags & bit:
                # Written as a bare presence, matching the `.musx`, where these
                # are empty elements rather than values.
                fields[name] = ""
        style = _MEAS_BARLINE_STYLES.get(flags >> 4)
        if style is not None:
            fields["barline"] = style
    return fields


def _staff_group(payload: bytes) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """The staff span, the bracket, and whether barlines join the group.

    Field order follows `etfspec.pdf`'s ETF `NG` record — `startInst endInst
    fullNameID fullXadj fullYadj | bracketType bracPos ...` — and every offset
    below was confirmed against the paired `.musx`, each with exactly one
    candidate.

    A text-block id of 0 means "no name", so it is written as **no field at
    all**, matching a `.musx` and the same omission convention as
    `measSpec.key`.
    """
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        "startInst": str(_u16(payload, 0)),
        "endInst": str(_u16(payload, 2)),
        "bracket": Record(
            tag="bracket",
            attrs={},
            text="",
            fields={"id": str(_u16(payload, _GROUP_BRACKET_ID))},
        ),
    }
    for name, offset in (("fullID", 4), ("abbrvID", _GROUP_ABBRV_ID)):
        number = _u16(payload, offset) if len(payload) >= offset + 2 else 0
        if number:
            fields[name] = str(number)
    if payload[_GROUP_BARLINE_BYTE] & _GROUP_BARLINE_BIT:
        fields["groupBarlineStyle"] = "group"
    return fields


def _gfhold(payload: bytes) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """`clefID` at +0, then a frame number per layer from +6.

    A frame of 0 means the layer is empty and is omitted, matching a `.musx`,
    where `locate_entries` reads an absent slot as "this layer holds nothing".
    """
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        "clefID": str(_u16(payload, 0)),
    }
    for layer, offset in ((1, 6), (2, 8)):
        frame = _u16(payload, offset)
        if frame:
            fields[f"frame{layer}"] = str(frame)
    return fields


_TUPLET_FIELDS = (("symbolicNum", 0), ("symbolicDur", 2), ("refNum", 4), ("refDur", 6))
"""ETF's documented field order, and the layout the payload actually has.

**Every corpus tuplet is 3:2 over a 512-EDU reference**, so no offset sweep can
tell these four apart -- any offset holding the right constant matches. What
pins them is the ETF order agreeing with the natural u16 reading at 0/2/4/6,
and then the end-to-end check: with these offsets every `.mus` sounded duration
matches its `.musx`, which a transposed or swapped pair would not survive
(swapping the two pairs inverts every ratio).
"""


def _lyric_records(
    record: MusDetailRecord, seen: dict[int, int], emitted: set[tuple[int, int]]
) -> list[Record]:
    """One `lyrDataVerse` Record per verse the entry sings.

    A `.mus` packs every verse into one record as consecutive 20-byte groups; a
    `.musx` writes one record per verse. Splitting here is what lets
    `lyrics_by_entry` read either container.

    **A `.mus` repeats an entry's assignments**, typically as two identical
    records, so the same (entry, verse) is emitted once and later copies are
    dropped. Corpus-wide, 697 of 2,524 assignments are such repeats and 23 of
    those disagree with the first about the syllable or the extension. None of
    the 23 falls in a document whose `.musx` can arbitrate, so keeping the first
    is unvalidated for exactly those; both orders match the oracle on all 971
    assignments it does cover.

    `inci` only has to make the identities distinct, so it counts assignments
    per entry.
    """
    out: list[Record] = []
    entnum = entry_key(record)
    groups = len(record.payload) // _LYRIC_GROUP
    for index in range(groups):
        at = index * _LYRIC_GROUP
        number = _u16(record.payload, at + _LYRIC_NUMBER)
        if not number:
            # An empty slot, not a verse.
            continue
        identity = (entnum, number)
        if identity in emitted:
            continue
        emitted.add(identity)
        fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
            "lyricNumber": str(number),
            "syll": str(_u16(record.payload, at + _LYRIC_SYLL)),
        }
        if _u16(record.payload, at + _LYRIC_WEXT):
            fields["wext"] = ""
        out.append(
            Record(
                tag="lyrDataVerse",
                attrs={"entnum": str(entnum), "inci": str(seen.get(entnum, 0))},
                text="",
                fields=fields,
            )
        )
        seen[entnum] = seen.get(entnum, 0) + 1
    return out


def _details_records(records: tuple[MusDetailRecord, ...]) -> list[Record]:
    out: list[Record] = []
    lyric_incidence: dict[int, int] = {}
    lyric_seen: set[tuple[int, int]] = set()
    artic_seen: set[tuple[int, int]] = set()
    for record in records:
        if record.tag == TAG_GFHOLD and len(record.payload) >= 10:
            out.append(
                Record(
                    tag="gfhold",
                    attrs={"cmper1": str(record.cmper1), "cmper2": str(record.cmper2)},
                    text="",
                    fields=_gfhold(record.payload),
                )
            )
        elif record.tag == TAG_ARTIC_ASSIGN and len(record.payload) >= 2:
            entnum = entry_key(record)
            definition = _u16(record.payload, _ARTIC_DEF_REFERENCE)
            # A `.mus` repeats an assignment the way it repeats a lyric: 23
            # corpus entries carry the same articDef twice. No `.musx` ever
            # does (0 of 11,404), so a repeat is a storage artifact and
            # emitting it would print the accent twice.
            if (entnum, definition) in artic_seen:
                continue
            artic_seen.add((entnum, definition))
            out.append(
                Record(
                    tag="articAssign",
                    attrs={"entnum": str(entnum), "inci": str(record.inci)},
                    text="",
                    fields={"articDef": str(definition)},
                )
            )
        elif record.tag == TAG_LYRIC_VERSE:
            out.extend(_lyric_records(record, lyric_incidence, lyric_seen))
        elif record.tag == TAG_STAFF_GROUP and len(record.payload) >= _GROUP_BARLINE_BYTE + 1:
            out.append(
                Record(
                    tag="staffGroup",
                    attrs={"cmper1": str(record.cmper1), "cmper2": str(record.cmper2)},
                    text="",
                    fields=_staff_group(record.payload),
                )
            )
        elif record.tag == TAG_TUPLET_DEF and len(record.payload) >= 8:
            out.append(
                Record(
                    tag="tupletDef",
                    attrs={"entnum": str(entry_key(record))},
                    text="",
                    fields={
                        name: str(_u16(record.payload, offset)) for name, offset in _TUPLET_FIELDS
                    },
                )
            )
    return out
