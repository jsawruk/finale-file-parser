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
| others | `measSpec` (176) | `keySig.key`, `beats`, `divbeat` |
| details | `gfhold` (1044) | `clefID`, `frame1`, `frame2` |
| options | `clefOptions` (109) | the clef table: `adjust`, `clefChar`, `clefYDisp`, `shapeID` |
| details | `tupletDef` (1072) | `symbolicNum`, `symbolicDur`, `refNum`, `refDur` |
| others | `staffSpec` (231) | `transposition.keysig.adjust` only — see below |

Every field above is confirmed against paired `.musx` files; see
`docs/formats/mus-binary-notes.md` for the evidence behind each.
"""

from __future__ import annotations

import os

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
    TAG_GFHOLD,
    TAG_TUPLET_DEF,
    MusDetailRecord,
    entry_key,
    read_mus_details,
)
from finale_file_parser.enigma.mus_entries import read_mus_entry_records
from finale_file_parser.enigma.mus_others import (
    OPTIONS_CMPER,
    TAG_CLEF_OPTIONS,
    TAG_FRAME_SPEC,
    TAG_MEAS_SPEC,
    TAG_STAFF_SPEC,
    MusOther,
    read_mus_others,
)
from finale_file_parser.version import mus as mus_header

__all__ = ["UNTRANSLATED", "read_mus_document"]

UNTRANSLATED = (
    "staffSpec transposition octave: Finale normalises a staff's transposition into "
    "a residue of -4..+2 and keeps the octaves separately, and the .mus stores "
    "only the residue -- so staves whose transpositions differ by an octave hold "
    "byte-identical payloads. The octave is absent from the file rather than "
    "hidden in it, and a .mus therefore fixes a transposing staff's written pitch "
    "only up to an octave. The key alteration IS recovered, which is all the "
    "written pitch needs otherwise, so note letters and accidentals are right; "
    "what stays wrong is the octave on those staves, and the concert pitch "
    "spell_note returns alongside the written one. See harm_lev_octave_shift and "
    "docs/formats/mus-binary-notes.md.",
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

_STAFF_TRANSPOSITION = 20
"""Offset of `staffSpec`'s `transposition` field, per ETF's documented field
order (`... topBarlineOffset transposition instflag dw_wRest ...`)."""

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
        texts=TextsPool(records=_EMPTY),
    )


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 2], "little")


def _u32(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 4], "little")


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
        elif record.tag == TAG_STAFF_SPEC and len(record.payload) >= _STAFF_TRANSPOSITION + 2:
            out.append(
                Record(tag="staffSpec", attrs=attrs, text="", fields=_staff_spec(record.payload))
            )
    return out


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


def _details_records(records: tuple[MusDetailRecord, ...]) -> list[Record]:
    out: list[Record] = []
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
