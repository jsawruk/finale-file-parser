"""Read the entry pool out of a legacy `.mus` file.

Produces the same `Entry`/`Note`/`Duration` types the `.musx` pipeline builds, so
downstream code (`spell_note`, `decode_key`, …) attaches unchanged. That parity is
the whole point: the container differs, the music does not.

The record layout is Coda's, documented in `docs/eeppd.txt`, and confirmed
field-by-field against the paired `.musx` for 12 documents / 3,198 entries — entry
numbers, note counts and durations all agree exactly. Layout, little-endian:

The pool is a flat array of fixed 38-byte **slots**, each tagged with the entry it
belongs to:

    0-3   entnum        the entry this slot belongs to (the `(n)` in ETF `^eE(n)`)
    4-5   slot index    0 for an entry's first slot, then 1, 2, ...
    6-37  payload       32 bytes, laid out per slot index

First slot (index 0):

    6-9    prev          previous entry number, 0 if none
    10-13  next          next entry number, 0 if none
    14-15  dura          written duration in EDU (1024 = quarter note)
    16-17  pos           manual positioning in EVPU, signed
    18-21  entry flag    SETBIT 0x80000000 always set; NOTEBIT 0x40000000
    22-23  extended flag
    24-25  note count
    26-37  notes 0-1     two note records

Continuation slots (index > 0) carry only notes, five per slot, from offset 6.

A note record is 6 bytes: TCD (2) then note flag (4). The TCD's upper twelve bits
are the pitch (signed) and its low nibble the alteration -- stored **sign and
magnitude**, bit 3 being the sign, not two's complement. `eeppd.txt` describes the
alteration as "a signed quantity ... -8 to +7", which reads as two's complement;
the corpus disagrees, and the corpus wins. Observed: 0x0 -> 0, 0x1 -> +1,
0x9 -> -1.

Scope: the 2011/2012 era, whose payload separates pools into their own zlib
streams. DCL-era files (2001-2005) pack everything into one stream with no known
pool delimiters, so this raises for them rather than guessing.
"""

from __future__ import annotations

import os

from finale_file_parser.enigma.document import Record
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import read_mus_streams
from finale_file_parser.enigma.music import Duration, Entry, duration_from_edu, read_entry

__all__ = ["harm_lev_octave_shift", "read_mus_entries", "read_mus_entry_records"]

_SLOT = 38
_SLOT_HEADER = 6
"""entnum (4) + slot index (2) precede every slot's payload."""
_FIRST_SLOT_NOTES = 2
"""Notes carried by an entry's first slot, after its fixed fields."""
_CONT_SLOT_NOTES = (_SLOT - _SLOT_HEADER) // 6
"""Notes carried by each continuation slot (five)."""
_FIRST_NOTE_OFFSET = 26
_NOTE = 6
_MAX_NOTES = 12
"""eeppd.txt: an entry can carry at most twelve notes."""

_SETBIT = 0x80000000
"""Set on every legal entry and every legal note record."""
_NOTEBIT = 0x40000000
"""Set for a note, clear for a rest -- but see `_entry_record`: NOTEBIT alone
does not decide whether an entry has pitch content."""
_FLOATREST = 0x01000000
"""A "floating" rest: it sits at the staff midline and has no pitch content."""
_GRACENOTE = 0x00800000
"""eeppd.txt: set for grace notes. Surfaced as a `graceNote` field so the
duration model gives them zero sounded time, as it does for a `.musx`."""
_TIE_START = 0x40000000
_TIE_END = 0x20000000

_TCD_ALT_BITS = 4
"""The TCD's low nibble is the alteration; the upper twelve bits are the pitch."""


def harm_lev_octave_shift(interval: int) -> int:
    """Octave correction to align a `.mus` `harm_lev` with the `.musx` convention.

    On a **transposing staff** the two containers place `harm_lev` in different
    octaves. Add this to a `.mus` note's `harm_lev` to get the value the `.musx`
    pipeline reports for the same note. `interval` is the staff transposition's
    diatonic interval (`StaffTransposition.interval`, 7 = one octave); pass 0 for
    a non-transposing staff, where the shift is 0.

    `read_mus_entries` does **not** apply this, because the entry pool carries no
    staff information. `read_mus_document` does not either, because the `.mus`
    cannot supply the `interval` this needs -- see below. Apply it at the point
    where the staff transposition is known, which in practice means a `.musx`.

    **This is the octave count of the normalised transposition, not an empirical
    fudge.** Finale folds the sounding interval into a residue in -4..+2 and keeps
    the octaves separately; `.mus` stores only the residue. Writing the sounding
    direction as `d = -interval`, the residue is `d - 7 * octaves` and this
    function returns `7 * octaves`:

        interval  sounding  residue  octaves  shift
               0         0        0        0      0
               1        -1       -1        0      0
               4        -4       -4        0      0
               5        -5        2       -1     -7
               7        -7        0       -1     -7
               8        -8       -1       -1     -7
              12       -12        2       -2    -14

    So a major 6th down is stored as a minor 3rd up less an octave, and a major
    9th down as a major 2nd down less an octave. That is why the octave moves at
    interval 5 rather than 7 -- the `+ 2` below is the normalisation boundary, not
    a fitted constant. Earlier revisions of this docstring called the rule
    empirical and the boundary unexplained; it is neither.

    The consequence for `.mus` is structural: staves whose transpositions share a
    residue store **byte-identical** `staffSpec` payloads -- intervals 0 and 7
    both store 0x0000, 1 and 8 both 0x0042, 5 and 12 both 0x0F83. The octave is
    not hidden in the file, it is absent from it, so a `.mus` determines a
    transposing staff's written pitch only up to an octave. Finale pinned it down
    when it wrote the `.musx`, using its instrument definition.

    Verified across every confirmed `.mus`/`.musx` pair: applying this makes
    30,888 of 30,891 notes agree exactly. See `docs/formats/mus-binary-notes.md`.
    """
    return -7 * ((interval + 2) // 7)


def read_mus_entry_records(path: str | os.PathLike[str]) -> tuple[Record, ...]:
    """Return the entry pool as generic `entry` Records, in stream order.

    The same shape `parse_enigma` produces for a `.musx`, so everything built
    over that model -- `read_entry`, `entry_chain`, `locate_entries` -- reads a
    `.mus` unchanged. `read_mus_entries` is this composed with `read_entry`,
    which is what keeps the two containers' entry semantics from drifting: there
    is one decode, not one per container.

    Records carry what the pool actually holds -- `entnum`/`prev`/`next`,
    `dura`, `numNotes`, `graceNote` where the flag is set, and a nested `note`
    per note record. Fields Enigma would write but this pool does not reach
    (positioning, articulations, lyrics) are simply absent, exactly as they are
    on a `.musx` record that omits them.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode, holds no recognisable
            entry pool, or the pool is malformed.
    """
    for stream in read_mus_streams(path):
        if _looks_like_entry_pool(stream):
            return tuple(_read_pool(stream))
    raise CorruptScoreError(
        f"{path} has no recognisable entry pool "
        "(DCL-era files pack all pools into one stream; that is not yet supported)"
    )


def read_mus_entries(path: str | os.PathLike[str]) -> tuple[Entry, ...]:
    """Return every entry in the `.mus` file at `path`, in stream order.

    Raises:
        FileNotFoundError: no such path.
        CorruptScoreError: the payload does not decode, holds no recognisable
            entry pool, or the pool is malformed.
        MalformedEntryError: a record decodes but is not a well-formed entry.
    """
    return tuple(read_entry(record) for record in read_mus_entry_records(path))


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _slot_span(note_count: int) -> int:
    """How many 38-byte slots one entry occupies.

    Always at least one, even for a rest, otherwise the walk would not advance.
    """
    overflow = max(note_count - _FIRST_SLOT_NOTES, 0)
    return 1 + -(-overflow // _CONT_SLOT_NOTES)  # ceiling division


def _looks_like_entry_pool(stream: bytes) -> bool:
    """Is this stream the entry pool?

    Identified by structure rather than by position, so a file whose streams are
    ordered differently still works. Every legal entry has SETBIT set and a
    plausible note count, and the slots must tile the stream exactly -- a
    combination the other pools do not satisfy (verified across the corpus).
    """
    if not stream or len(stream) % _SLOT:
        return False
    position = 0
    while position + _SLOT <= len(stream):
        if _u16(stream, position + 4) != 0:
            return False  # a first slot must carry slot index 0
        if not _u32(stream, position + 18) & _SETBIT:
            return False
        count = _u16(stream, position + 24)
        if count > _MAX_NOTES:
            return False
        position += _SLOT * _slot_span(count)
    return position == len(stream)


def _read_pool(stream: bytes) -> list[Record]:
    records: list[Record] = []
    position = 0
    while position + _SLOT <= len(stream):
        stored_count = _u16(stream, position + 24)
        if stored_count > _MAX_NOTES:
            raise CorruptScoreError(f"entry note count {stored_count} exceeds {_MAX_NOTES}")
        records.append(_entry_record(stream, position, stored_count))
        position += _SLOT * _slot_span(stored_count)
    return records


def _note_offsets(base: int, count: int) -> list[int]:
    """Absolute offsets of an entry's note records, across its slots."""
    offsets = [base + _FIRST_NOTE_OFFSET + _NOTE * i for i in range(min(count, _FIRST_SLOT_NOTES))]
    remaining = count - _FIRST_SLOT_NOTES
    slot = 1
    while remaining > 0:
        start = base + _SLOT * slot + _SLOT_HEADER
        for i in range(min(remaining, _CONT_SLOT_NOTES)):
            offsets.append(start + _NOTE * i)
        remaining -= _CONT_SLOT_NOTES
        slot += 1
    return offsets


def _entry_record(stream: bytes, offset: int, stored_count: int) -> Record:
    flag = _u32(stream, offset + 18)
    # FLOATREST decides, not NOTEBIT. Three cases, all observed in the corpus:
    #   * ordinary note      NOTEBIT set                  -> notes = stored count
    #   * floating rest      FLOATREST set, NOTEBIT clear -> a placeholder note
    #     record is stored with a count of 1, but there is no pitch content and
    #     .musx reports zero notes
    #   * positioned rest    both clear                   -> eeppd.txt: moving a
    #     rest off the midline clears FLOATREST and adds a real note record for
    #     the vertical position, which .musx surfaces as one note
    # Using NOTEBIT instead mis-classifies the third case (74 corpus entries).
    note_count = 0 if flag & _FLOATREST else stored_count
    edu = _u16(stream, offset + 14)
    # Fail here rather than in `read_entry`, so the message names the entry.
    try:
        duration_from_edu(edu)
    except Exception as exc:
        raise CorruptScoreError(f"entry {_u32(stream, offset)}: bad duration {edu}") from exc
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        "dura": str(edu),
        "numNotes": str(note_count),
    }
    if flag & _GRACENOTE:
        # Presence is the signal, as it is in EnigmaXML's `<graceNote/>`.
        fields["graceNote"] = ""
    notes = tuple(_note_record(stream, o) for o in _note_offsets(offset, note_count))
    if notes:
        fields["note"] = notes if len(notes) > 1 else notes[0]
    return Record(
        tag="entry",
        attrs={
            "entnum": str(_u32(stream, offset)),
            "prev": str(_u32(stream, offset + 6)),
            "next": str(_u32(stream, offset + 10)),
        },
        text="",
        fields=fields,
    )


def _note_record(stream: bytes, offset: int) -> Record:
    if offset + _NOTE > len(stream):
        raise CorruptScoreError("entry note record runs past the end of the pool")
    tcd = _u16(stream, offset)
    flag = _u32(stream, offset + 2)
    magnitude = tcd & 0x07
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        "harmLev": str(_signed(tcd >> _TCD_ALT_BITS, 16 - _TCD_ALT_BITS)),
        "harmAlt": str(-magnitude if tcd & 0x08 else magnitude),
    }
    if flag & _TIE_START:
        fields["tieStart"] = ""
    if flag & _TIE_END:
        fields["tieEnd"] = ""
    return Record(tag="note", attrs={}, text="", fields=fields)


_ = Duration  # re-exported type used in the public signature
