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
from finale_file_parser.enigma.mus_details import TAG_GFHOLD, MusDetailRecord, read_mus_details
from finale_file_parser.enigma.mus_entries import read_mus_entry_records
from finale_file_parser.enigma.mus_others import (
    TAG_FRAME_SPEC,
    TAG_MEAS_SPEC,
    MusOther,
    read_mus_others,
)

__all__ = ["UNTRANSLATED", "read_mus_document"]

UNTRANSLATED = (
    "staffSpec: part names and staff transposition. The record is located (others "
    "tag 231) but the transposition's octave is provably NOT in it -- staves the "
    ".musx gives intervals an octave apart have byte-identical .mus payloads, "
    "differing only in the .musx's instUuid. So transposing staves cannot be "
    "spelled correctly from a .mus until an instrument table is found, if one "
    "exists. Parts fall back to positional names. See docs/formats/"
    "mus-binary-notes.md.",
    "clefOptions: the clef definition table lives in the options pool, whose "
    "payloads are not decoded, so no clef is emitted at all.",
    "measSpec display time signatures (useDisplayTimesig, dispBeats, dispDivbeat).",
    "gfhold frame3-4: layers 3 and 4. Frames 1 and 2 are at payload +6 and +8, "
    "confirmed against the corpus; no corpus .musx carries a frame3 or frame4, so "
    "the next two slots are a guess this does not make. A document using layer 3 "
    "or 4 therefore leaves those entries unplaced, which locate_entries rejects "
    "as orphans -- a loud failure rather than a silent misplacement.",
    "tupletDef: tuplets read as their written durations.",
)
"""What a `.mus`-derived score does not yet carry, and the consequence of each.

Kept as data rather than prose so a caller can surface it, and so closing one
gap is a visible deletion here.
"""

_VERSION = "mus"
"""`EnigmaDocument.version` is the EnigmaXML schema version, which a `.mus` has
no equivalent of. A distinct value is better than a plausible-looking lie."""

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
        options=OptionsPool(records=_EMPTY),
        others=OthersPool(records=tuple(_others_records(others))),
        details=DetailsPool(records=tuple(_details_records(details))),
        entries=EntriesPool(records=read_mus_entry_records(path)),
        texts=TextsPool(records=_EMPTY),
    )


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 2], "little")


def _u32(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 4], "little")


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
    return out


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


def _details_records(records: tuple[MusDetailRecord, ...]) -> list[Record]:
    out: list[Record] = []
    for record in records:
        if record.tag != TAG_GFHOLD or len(record.payload) < 10:
            continue
        out.append(
            Record(
                tag="gfhold",
                attrs={"cmper1": str(record.cmper1), "cmper2": str(record.cmper2)},
                text="",
                fields=_gfhold(record.payload),
            )
        )
    return out
