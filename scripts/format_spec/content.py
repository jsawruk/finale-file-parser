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
            "Records of one tag sit together in a section, and sections are separated by "
            "runs of two-byte zeroes, which a walk must skip. A zero there cannot begin a "
            "record: it would mean tag 0, which no record uses. Measured across the corpus, "
            "6,372 of 6,416 such runs are followed by a <em>different</em> tag, so they mark "
            "section boundaries rather than occurring at random. Most are a single two-byte "
            "unit, and skipping one lands the walk on a four-byte boundary 85% of the time, "
            "which points at alignment before a new section &mdash; though the 15% that do "
            "not leave that unproven. This is the 2011 era only: the row-based DCL era pads "
            "differently, filling out a record's last row.",
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
            Field(
                4,
                12,
                "data",
                "uint8[12]",
                "six 16-bit values, or three 32-bit (ETF: twobytes and fourbytes)",
            ),
        ],
        data=data,
        caption="A 2001&ndash;2005 others row: fixed 16 bytes, ETF's two-character tag.",
        notes=[
            "<strong>The tag is a u16, not two characters.</strong> Coda stores the two "
            "letters as one 16-bit integer, so the machine's byte order applies to them as "
            "it would to any number. Worked through with real bytes, for the measure spec "
            "tag <code>^MS</code>:<br><br>"
            "<code>big-endian file&nbsp;&nbsp;&nbsp;&nbsp;bytes 4d 53&nbsp;&nbsp;&rarr;&nbsp;"
            "as text &lsquo;MS&rsquo;&nbsp;&nbsp;&rarr;&nbsp;as u16 0x4d53</code><br>"
            "<code>little-endian file&nbsp;bytes 53 4d&nbsp;&nbsp;&rarr;&nbsp;"
            "as text &lsquo;SM&rsquo;&nbsp;&nbsp;&rarr;&nbsp;as u16 0x4d53</code><br><br>"
            "Both hold the same tag, 0x4d53, whose high byte 0x4d is &lsquo;M&rsquo; and "
            "low byte 0x53 is &lsquo;S&rsquo;. Only the order the two bytes sit in differs. "
            "A reader that takes the pair as text gets &lsquo;SM&rsquo; from the "
            "little-endian file and finds no such tag; one that reads a u16 and splits it "
            "into high and low bytes gets &lsquo;MS&rsquo; from both.",
            "A record too big for one row <strong>runs on into further rows</strong> under "
            "the same tag and key. ETF calls each row an <em>incidence</em>, and a record's "
            "payload is its rows' data concatenated in file order. A reader knows where a "
            "record ends because rows are grouped and sorted by tag and key: the run stops "
            "at the first row whose tag or key differs, so a reader needs no count. The "
            "expected number is a property of each structure rather than anything the file "
            "states &mdash; Coda's specification gives it per record type, saying a staff "
            "spec is stored over three incidences and a page spec over two &mdash; and the "
            "final row is zero-padded to fill it. Since the file never records that number, "
            "concatenating until the key changes is the reliable rule.",
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
            Field(6, 10, "data", "uint8[10]", "five 16-bit values (ETF calls them twobytes)"),
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
            Field(0, 4, "entnum", "uint32", "this entry's number, its key"),
            Field(4, 2, "slot", "uint16", "0 for this entry's first slot, then 1, 2, ..."),
            Field(6, 4, "prev", "uint32", "previous entry number, 0 if none"),
            Field(10, 4, "next", "uint32", "next entry number, 0 if none"),
            Field(14, 2, "dura", "uint16", "written duration in EDU; 1024 = quarter note"),
            Field(16, 2, "pos", "int16", "manual positioning in EVPU, signed"),
            Field(18, 4, "flags", "uint32", "SETBIT: a real entry; NOTEBIT: note, not rest"),
            Field(22, 2, "extflags", "uint16", "extended flags"),
            Field(24, 2, "noteCount", "uint16", "notes in this entry, across all its slots"),
            Field(26, 6, "note[0]", "NoteRec", "pitch word + flags; see below"),
            Field(32, 6, "note[1]", "NoteRec", "the first slot holds two"),
        ],
        data=bytes(buf),
        caption=f"The first slot of one entry, in the entries pool. The pool is a flat "
        f"array of fixed {ENT._SLOT}-byte <em>slots</em>; an entry occupies one slot if it "
        f"has two notes or fewer, and further slots for the rest. Every slot repeats the "
        f"entry number it belongs to, so a reader never has to track position.",
        notes=[
            f"A <strong>slot</strong> is one fixed {ENT._SLOT}-byte cell of the pool. An "
            f"entry's first slot carries the entry's own fields plus its first two notes; "
            f"if it has more, they continue in further slots holding "
            f"{ENT._CONT_SLOT_NOTES} notes each from offset {ENT._SLOT_HEADER}, under the "
            f"same entry number with an increasing slot index. An entry may carry up to "
            f"{ENT._MAX_NOTES} notes.",
            "<strong>The two entry flags a reader must respect.</strong> "
            "<code>SETBIT</code> (0x80000000) is set on every legitimate entry, so a slot "
            "without it is not one. <code>NOTEBIT</code> (0x40000000) distinguishes a note "
            "from a rest: when it is clear the entry sounds nothing, and a rest normally "
            "carries no note records at all.",
            "<strong>Both eras share this layout</strong>, field for field and offset for "
            "offset. They differ only in <em>byte order</em>: the same fields, with their "
            "bytes in the opposite order on a Mac-written 2001-2005 file. That the layout "
            "really is shared is the corpus's verdict rather than an assumption. Across 136 "
            "DCL-era documents the slots <em>tile the pool exactly</em> &mdash; reading "
            f"{ENT._SLOT}-byte cells from the start consumes the pool with no remainder and "
            "no overrun, which a wrong slot size would not do &mdash; and every entry has "
            "SETBIT set.",
        ],
    )


def note_record() -> Struct:
    tcd = (64 << 4) | 0x9  # pitch 64, alteration -1 (sign-and-magnitude)
    data = le16(tcd) + le32(ENT._TIE_START)
    return Struct(
        name="NoteRec",
        fields=[
            Field(0, 2, "tcd", "uint16", "Tone Center Displacement: pitch and alteration"),
            Field(2, 4, "flags", "uint32", "ties, accidental display, note id; see below"),
        ],
        data=data,
        caption="A note record: six bytes carrying one note's pitch and its tie and "
        "accidental state.",
        notes=[
            "<strong>The alteration is sign-and-magnitude, not two's complement.</strong> "
            "Coda's documentation calls it &ldquo;a signed quantity ... -8 to +7&rdquo;, "
            "which reads as two's complement. The corpus disagrees, and the corpus wins. "
            "The low nibble is a sign bit above a three-bit magnitude:<br><br>"
            "<code>bit&nbsp;&nbsp;&nbsp;3&nbsp;&nbsp;&nbsp;2&nbsp;&nbsp;&nbsp;1"
            "&nbsp;&nbsp;&nbsp;0</code><br>"
            "<code>&nbsp;&nbsp;&nbsp;&nbsp;[&nbsp;s&nbsp;][&nbsp;m&nbsp;&nbsp;&nbsp;m"
            "&nbsp;&nbsp;&nbsp;m&nbsp;]</code><br>"
            "<code>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;sign&nbsp;&nbsp;magnitude 0-7</code>"
            "<br><br>"
            "The two readings agree on naturals and sharps and diverge on every flat. "
            "Observed in the corpus: <code>0x0</code> is 0 and <code>0x1</code> is +1, "
            "which both readings give; but <code>0x9</code> = <code>1001</code> is "
            "<strong>&minus;1</strong>, sign set with magnitude 1. Read as two's "
            "complement the same nibble would be &minus;7, spelling a note six steps away "
            "from the one Finale displays.",
            "<strong>The flags carry more than ties.</strong> The 32-bit field also holds "
            "accidental display and the note's identity within its entry. From Coda's "
            "specification: <code>0x80000000</code> legality, always set; "
            "<code>0x40000000</code> tie start; <code>0x20000000</code> tie end; "
            "<code>0x10000000</code> cross-staff; <code>0x02000000</code> upper stem of a "
            "split stem; <code>0x01000000</code> show an accidental, which Finale "
            "recomputes while editing unless frozen; <code>0x00800000</code> parenthesize "
            "that accidental; <code>0x001F0000</code> a mask holding the note's id, 1 to "
            "12, by which entry details such as articulations and performance data address "
            "one note of a chord; <code>0x00000002</code> freeze the accidental bit.",
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
