"""Tests for the legacy .mus entry-pool reader."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_entries import (
    harm_lev_octave_shift,
    read_mus_entries,
    read_mus_entry_records,
)
from finale_file_parser.enigma.music import NoteValue

SLOT = 38
BANNER_OFFSET = 0x20

SETBIT = 0x80000000
NOTEBIT = 0x40000000
TIE_START = 0x40000000
TIE_END = 0x20000000
BEATBIT = 0x00000800


def _slot(entnum: int, index: int, payload: bytes) -> bytes:
    assert len(payload) == SLOT - 6
    return entnum.to_bytes(4, "little") + index.to_bytes(2, "little") + payload


def _entry_slot(entnum: int, *, dura: int, flag: int, notes: list[tuple[int, int]]) -> bytes:
    """First slot of an entry, carrying up to two notes."""
    body = (
        (0).to_bytes(4, "little")  # prev
        + (0).to_bytes(4, "little")  # next
        + dura.to_bytes(2, "little")
        + (0).to_bytes(2, "little")  # pos
        + flag.to_bytes(4, "little")
        + (0).to_bytes(2, "little")  # extended flag
        + len(notes).to_bytes(2, "little")
    )
    for tcd, note_flag in notes[:2]:
        body += tcd.to_bytes(2, "little") + note_flag.to_bytes(4, "little")
    return _slot(entnum, 0, body.ljust(SLOT - 6, b"\x00"))


def _mus_file(pool: bytes) -> bytes:
    """A 2012-era .mus whose payload is a single zlib stream holding `pool`."""
    header = bytearray(b"\x00" * 0x216)
    header[0:18] = b"ENIGMA BINARY FILE"
    banner = b"Finale(R) 2012 Copyright (c) 1987-2011 MakeMusic"
    header[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
    # Pad the pool so it clears the reader's 4096-byte "real stream" floor.
    return bytes(header) + zlib.compress(pool + b"\x00" * 0, 9)


def _pool(n: int) -> bytes:
    """`n` single-note quarter-note entries, plus padding to clear the size floor."""
    out = b""
    for i in range(n):
        out += _entry_slot(
            i + 1, dura=1024, flag=SETBIT | NOTEBIT, notes=[(0x0060, SETBIT | 0x00010000)]
        )
    return out


def test_reads_entries(tmp_path: Path) -> None:
    path = tmp_path / "e.mus"
    path.write_bytes(_mus_file(_pool(200)))
    entries = read_mus_entries(path)
    assert len(entries) == 200
    assert entries[0].entnum == 1
    assert entries[0].duration.base is NoteValue.QUARTER
    assert entries[0].duration.dots == 0
    assert not entries[0].is_rest
    assert entries[0].notes[0].harm_lev == 6
    assert entries[0].notes[0].harm_alt == 0


def test_rest_has_no_notes_even_though_a_placeholder_is_stored(tmp_path: Path) -> None:
    """FLOATREST decides, not the stored count and not NOTEBIT.

    A floating rest carries a placeholder note record with a count of 1, while
    .musx reports zero notes. Reading the count regresses 55 corpus entries;
    reading NOTEBIT instead regresses a different 74, because a rest moved off the
    midline clears FLOATREST and stores a real note record for its position.
    """
    pool = _entry_slot(1, dura=1024, flag=SETBIT | 0x01000000, notes=[(0x0000, SETBIT)]) + _pool(
        150
    )
    path = tmp_path / "rest.mus"
    path.write_bytes(_mus_file(pool))
    entries = read_mus_entries(path)
    assert entries[0].is_rest
    assert entries[0].notes == ()


def test_the_beam_bit_is_surfaced(tmp_path: Path) -> None:
    """`BEATBIT` says the entry starts a beam group. Nothing downstream can
    recover it, so dropping it silently loses every beam in the file -- and the
    typed `Entry` does not carry it, so only the record view can be checked."""
    pool = (
        _entry_slot(1, dura=512, flag=SETBIT | NOTEBIT | BEATBIT, notes=[(0x0000, SETBIT)])
        + _entry_slot(2, dura=512, flag=SETBIT | NOTEBIT, notes=[(0x0000, SETBIT)])
        + _pool(150)
    )
    path = tmp_path / "beam.mus"
    path.write_bytes(_mus_file(pool))
    records = read_mus_entry_records(path)
    assert "beam" in records[0].fields
    assert "beam" not in records[1].fields


@pytest.mark.parametrize(
    ("nibble", "expected"),
    [(0x0, 0), (0x1, 1), (0x2, 2), (0x9, -1), (0xA, -2)],
)
def test_alteration_is_sign_and_magnitude(tmp_path: Path, nibble: int, expected: int) -> None:
    """Bit 3 is a sign bit, not a two's-complement sign.

    eeppd.txt reads as two's complement, under which 0x9 would be -7. The corpus
    says -1. Getting this wrong silently mis-spells accidentals.
    """
    pool = _entry_slot(
        1, dura=1024, flag=SETBIT | NOTEBIT, notes=[(0x0020 | nibble, SETBIT)]
    ) + _pool(150)
    path = tmp_path / "alt.mus"
    path.write_bytes(_mus_file(pool))
    assert read_mus_entries(path)[0].notes[0].harm_alt == expected


def test_ties_decode(tmp_path: Path) -> None:
    pool = _entry_slot(
        1, dura=1024, flag=SETBIT | NOTEBIT, notes=[(0x0060, SETBIT | TIE_START | TIE_END)]
    ) + _pool(150)
    path = tmp_path / "tie.mus"
    path.write_bytes(_mus_file(pool))
    note = read_mus_entries(path)[0].notes[0]
    assert note.tie_start and note.tie_end


def test_entry_spanning_two_slots_reads_all_notes(tmp_path: Path) -> None:
    """Three notes overflow the first slot; the third lives in a continuation.

    Reading notes at a fixed stride from the entry start puts note 3 on top of the
    next slot's header and yields nonsense (observed: harm_lev 208 instead of -5).
    """
    first = _entry_slot(
        1,
        dura=1024,
        flag=SETBIT | NOTEBIT,
        notes=[(0x0010, SETBIT), (0x0020, SETBIT), (0x0030, SETBIT)],
    )
    # Continuation slot: note records start at payload offset 0 (file offset 6).
    cont = _slot(1, 1, (0x0030).to_bytes(2, "little") + SETBIT.to_bytes(4, "little") + b"\x00" * 26)
    path = tmp_path / "chord.mus"
    path.write_bytes(_mus_file(first + cont + _pool(150)))
    entry = read_mus_entries(path)[0]
    assert len(entry.notes) == 3
    assert [n.harm_lev for n in entry.notes] == [1, 2, 3]


def test_rejects_a_payload_with_no_entry_pool(tmp_path: Path) -> None:
    path = tmp_path / "none.mus"
    path.write_bytes(_mus_file(b"\x01\x02\x03\x04" * 2000))
    with pytest.raises(CorruptScoreError, match="no recognisable entry pool"):
        read_mus_entries(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_mus_entries(tmp_path / "absent.mus")


@pytest.mark.parametrize(
    ("interval", "shift"),
    [(0, 0), (1, 0), (4, 0), (5, -7), (7, -7), (8, -7), (12, -14)],
)
def test_harm_lev_octave_shift(interval: int, shift: int) -> None:
    """Pins the empirical octave rule for transposing staves.

    Every value here was measured against paired .musx files. The boundary is the
    surprising part: the octave moves at interval 5, not 7, so a "divide by 7"
    implementation passes the 0/7/12 cases and silently breaks 5 and 8.
    """
    assert harm_lev_octave_shift(interval) == shift
