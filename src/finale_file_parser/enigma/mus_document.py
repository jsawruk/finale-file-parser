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
| details | `lyrDataVerse` (1108) | `lyricNumber`, `syll`, `wext`, per 20-byte group |
| details | `articAssign` (1009) | `articDef` |
| others | `articDef` (121) | `charMain` — at +0 (2011) or +2 (2012) |
| others | `repeatBack` (203) | `actuate` — Finale's "Total Passes" |
| others | `repeatEndingStart` (204) | presence only; the bracket's extent comes from `barEnding` |
| others | `repeatPassList` (206) | `act` — which pass the ending is taken on |
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
    TAG_MEAS_SPEC,
    TAG_REPEAT_BACK,
    TAG_REPEAT_ENDING_START,
    TAG_REPEAT_PASS_LIST,
    TAG_STAFF_SPEC,
    MusOther,
    read_mus_others,
)
from finale_file_parser.enigma.mus_payload import read_mus_streams
from finale_file_parser.version import mus as mus_header

__all__ = ["UNTRANSLATED", "read_mus_document"]

UNTRANSLATED = (
    "staffSpec whole-octave transpositions: a transposition that is an exact "
    "octave leaves Finale's residue at zero and the key unchanged, so the staff "
    "is recorded as though it did not transpose at all -- nothing distinguishes "
    "a double bass written at sounding pitch from a concert staff. Those staves "
    "come out an octave from the .musx (845 notes, all interval 7). Every "
    "transposition WITH a residue is now recovered: the octaves Finale folds "
    "into harm_lev are undone by written_octave_correction. See "
    "docs/formats/transposition-octave.md.",
    "staffSpec part names: the reference at +30/+32 does not resolve to a text "
    "block -- the best candidate chain matches 16 of 59 staves, and by hand it "
    "picks a trumpet block for a saxophone part. The .musx is only a fuzzy oracle "
    "here -- it names the same staff 'Tenor Sax' where the .mus says 'Tenor "
    "Saxophone', synonyms rather than a disagreement -- so a match must tolerate "
    "abbreviation. Parts fall back to positional names rather than to a plausible "
    "wrong one. See docs/formats/mus-binary-notes.md.",
    "Instrument-derived clefs: where a gfhold stores clefID 0 it means 'use the "
    "staff's defaultClef', and for some staves the .mus stores 0 there too while "
    "the .musx materialises a real clef. Those measures come out treble. Same "
    "root cause as the transposition gap above -- the value lives with the "
    "instrument, not in the file.",
    "measSpec display time signatures (useDisplayTimesig, dispBeats, dispDivbeat).",
    "Final barlines: measSpec's flags byte at +10 holds the barline style in its "
    "high nibble, and 1 (normal) and 2 (double) ARE read -- see enigma.barlines. "
    "A final bar is not: nibble 3 is the obvious reading and it does not occur "
    "once in 4,427 measures across 99 corpus .mus documents, so nothing checks a "
    "guess. A .mus therefore ends a piece with an ordinary barline where the "
    ".musx draws a final one.",
    "Staff group names: a staffGroup's fullID IS recovered, but resolving it "
    "needs the textBlock -> blockText chain, which a .mus does not supply -- "
    "the same missing chain as staffSpec part names. Groups therefore come out "
    "unnamed rather than labelled with a raw block number; 4 of the 14 paired "
    "documents with groups differ from their .musx in nothing else.",
    "Staff layout order (instUsed): a .musx lists its staves in the order the "
    "score lays them out, which is not always ascending. The .mus tag for that "
    "list is unidentified and the corpus cannot identify it -- every paired "
    "document numbers its slots and staves alike, so no pair separates a right "
    "guess from a wrong one. Staves therefore come out in numeric order, which "
    "is right for every document there is evidence about. Staff groups are read "
    "through that order; see enigma.groups.",
    "Text repeats (Fine, D.C. al Coda): the .musx reading is implemented, the "
    ".mus one is not. Exactly one paired document carries a text repeat, with "
    "two assignments, and a key set that small matches several tags by chance -- "
    "so no .mus tag can be identified from this corpus. A .mus therefore exports "
    "no markings. See enigma.jumps.",
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
    "gfhold frame3-4: layers 3 and 4. Frames 1 and 2 are at payload +6 and +8, "
    "confirmed against the corpus; no corpus .musx carries a frame3 or frame4, so "
    "the next two slots are a guess this does not make. A document using layer 3 "
    "or 4 therefore leaves those entries unplaced, which locate_entries rejects "
    "as orphans -- a loud failure rather than a silent misplacement.",
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
            malformed. DCL-era files (2001-2005) raise here.
    """
    others = read_mus_others(path)
    details = read_mus_details(path)
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


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 2], "little")


def _u32(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 4], "little")


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


def _clef_def(entry: bytes, stride: int) -> Record:
    """One clef-table entry.

    A zero `clefChar` or `shapeID` is written as an absent field, not as "0":
    `clef_definitions` reads absent as "there is no character/shape", and a
    clef with neither is what makes `Clef.sign` report UNKNOWN rather than
    inventing a G clef.
    """
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {}
    for name, offset in _CLEF_FIELD_OFFSETS[stride].items():
        raw = entry[offset : offset + 2]
        value = int.from_bytes(raw, "little", signed=name in _CLEF_SIGNED)
        if value or name in _CLEF_SIGNED:
            fields[name] = str(value)
    return Record(tag="clefDef", attrs={}, text="", fields=fields)


def _others_records(records: tuple[MusOther, ...]) -> list[Record]:
    out: list[Record] = []
    for record in records:
        attrs = {"cmper": str(record.cmper)}
        if record.part:
            # A part-variant record; `part` absent means the score record, which
            # is the convention every downstream module filters on.
            attrs["part"] = str(record.part)
        if record.tag == TAG_FRAME_SPEC and len(record.payload) >= 8:
            out.append(
                Record(
                    tag="frameSpec",
                    attrs=attrs,
                    text="",
                    fields={
                        "startEntry": str(_u32(record.payload, 0)),
                        "endEntry": str(_u32(record.payload, 4)),
                    },
                )
            )
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
        elif record.tag == TAG_REPEAT_PASS_LIST and len(record.payload) >= 2:
            act = _u16(record.payload, 0)
            if act:
                out.append(
                    Record(tag="repeatPassList", attrs=attrs, text="", fields={"act": str(act)})
                )
    return out


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


def _staff_spec(payload: bytes) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """Only the transposition's key alteration -- which is all written pitch needs.

    `transpose_key` uses `adjust` alone; `interval` is accepted "for symmetry
    with transpose_pitch and does not affect the key". So recovering `adjust`
    fixes the written key, and with it every transposing staff's note letters,
    without the octave the `.mus` does not store.

    **`interval` is deliberately left absent, which reads as 0.** That is
    correct for the written pitch the IR uses and *wrong* for the concert pitch
    `spell_note` also returns -- a `.mus` cannot supply it. See UNTRANSLATED.
    """
    raw = _u16(payload, _STAFF_TRANSPOSITION)
    magnitude = raw & _ALTERATION_MAGNITUDE
    adjust = -magnitude if raw & _ALTERATION_SIGN else magnitude
    if not adjust:
        return {}
    keysig = Record(tag="keysig", attrs={}, text="", fields={"adjust": str(adjust)})
    return {
        "transposition": Record(tag="transposition", attrs={}, text="", fields={"keysig": keysig})
    }


def _meas_spec(payload: bytes) -> dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]]:
    """`width, key, beats, divbeat` from offset zero, as `.musx` names them.

    A stored key of 0 is written as **no `keySig` at all**, which is what a
    `.musx` does: it omits the element rather than writing zero, and
    `locate_entries` reads an absent key as "inherit the previous measure's".
    Emitting `key="0"` instead would silently turn every inheriting measure into
    C major. Verified over the corpus: a `.musx` never writes `key="0"`, and
    `.mus` stores 0 exactly where the `.musx` omits the element.
    """
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        "beats": str(_u16(payload, 4)),
        "divbeat": str(_u16(payload, 6)),
    }
    key = _u16(payload, 2)
    if key:
        fields["keySig"] = Record(tag="keySig", attrs={}, text="", fields={"key": str(key)})
    if len(payload) > _MEAS_FLAGS:
        for name, bit in _MEAS_REPEAT_BITS.items():
            if payload[_MEAS_FLAGS] & bit:
                # Written as a bare presence, matching the `.musx`, where these
                # are empty elements rather than values.
                fields[name] = ""
        style = _MEAS_BARLINE_STYLES.get(payload[_MEAS_FLAGS] >> 4)
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
