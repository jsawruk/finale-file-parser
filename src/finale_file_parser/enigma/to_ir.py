"""Build the format-neutral IR from a parsed EnigmaXML document.

The `.musx` side of the hub-and-spoke shape in `docs/DECISIONS.md`: this module
knows Enigma, the IR does not know this module, and no exporter knows either. A
`.mus` reader added later produces the same `Score` and every exporter keeps
working.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from finale_file_parser.enigma.clef import Clef, ClefSign, clef_definitions, clefs_by_measure
from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.key import Mode, decode_key
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.pitch import StaffTransposition, read_transposition, spell_note
from finale_file_parser.enigma.timesig import TimeSignature as EnigmaTimeSignature
from finale_file_parser.enigma.timesig import time_signatures
from finale_file_parser.enigma.tuplet import entry_chain, sounded_durations, tuplets_by_entry
from finale_file_parser.ir import Event, Measure, Part, Pitch, Score, TimeSignature, Voice

__all__ = ["build_score"]

_WHOLE_EDU = 4096
_NO_TRANSPOSITION = StaffTransposition(interval=0, adjust=0)

_CLEF_ANCHORS = {
    ClefSign.G: (-10, 2),
    ClefSign.F: (2, 4),
    ClefSign.C: (-4, 3),
}
"""(adjust, staff line) for each sign's standard clef.

Two `adjust` units move the clef one staff line. Applying that to the corpus clef
table reproduces exactly the nine historically used clefs -- treble, alto, tenor,
bass, both baritones, French violin, mezzo-soprano and soprano. That is why the
rule is trusted rather than merely fitted to the three clefs the corpus selects:
a wrong step would not land on the complete set.
"""

_ADJUST_PER_LINE = 2

_MUSICXML_SIGNS = {
    ClefSign.G: "G",
    ClefSign.F: "F",
    ClefSign.C: "C",
    ClefSign.SHAPE: "percussion",
}


def _clef_line(clef: Clef) -> int | None:
    anchor = _CLEF_ANCHORS.get(clef.sign)
    if anchor is None:
        return None
    anchor_adjust, anchor_line = anchor
    return anchor_line + (clef.adjust - anchor_adjust) // _ADJUST_PER_LINE


@dataclass
class _Cell:
    """What one (staff, measure) holds, gathered in a single pass."""

    events_by_layer: dict[int, list[Event]]
    key_raw: int


def build_score(document: EnigmaDocument) -> Score:
    """Convert a parsed EnigmaXML document into the IR.

    One part per staff, measures in order, one IR voice per Finale layer.
    """
    location = locate_entries(document)
    chain = entry_chain(document)
    sounded = sounded_durations(chain, tuplets_by_entry(document))
    records = {int(r.attrs["entnum"]): r for r in document.entries.of_tag("entry")}
    transpositions = _transpositions(document)

    # One pass, in chain order, so a measure's notes come out in playing order
    # rather than document order.
    cells: dict[tuple[int, int], _Cell] = {}
    for entnum in chain.order:
        here = location.get(entnum)
        record = records.get(entnum)
        if here is None or record is None:
            continue
        cell = cells.setdefault(
            (here.staff, here.measure),
            _Cell(events_by_layer=defaultdict(list), key_raw=here.key_signature),
        )
        cell.events_by_layer[here.layer].append(
            _event(
                record=record,
                key_raw=here.key_signature,
                transposition=transpositions.get(here.staff, _NO_TRANSPOSITION),
                written_edu=chain.written_edu[entnum],
                sounded_edu=sounded[entnum],
            )
        )

    signatures = time_signatures(document)
    clef_table = clef_definitions(document)
    clef_at = clefs_by_measure(document)

    staves = sorted({staff for staff, _ in cells})
    numbers = sorted({measure for _, measure in cells})
    parts = [
        Part(
            id=f"P{staff}",
            name=f"Staff {staff}",
            measures=tuple(
                _measure(
                    staff=staff,
                    number=number,
                    previous=numbers[index - 1] if index else None,
                    cells=cells,
                    signatures=signatures,
                    clef_table=clef_table,
                    clef_at=clef_at,
                )
                for index, number in enumerate(numbers)
                if (staff, number) in cells
            ),
        )
        for staff in staves
    ]
    return Score(parts=tuple(parts))


def _transpositions(document: EnigmaDocument) -> dict[int, StaffTransposition]:
    out: dict[int, StaffTransposition] = {}
    for record in document.others.of_tag("staffSpec"):
        if "part" in record.attrs:
            continue
        transposition = read_transposition(record)
        if transposition is not None:
            out[int(record.attrs["cmper"])] = transposition
    return out


def _event(
    *,
    record: Record,
    key_raw: int,
    transposition: StaffTransposition,
    written_edu: int,
    sounded_edu: Fraction,
) -> Event:
    entry = read_entry(record)
    key = decode_key(key_raw)
    pitches = tuple(
        Pitch(
            step=spelled.written.letter,
            octave=spelled.written.octave,
            alteration=spelled.written.alteration,
        )
        for spelled in (spell_note(note, key, transposition) for note in entry.notes)
    )
    written = Fraction(written_edu, _WHOLE_EDU)
    duration = Fraction(sounded_edu) / _WHOLE_EDU
    # A ratio of 1 means no tuplet; recording it anyway would make every note
    # carry a pointless <time-modification>.
    ratio = duration / written if written and duration != written else None
    return Event(
        duration=duration,
        written_duration=written,
        pitches=pitches,
        dots=entry.duration.dots,
        tie_start=any(note.tie_start for note in entry.notes),
        tie_end=any(note.tie_end for note in entry.notes),
        tuplet_ratio=ratio,
        is_grace="graceNote" in record.fields,
    )


def _measure(
    *,
    staff: int,
    number: int,
    previous: int | None,
    cells: dict[tuple[int, int], _Cell],
    signatures: dict[int, EnigmaTimeSignature],
    clef_table: dict[int, Clef],
    clef_at: dict[tuple[int, int], int],
) -> Measure:
    cell = cells[(staff, number)]
    previous_cell = cells.get((staff, previous)) if previous is not None else None

    signature = signatures.get(number)
    previous_signature = signatures.get(previous) if previous is not None else None
    clef_index = clef_at.get((staff, number))
    previous_clef_index = clef_at.get((staff, previous)) if previous is not None else None
    clef = clef_table.get(clef_index) if clef_index is not None else None
    clef_changed = clef is not None and clef_index != previous_clef_index

    key = decode_key(cell.key_raw)
    key_changed = previous_cell is None or cell.key_raw != previous_cell.key_raw

    return Measure(
        number=number,
        voices=tuple(
            Voice(number=layer, events=tuple(events))
            for layer, events in sorted(cell.events_by_layer.items())
        ),
        # Emit an attribute only where it changes: that is what MusicXML expects,
        # and it keeps the output readable.
        key_fifths=key.fifths if key_changed else None,
        is_minor=key.mode is Mode.MINOR,
        time=(
            TimeSignature(beats=signature.numerator, beat_type=signature.denominator)
            if signature is not None and signature != previous_signature
            else None
        ),
        clef_sign=_MUSICXML_SIGNS.get(clef.sign) if clef_changed and clef else None,
        clef_line=_clef_line(clef) if clef_changed and clef else None,
    )
