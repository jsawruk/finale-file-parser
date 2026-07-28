"""Build the format-neutral IR from a parsed EnigmaXML document.

The `.musx` side of the hub-and-spoke shape in `docs/DECISIONS.md`: this module
knows Enigma, the IR does not know this module, and no exporter knows either. A
`.mus` reader added later produces the same `Score` and every exporter keeps
working.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from fractions import Fraction

from finale_file_parser.enigma.articulations import articulations_by_entry
from finale_file_parser.enigma.barlines import barline_styles
from finale_file_parser.enigma.beams import BeamedNote, beams_for
from finale_file_parser.enigma.clef import (
    Clef,
    ClefSign,
    clef_definitions,
    clefs_by_measure,
    default_clefs,
)
from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.groups import staff_groups, staff_order
from finale_file_parser.enigma.jumps import jumps_by_measure
from finale_file_parser.enigma.key import Mode, decode_key
from finale_file_parser.enigma.location import effective_keys, locate_entries
from finale_file_parser.enigma.lyrics import Lyric as EnigmaLyric
from finale_file_parser.enigma.lyrics import lyrics_by_entry
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.enigma.pitch import StaffTransposition, read_transposition, spell_note
from finale_file_parser.enigma.repeats import Repeats, repeats_for
from finale_file_parser.enigma.text import file_info, staff_names
from finale_file_parser.enigma.timesig import TimeSignature as EnigmaTimeSignature
from finale_file_parser.enigma.timesig import time_signatures
from finale_file_parser.enigma.tuplet import entry_chain, sounded_durations, tuplets_by_entry
from finale_file_parser.ir import (
    Event,
    Lyric,
    Measure,
    Part,
    PartGroup,
    Pitch,
    Score,
    TimeSignature,
    Voice,
)

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
    starts_beam: dict[int, list[bool]] = field(default_factory=lambda: defaultdict(list))
    """Enigma's beam bit per event, parallel to `events_by_layer`. Kept beside
    the events rather than on them: it is an Enigma detail the IR has no need
    of once the beams themselves are worked out."""


def build_score(document: EnigmaDocument) -> Score:
    """Convert a parsed EnigmaXML document into the IR.

    One part per staff, measures in order, one IR voice per Finale layer.
    """
    location = locate_entries(document)
    chain = entry_chain(document)
    sounded = sounded_durations(chain, tuplets_by_entry(document))
    records = {int(r.attrs["entnum"]): r for r in document.entries.of_tag("entry")}
    transpositions = _transpositions(document)
    lyrics = lyrics_by_entry(document)
    articulations = articulations_by_entry(document)

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
        cell.starts_beam[here.layer].append("beam" in record.fields)
        cell.events_by_layer[here.layer].append(
            _event(
                record=record,
                key_raw=here.key_signature,
                transposition=transpositions.get(here.staff, _NO_TRANSPOSITION),
                written_edu=chain.written_edu[entnum],
                sounded_edu=sounded[entnum],
                lyrics=lyrics.get(entnum, ()),
                articulations=articulations.get(entnum, ()),
            )
        )

    for cell in cells.values():
        _apply_beams(cell)

    signatures = time_signatures(document)
    clef_table = clef_definitions(document)
    clef_at = clefs_by_measure(document)
    names = staff_names(document)
    info = file_info(document)
    repeats = repeats_for(document)
    directions = jumps_by_measure(document)
    barlines = barline_styles(document)

    staves = _ordered_staves(document, {staff for staff, _ in cells})
    keys = effective_keys(document)
    numbers = _measure_numbers(keys, cells)
    clef_at = _carried_clefs(document, staves, numbers, clef_at)
    parts = [
        Part(
            id=f"P{staff}",
            # Fall back to a positional label only where the document names no
            # staff, which is most of them: 24 of 84 in the sampled corpus.
            name=names[staff].full or names[staff].abbreviated
            if staff in names
            else f"Staff {staff}",
            measures=tuple(
                _measure(
                    staff=staff,
                    number=number,
                    previous=numbers[index - 1] if index else None,
                    cells=cells,
                    keys=keys,
                    signatures=signatures,
                    clef_table=clef_table,
                    clef_at=clef_at,
                    repeats=repeats,
                    directions=directions,
                    barlines=barlines,
                )
                for index, number in enumerate(numbers)
            ),
        )
        for staff in staves
    ]
    return Score(
        parts=tuple(parts),
        groups=_groups(document, [part.id for part in parts]),
        title=info.get("title", ""),
        composer=info.get("composer", ""),
        metadata={k: v for k, v in info.items() if k not in {"title", "composer"}},
    )


RESERVED_STAFF = 0x7FFF
"""A staff id Finale reserves rather than lays out: 32767, the same sentinel the
format uses for "to the end" in `staffGroup.endMeas`.

Every one of the 401 corpus documents declares it, and no document treats it as
part of the score:

* it is **never** in the score's instrument list (0 of 401), which is what
  `instUsed` is -- the layout of the staves the score shows;
* it is **never** named by a staff group (0 of 401);
* its `staffSpec` is a template rather than a description of a part -- 401
  documents hold just two distinct bodies, all with the same fixed `instUuid`,
  a one-line `customStaff`, and clefs, key signatures, measure numbers, repeats
  and repeat barlines all hidden;
* 376 of 398 give it a single repeated pitch, always in layer 1, and none
  carries a lyric.

It is also the **only** staff in the corpus absent from the instrument list, so
excluding it excludes nothing else. What Finale actually uses it for is not
known and this does not guess; what is established is that it is not a part of
the score, and exporting it put a spurious "Staff 32767" into every file this
project produced. Its entries are still placed by `locate_entries`, so nothing
below the IR is lost.
"""


def _measure_numbers(keys: dict[int, int], cells: dict[tuple[int, int], _Cell]) -> list[int]:
    """Every measure of the score, in order.

    The list comes from `measSpec` -- which `effective_keys` already walks, one
    entry per measure -- and **not** from where the music happens to be. It runs
    1..N with no gaps in all 398 buildable corpus documents and nothing sounds
    outside it, whereas the measures that hold entries omit every bar in which
    the whole ensemble rests: 1,375 of them across 162 documents.

    A document with no `measSpec` at all falls back to the measures that hold
    entries, so a malformed file still exports what it has.
    """
    return sorted(keys) or sorted({measure for _, measure in cells})


def _measure_rest(signature: EnigmaTimeSignature | None) -> Event:
    """One rest filling the bar.

    A part silent through a measure still has that measure -- MusicXML gives
    every part every measure, and a reader that meets a gap in the numbering has
    no way to tell a silent bar from a missing one. Its length is the time
    signature's, which is why this is not just a whole-note rest: a 3/4 measure
    rest lasts 3/4 and has no note value.
    """
    length = (
        Fraction(signature.numerator, signature.denominator)
        if signature is not None
        else Fraction(1)
    )
    return Event(
        duration=length,
        written_duration=length,
        pitches=(),
        is_measure_rest=True,
    )


def _carried_clefs(
    document: EnigmaDocument,
    staves: list[int],
    numbers: list[int],
    clef_at: dict[tuple[int, int], int],
) -> dict[tuple[int, int], int]:
    """The clef in force at every (staff, measure), not only where notes are.

    `clefs_by_measure` reads `gfhold`, and a measure a staff rests through has
    no `gfhold` at all -- so without carrying the last one forward a part would
    lose its clef the moment it fell silent, and re-announce it on returning.
    Before the first `gfhold` the staff's own `defaultClef` applies.
    """
    defaults = default_clefs(document)
    out = dict(clef_at)
    for staff in staves:
        current = defaults.get(staff, 0)
        for number in numbers:
            current = clef_at.get((staff, number), current)
            out[(staff, number)] = current
    return out


def _ordered_staves(document: EnigmaDocument, present: set[int]) -> list[int]:
    """The staves carrying music, in the order the score lays them out.

    `instUsed` gives that order, and it is not always ascending: 10 corpus
    documents list their staves in an order the staff numbers do not follow, and
    sorting instead puts those parts down the page in the wrong places. Where
    the document has no such list -- every `.mus`, whose equivalent record is
    unidentified -- `staff_order` already falls back to numeric order, so this
    changes nothing there.

    A staff with music but no slot in the list keeps a place, after the listed
    ones, rather than being dropped: it has notes, and losing a part is worse
    than putting it last. The one exception is `RESERVED_STAFF`, which every
    document declares and none lays out.
    """
    order = staff_order(document)
    wanted = present - {RESERVED_STAFF}
    listed = [staff for staff in order if staff in wanted]
    return listed + sorted(wanted - set(order))


def _groups(document: EnigmaDocument, part_ids: list[str]) -> tuple[PartGroup, ...]:
    """Staff groups whose staves form a contiguous run of the score's parts.

    A group is **dropped** where its staves are not contiguous here, which
    happens when the document lays its staves out in an order their numbers do
    not follow: 14 of 230 corpus groups. `build_score` orders parts by staff
    number, so for those documents a `<part-group>` would brace a run of parts
    the score does not group -- worse than no bracket at all. Fixing it properly
    means ordering parts by `staff_order`, which is a change to every part's
    position and belongs in its own slice.
    """
    at = {part_id: index for index, part_id in enumerate(part_ids)}
    out: list[PartGroup] = []
    for group in staff_groups(document):
        ids = [f"P{staff}" for staff in group.staves]
        positions = [at[part_id] for part_id in ids if part_id in at]
        if not positions or sorted(positions) != list(range(min(positions), max(positions) + 1)):
            continue
        out.append(
            PartGroup(
                part_ids=tuple(part_ids[index] for index in sorted(positions)),
                symbol=group.symbol,
                barline=group.barline,
                name=group.name,
                abbreviation=group.abbreviation,
            )
        )
    return tuple(out)


def _apply_beams(cell: _Cell) -> None:
    """Replace each layer's events with the same events carrying their beams.

    Beaming is a property of a run of notes, not of one note, so it can only be
    worked out once a layer's events are all in playing order -- which is why
    this is a second pass rather than part of `_event`.
    """
    for layer, events in cell.events_by_layer.items():
        flags = cell.starts_beam[layer]
        notes = [
            BeamedNote(
                written_duration=event.written_duration,
                dots=event.dots,
                is_rest=event.is_rest,
                starts_group=starts,
            )
            for event, starts in zip(events, flags, strict=True)
        ]
        cell.events_by_layer[layer] = [
            replace(event, beams=tuple(beams)) if beams else event
            for event, beams in zip(events, beams_for(notes), strict=True)
        ]


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
    lyrics: tuple[EnigmaLyric, ...] = (),
    articulations: tuple[str, ...] = (),
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
        # Verse order, so a multi-verse note emits its lyrics top to bottom.
        lyrics=tuple(
            Lyric(
                number=lyric.number,
                text=lyric.text,
                syllabic=lyric.syllabic.value,
                extend=lyric.extend,
            )
            for lyric in sorted(lyrics, key=lambda item: item.number)
        ),
        articulations=articulations,
    )


def _measure(
    *,
    staff: int,
    number: int,
    previous: int | None,
    cells: dict[tuple[int, int], _Cell],
    keys: dict[int, int],
    signatures: dict[int, EnigmaTimeSignature],
    clef_table: dict[int, Clef],
    clef_at: dict[tuple[int, int], int],
    repeats: Repeats,
    directions: dict[int, tuple[str, ...]] | None = None,
    barlines: dict[int, str] | None = None,
) -> Measure:
    cell = cells.get((staff, number))

    signature = signatures.get(number)
    previous_signature = signatures.get(previous) if previous is not None else None
    clef_index = clef_at.get((staff, number))
    previous_clef_index = clef_at.get((staff, previous)) if previous is not None else None
    clef = clef_table.get(clef_index) if clef_index is not None else None
    clef_changed = clef is not None and clef_index != previous_clef_index

    # The key comes from the measure, not from the staff's notes, so a measure
    # in which this part is silent still knows what key it is in.
    key_raw = keys.get(number, cell.key_raw if cell is not None else 0)
    key = decode_key(key_raw)
    key_changed = previous is None or keys.get(previous) != key_raw
    here = repeats.get(number)

    return Measure(
        number=number,
        voices=(
            tuple(
                Voice(number=layer, events=tuple(events))
                for layer, events in sorted(cell.events_by_layer.items())
            )
            if cell is not None
            else (Voice(number=1, events=(_measure_rest(signature),)),)
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
        # Repeats belong to the measure, not the staff: every part carries the
        # same barline, which is what a reader of one part expects to see.
        # A marking belongs to the measure, so every part shows it -- which is
        # what a player reading one part needs.
        directions=(directions or {}).get(number, ()),
        barline_style=(barlines or {}).get(number),
        repeat_forward=here.forward,
        repeat_backward=here.backward,
        repeat_passes=here.passes,
        endings=here.endings,
    )
