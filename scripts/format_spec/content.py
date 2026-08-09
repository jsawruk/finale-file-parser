"""The specification's narrative sections and structure definitions.

Every constant here is imported from the parser rather than retyped, so a
layout in this document cannot silently drift from the code that reads it.
"""

from __future__ import annotations

from finale_file_parser.enigma import mus_entries as ENT
from finale_file_parser.enigma import mus_others as OTH
from finale_file_parser.enigma import mus_payload as PAY
from finale_file_parser.version import mus as MUSHDR

from .hexview import Field, Struct

# --------------------------------------------------------------------------
# Synthetic byte builders. No corpus bytes appear anywhere in this document:
# the corpus is licensed third-party music. Every dump below is constructed
# here, which also lets each example isolate the field under discussion.
# --------------------------------------------------------------------------


def le16(v: int) -> bytes:
    return v.to_bytes(2, "little")


def le32(v: int) -> bytes:
    return v.to_bytes(4, "little")


def be16(v: int) -> bytes:
    return v.to_bytes(2, "big")


def mus_file_header() -> Struct:
    """The first 0xA0 bytes of a .mus file."""
    buf = bytearray(b"\x00" * MUSHDR.MUS_METADATA_SIZE)
    buf[0:4] = b"\x00\x00\x00\x00"
    banner = b"Finale(R) 2005 for Windows\x00"
    buf[MUSHDR.BANNER_OFFSET : MUSHDR.BANNER_OFFSET + len(banner)] = banner
    # created stamp: date, application tag, platform tag
    buf[0x66:0x6A] = le32(0x00093A80)
    buf[0x70:0x74] = b"FIN\x00"
    buf[0x74:0x78] = b"WIN\x00"
    # modified stamp
    buf[0x8C:0x90] = le32(0x00093B10)
    buf[0x96:0x9A] = b"FIN\x00"
    buf[0x9A:0x9E] = b"WIN\x00"
    return Struct(
        name="MusFileHeader",
        fields=[
            Field(
                MUSHDR.BANNER_OFFSET,
                MUSHDR.BANNER_FIELD_SIZE,
                "banner",
                "char[64]",
                "NUL-terminated; tail of a previous longer banner may follow",
            ),
            Field(0x66, 4, "created.date", "uint32", "creation date stamp"),
            Field(0x70, 4, "created.app", "char[4]", "application tag, e.g. FIN"),
            Field(0x74, 4, "created.platform", "char[4]", "MAC or WIN"),
            Field(0x8C, 4, "modified.date", "uint32", "last-modified date stamp"),
            Field(0x96, 4, "modified.app", "char[4]", "application tag"),
            Field(0x9A, 4, "modified.platform", "char[4]", "MAC or WIN"),
        ],
        data=bytes(buf),
        caption="A synthetic .mus header. The banner is the primary version evidence; "
        "the two provenance stamps say which application and platform wrote the file.",
        notes=[
            "The banner field is fixed-size and is <em>not</em> zero-filled when Finale "
            "rewrites it, so a shorter banner can leave the tail of a previous, longer one "
            "behind. Everything from the first NUL onward must be discarded.",
        ],
    )


def dcl_pool_record() -> Struct:
    """One link of the DCL-era pool chain."""
    stream = bytes.fromhex("00040ec5b39a2f")
    data = le16(PAY.POOL_OTHERS) + le32(10 + len(stream)) + le32(0x0044219C) + stream
    return Struct(
        name="DclPoolRecord",
        fields=[
            Field(0, 2, "kind", "uint16", "15 others, 16 details, 17 entries, 18 text"),
            Field(2, 4, "length", "uint32", "whole record, this 10-byte header included"),
            Field(
                6,
                4,
                "checksum",
                "uint32",
                "omitted entirely when the pool is empty (length == 6)",
            ),
            Field(10, len(stream), "stream", "uint8[]", "PKWARE DCL data, length - 10 bytes"),
        ],
        data=data,
        caption="A DCL-era pool record. Records lie end to end from 0x200 to the "
        "last byte of the file, with no gaps.",
        notes=[
            "<strong>length counts its own header.</strong> The chain is walked by adding "
            "length to the current position. This is also why a fixed 0x20A works as "
            "&ldquo;where the first stream starts&rdquo;: 0x200 plus the ten-byte header.",
            "A length of exactly 6 means the pool is <strong>empty</strong> &mdash; kind and "
            "length and nothing else, no checksum and no stream.",
        ],
    )


def mus2011_record() -> Struct:
    """A 2011-era self-identifying record."""
    payload = bytes.fromhex("6000 5802 0400 0100 0000 0000".replace(" ", ""))
    data = (
        le16(OTH.TAG_MEAS_SPEC)
        + le16(1)
        + le16(0)
        + le32(len(payload))
        + payload
        + le32(len(payload))
    )
    return Struct(
        name="MusRecord2011",
        fields=[
            Field(0, 2, "tag", "uint16", "record type; .musx names the same types"),
            Field(2, 2, "cmper", "uint16", "the (n) in an ETF ^XX(n) &mdash; the record's key"),
            Field(4, 2, "part", "uint16", "0 for the score, then 1, 2, ... per linked part"),
            Field(6, 4, "length", "uint32", "payload size in bytes"),
            Field(10, len(payload), "payload", "uint8[]", "length bytes"),
            Field(10 + len(payload), 4, "trailer", "uint32", "the length again"),
        ],
        data=data,
        caption="A 2011-era record: tag 176 (measSpec), key 1, score part. One record "
        f"occupies {OTH._HEADER} + length + {OTH._EXTRA_LENGTH} bytes.",
        notes=[
            "These records are <strong>self-identifying</strong>: each carries its own key, "
            "so nothing outside the record is needed to address it &mdash; no directory, no "
            "key array, no positional convention.",
            "Records of one tag sit together in a section, and sections may be separated "
            "by two-byte zero padding, which a walk must skip. The padding is a consequence "
            "of how a record is stored rather than a delimiter: a record is written into "
            "whole rows, and its last row is filled out with zeroes.",
        ],
    )


def dcl_others_row() -> Struct:
    """A DCL-era others row."""
    data = le16(1) + b"SM" + bytes.fromhex("600058020400010000000000")
    return Struct(
        name="DclOthersRow",
        fields=[
            Field(0, 2, "cmper", "uint16", "the (n) in an ETF ^XX(n)"),
            Field(2, 2, "tag", "uint16", "two characters stored as a u16"),
            Field(4, 12, "data", "uint8[12]", "ETF's 6 twobyte values (or 3 fourbytes)"),
        ],
        data=data,
        caption="A 2001&ndash;2005 others row: fixed 16 bytes, ETF's two-character tag.",
        notes=[
            "<strong>The tag is a u16, not two bytes.</strong> On a little-endian file its "
            "characters come out reversed: <code>^MS</code> is written <code>SM</code>, "
            "and <code>^&amp;a</code> is written <code>a&amp;</code>.",
            "A record too big for one row <strong>runs on into further rows</strong> under "
            "the same tag and key. ETF calls each row an <em>incidence</em>, and a record's "
            "payload is its rows' data concatenated in file order. A reader knows where a "
            "record ends because rows are grouped and sorted by tag and key: the run stops "
            "at the first row whose tag or key differs. How many rows to expect is fixed by "
            "the structure &mdash; a staff spec takes three, a page spec two &mdash; and the "
            "last row is zero-padded to fill it.",
        ],
    )


def dcl_details_row() -> Struct:
    data = le16(1) + le16(3) + b"FG" + bytes.fromhex("01000000000000000000")
    return Struct(
        name="DclDetailsRow",
        fields=[
            Field(0, 2, "cmper1", "uint16", "first key"),
            Field(2, 2, "cmper2", "uint16", "second key"),
            Field(4, 2, "tag", "uint16", "two characters as a u16"),
            Field(6, 10, "data", "uint8[10]", "ETF's 5 twobytes"),
        ],
        data=data,
        caption="A details row. Two keys rather than one &mdash; details are addressed by a "
        "pair, which is how a record hangs off a (staff, measure) intersection.",
    )


def entry_first_slot() -> Struct:
    """The first slot of an entry."""
    buf = bytearray(ENT._SLOT)
    buf[0:4] = le32(101)  # entnum
    buf[4:6] = le16(0)  # slot index
    buf[6:10] = le32(100)  # prev
    buf[10:14] = le32(102)  # next
    buf[14:16] = le16(1024)  # dura: quarter note
    buf[16:18] = le16(0)  # pos
    buf[18:22] = le32(ENT._SETBIT | ENT._NOTEBIT)
    buf[22:24] = le16(0)
    buf[24:26] = le16(2)  # note count
    buf[26:28] = le16((60 << 4) | 0x0)  # TCD: pitch 60, no alteration
    buf[28:32] = le32(0)
    buf[32:34] = le16((64 << 4) | 0x1)  # TCD: pitch 64, +1
    buf[34:38] = le32(0)
    return Struct(
        name="EntrySlotFirst",
        fields=[
            Field(0, 4, "entnum", "uint32", "the (n) in ETF ^eE(n)"),
            Field(4, 2, "slot", "uint16", "0 for an entry's first slot, then 1, 2, ..."),
            Field(6, 4, "prev", "uint32", "previous entry number, 0 if none"),
            Field(10, 4, "next", "uint32", "next entry number, 0 if none"),
            Field(14, 2, "dura", "uint16", "written duration in EDU; 1024 = quarter note"),
            Field(16, 2, "pos", "int16", "manual positioning in EVPU, signed"),
            Field(18, 4, "flags", "uint32", "SETBIT 0x80000000 always; NOTEBIT 0x40000000"),
            Field(22, 2, "extflags", "uint16", "extended flags"),
            Field(24, 2, "noteCount", "uint16", "how many note records follow, across slots"),
            Field(26, 6, "note[0]", "NoteRec", "TCD (2) + note flag (4)"),
            Field(32, 6, "note[1]", "NoteRec", "the first slot holds two"),
        ],
        data=bytes(buf),
        caption=f"An entry's first slot. The pool is a flat array of fixed {ENT._SLOT}-byte "
        "slots, each tagged with the entry it belongs to.",
        notes=[
            f"Continuation slots (index &gt; 0) carry only notes, {ENT._CONT_SLOT_NOTES} per "
            f"slot, from offset {ENT._SLOT_HEADER}. An entry may carry up to "
            f"{ENT._MAX_NOTES} notes.",
            "<strong>Both eras share this layout.</strong> What differs is only which way "
            "round the integers are written. That the layout really is shared is the "
            "corpus's verdict, not an assumption: across 136 DCL-era documents the slots "
            "tile the pool exactly and every entry has SETBIT set.",
        ],
    )


def note_record() -> Struct:
    tcd = (64 << 4) | 0x9  # pitch 64, alteration -1 (sign-and-magnitude)
    data = le16(tcd) + le32(ENT._TIE_START)
    return Struct(
        name="NoteRec",
        fields=[
            Field(0, 2, "tcd", "uint16", "upper 12 bits pitch (signed), low nibble alteration"),
            Field(2, 4, "flags", "uint32", "TIE_START 0x40000000, TIE_END 0x20000000"),
        ],
        data=data,
        caption="A note record: six bytes, two of them carrying both pitch and alteration.",
        notes=[
            "<strong>The alteration is sign-and-magnitude, not two's complement.</strong> "
            "Bit 3 is the sign. <code>eeppd.txt</code> describes it as &ldquo;a signed "
            "quantity ... -8 to +7&rdquo;, which reads as two's complement; the corpus "
            "disagrees, and the corpus wins. Observed: 0x0 &rarr; 0, 0x1 &rarr; +1, "
            "0x9 &rarr; &minus;1.",
        ],
    )


ALL_STRUCTS = {
    "mus_file_header": mus_file_header,
    "dcl_pool_record": dcl_pool_record,
    "mus2011_record": mus2011_record,
    "dcl_others_row": dcl_others_row,
    "dcl_details_row": dcl_details_row,
    "entry_first_slot": entry_first_slot,
    "note_record": note_record,
}
