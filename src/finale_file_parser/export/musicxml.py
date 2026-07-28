"""Write a `Score` as MusicXML.

Consumes the IR only -- nothing from `enigma` or `container` -- so any reader that
produces a `Score` exports for free (`docs/DECISIONS.md`, 2026-07-20).

Output is `score-partwise`, the more widely supported of the two MusicXML
orderings, and is validated against the official W3C schema in the tests.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from fractions import Fraction

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.ir import (
    Ending,
    Event,
    Lyric,
    Measure,
    Part,
    PartGroup,
    Pitch,
    Score,
    Voice,
)

__all__ = ["MUSICXML_VERSION", "ExportError", "to_musicxml"]

MUSICXML_VERSION = "4.0"

_DOCTYPE = (
    '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML '
    f'{MUSICXML_VERSION} Partwise//EN" '
    f'"http://www.musicxml.org/dtds/{MUSICXML_VERSION}/partwise.dtd">'
)

_NOTE_TYPES = {
    1: "whole",
    2: "half",
    4: "quarter",
    8: "eighth",
    16: "16th",
    32: "32nd",
    64: "64th",
    128: "128th",
    256: "256th",
}
"""Denominator of the written value as a fraction of a whole note -> MusicXML type."""

_MAX_DIVISIONS = 1_000_000
"""Guard against a pathological duration forcing an absurd divisions value."""


class ExportError(FinaleFileError):
    """The score cannot be represented as MusicXML."""


def to_musicxml(score: Score) -> bytes:
    """Render `score` as a MusicXML document.

    Raises:
        ExportError: a duration has no MusicXML note type, or the divisions
            needed to express the score's durations exceed the guard.
    """
    root = ET.Element("score-partwise", version=MUSICXML_VERSION)
    _append_identification(root, score)

    _append_part_list(root, score)

    for part in score.parts:
        _append_part(root, part)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{_DOCTYPE}\n{body}\n'.encode()


def _append_part_list(root: ET.Element, score: Score) -> None:
    """The part list, with each group's brace or bracket wrapped around it.

    MusicXML expresses a group as a matched pair of `<part-group>` elements
    surrounding the `<score-part>`s it covers, identified by a `number` rather
    than by nesting. The number is reused once a group closes, which is what
    lets an arbitrarily deep score use few of them.
    """
    part_list = ET.SubElement(root, "part-list")
    starting, stopping = _group_edges(score)
    open_numbers: dict[int, str] = {}
    for index, part in enumerate(score.parts):
        for group_index in starting.get(index, ()):
            number = _lowest_free(open_numbers)
            open_numbers[group_index] = number
            _append_group(part_list, score.groups[group_index], number, "start")
        score_part = ET.SubElement(part_list, "score-part", id=part.id)
        ET.SubElement(score_part, "part-name").text = part.name or part.id
        # Innermost first, so groups close in the reverse of the order they
        # opened even where several end on the same part.
        for group_index in reversed(stopping.get(index, ())):
            number = open_numbers.pop(group_index)
            ET.SubElement(part_list, "part-group", number=number, type="stop")


def _group_edges(score: Score) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Which groups start and stop at each part index, in opening order."""
    at = {part.id: index for index, part in enumerate(score.parts)}
    starting: dict[int, list[int]] = {}
    stopping: dict[int, list[int]] = {}
    for group_index, group in enumerate(score.groups):
        positions = [at[part_id] for part_id in group.part_ids if part_id in at]
        if not positions:
            continue
        starting.setdefault(min(positions), []).append(group_index)
        stopping.setdefault(max(positions), []).append(group_index)
    return starting, stopping


def _lowest_free(open_numbers: dict[int, str]) -> str:
    taken = set(open_numbers.values())
    number = 1
    while str(number) in taken:
        number += 1
    return str(number)


def _append_group(part_list: ET.Element, group: PartGroup, number: str, kind: str) -> None:
    element = ET.SubElement(part_list, "part-group", number=number, type=kind)
    # Schema order: group-name, group-abbreviation, group-symbol, group-barline.
    if group.name:
        ET.SubElement(element, "group-name").text = group.name
    if group.abbreviation:
        ET.SubElement(element, "group-abbreviation").text = group.abbreviation
    if group.symbol:
        ET.SubElement(element, "group-symbol").text = group.symbol
    if group.barline:
        ET.SubElement(element, "group-barline").text = "yes"


def _append_identification(root: ET.Element, score: Score) -> None:
    if score.title:
        work = ET.SubElement(root, "work")
        ET.SubElement(work, "work-title").text = score.title
    if not score.composer:
        return
    identification = ET.SubElement(root, "identification")
    creator = ET.SubElement(identification, "creator", type="composer")
    creator.text = score.composer


def _divisions_for(part: Part) -> int:
    """Divisions per quarter note that make every duration in `part` an integer.

    MusicXML durations are integers, so the denominators have to be cleared. A
    triplet eighth is 1/12 of a whole note, which needs divisions divisible by 3 --
    picking 1 (or any power of two) silently truncates it to zero.
    """
    denominator = 1
    for measure in part.measures:
        for voice in measure.voices:
            for event in voice.events:
                if event.is_grace:
                    continue
                # duration is a fraction of a whole note; a quarter is 1/4, so
                # duration * 4 * divisions must be a whole number.
                denominator = math.lcm(denominator, (event.duration * 4).denominator)
    if denominator > _MAX_DIVISIONS:
        raise ExportError(f"durations require {denominator} divisions per quarter; refusing")
    return denominator


def _duration_in_divisions(duration: Fraction, divisions: int) -> int:
    value = duration * 4 * divisions
    if value.denominator != 1:
        raise ExportError(f"duration {duration} is not expressible in {divisions} divisions")
    return int(value)


def _note_type(event: Event) -> str:
    """MusicXML note type from the written duration, undotting first.

    `written_duration` includes the augmentation dots, so a dotted quarter is 3/8
    -- which is not a note value. Removing the dots recovers the base 1/4.
    """
    undotted = event.written_duration / (2 - Fraction(1, 2**event.dots))
    if undotted.numerator != 1:
        raise ExportError(f"written duration {event.written_duration} is not a note value")
    name = _NOTE_TYPES.get(undotted.denominator)
    if name is None:
        raise ExportError(f"written duration {event.written_duration} has no MusicXML type")
    return name


def _append_part(root: ET.Element, part: Part) -> None:
    element = ET.SubElement(root, "part", id=part.id)
    divisions = _divisions_for(part)
    first = True
    for measure in part.measures:
        _append_measure(element, measure, divisions, emit_divisions=first)
        first = False


def _append_measure(
    parent: ET.Element, measure: Measure, divisions: int, *, emit_divisions: bool
) -> None:
    element = ET.SubElement(parent, "measure", number=str(measure.number))
    _append_barline(element, measure, "left")
    _append_attributes(element, measure, divisions, emit_divisions=emit_divisions)
    for words in measure.directions:
        # Before the notes: the marking applies to the measure, and a direction
        # placed after them would read as belonging to the next bar.
        direction = ET.SubElement(element, "direction", placement="above")
        ET.SubElement(ET.SubElement(direction, "direction-type"), "words").text = words

    for index, voice in enumerate(measure.voices):
        if index:
            # Voices are written in sequence, so the cursor must be rewound to the
            # start of the measure before each one after the first.
            spent = sum(
                (
                    _duration_in_divisions(e.duration, divisions)
                    for e in measure.voices[index - 1].events
                ),
                0,
            )
            if spent:
                backup = ET.SubElement(element, "backup")
                ET.SubElement(backup, "duration").text = str(spent)
        for event in voice.events:
            _append_event(element, event, voice, divisions)

    _append_barline(element, measure, "right")


def _append_barline(element: ET.Element, measure: Measure, location: str) -> None:
    """The barline: its style, a repeat, and any ending bracket that meets it.

    Left and right are separate elements at opposite ends of the measure, so a
    forward repeat opens the measure and a backward one closes it -- and a
    one-measure ending, which both opens and closes here, writes one of each.
    """
    left = location == "left"
    endings = [e for e in measure.endings if (e.type == "start") == left]
    repeat = measure.repeat_forward if left else measure.repeat_backward
    # A double or final bar belongs to the right barline only. Where a repeat
    # meets one -- four corpus measures do -- the repeat's own heavy line is
    # what gets drawn, which the `elif` below enforces: two `<bar-style>`
    # elements in one barline is invalid.
    style = None if left else measure.barline_style
    if not endings and not repeat and style is None:
        return

    barline = ET.SubElement(element, "barline", location=location)
    # Schema order within a barline: bar-style, then ending, then repeat.
    if repeat:
        ET.SubElement(barline, "bar-style").text = "heavy-light" if left else "light-heavy"
    elif style is not None:
        ET.SubElement(barline, "bar-style").text = style
    for ending in endings:
        attrs = {"number": ",".join(str(n) for n in ending.numbers), "type": ending.type}
        ET.SubElement(barline, "ending", attrs).text = _ending_text(ending)
    if repeat:
        attrs = {"direction": "forward" if left else "backward"}
        # `times` defaults to 2, so it is written only where Finale says
        # otherwise -- a section played three times, say.
        if not left and measure.repeat_passes != 2:
            attrs["times"] = str(measure.repeat_passes)
        ET.SubElement(barline, "repeat", attrs)


def _ending_text(ending: Ending) -> str:
    """What the bracket reads as: "1." for one pass, "1., 2." for several.

    MusicXML takes the displayed text separately from `number`, and leaving it
    empty makes a reader invent its own. Finale can store custom text
    (`repeatEndingText`), which three corpus documents use and this does not
    read; the derived form matches what the others display.
    """
    return ", ".join(f"{number}." for number in ending.numbers)


def _append_attributes(
    element: ET.Element, measure: Measure, divisions: int, *, emit_divisions: bool
) -> None:
    needed = (
        emit_divisions
        or measure.key_fifths is not None
        or measure.time is not None
        or measure.clef_sign is not None
    )
    if not needed:
        return
    attributes = ET.SubElement(element, "attributes")
    # Order is fixed by the schema: divisions, key, time, ... clef.
    if emit_divisions:
        ET.SubElement(attributes, "divisions").text = str(divisions)
    if measure.key_fifths is not None:
        key = ET.SubElement(attributes, "key")
        ET.SubElement(key, "fifths").text = str(measure.key_fifths)
        ET.SubElement(key, "mode").text = "minor" if measure.is_minor else "major"
    if measure.time is not None:
        time = ET.SubElement(attributes, "time")
        ET.SubElement(time, "beats").text = str(measure.time.beats)
        ET.SubElement(time, "beat-type").text = str(measure.time.beat_type)
    if measure.clef_sign is not None:
        clef = ET.SubElement(attributes, "clef")
        ET.SubElement(clef, "sign").text = measure.clef_sign
        if measure.clef_line is not None:
            ET.SubElement(clef, "line").text = str(measure.clef_line)


def _append_event(element: ET.Element, event: Event, voice: Voice, divisions: int) -> None:
    if event.is_rest:
        _append_note(element, event, voice, divisions, pitch=None, chord=False)
        return
    for index, pitch in enumerate(event.pitches):
        _append_note(element, event, voice, divisions, pitch=pitch, chord=bool(index))


def _append_note(
    element: ET.Element,
    event: Event,
    voice: Voice,
    divisions: int,
    *,
    pitch: Pitch | None,
    chord: bool,
) -> None:
    note = ET.SubElement(element, "note")
    # Schema order: grace, chord, pitch or rest, duration, tie, voice, type...
    # A grace note takes no metric time, and the schema requires duration > 0, so
    # it is expressed by omitting duration rather than by writing zero.
    if event.is_grace:
        ET.SubElement(note, "grace")
    if chord:
        ET.SubElement(note, "chord")
    if pitch is None:
        # `measure="yes"` is what makes a reader centre one symbol in the bar
        # rather than draw a rest of some particular value -- and it is why the
        # note carries no <type>, since the length is the bar's, not a note's.
        rest = ET.SubElement(note, "rest")
        if event.is_measure_rest:
            rest.set("measure", "yes")
    else:
        element_pitch = ET.SubElement(note, "pitch")
        ET.SubElement(element_pitch, "step").text = pitch.step
        if pitch.alteration:
            ET.SubElement(element_pitch, "alter").text = str(pitch.alteration)
        ET.SubElement(element_pitch, "octave").text = str(pitch.octave)
    if not event.is_grace:
        ET.SubElement(note, "duration").text = str(
            _duration_in_divisions(event.duration, divisions)
        )
    # <tie> is the sounding instruction; <tied> inside <notations> is the visual
    # slur. Both are required for a tie to survive a round trip through most
    # applications.
    if event.tie_end:
        ET.SubElement(note, "tie", type="stop")
    if event.tie_start:
        ET.SubElement(note, "tie", type="start")
    ET.SubElement(note, "voice").text = str(voice.number)
    if not event.is_measure_rest:
        ET.SubElement(note, "type").text = _note_type(event)
    for _ in range(event.dots):
        ET.SubElement(note, "dot")
    if event.tuplet_ratio is not None:
        modification = ET.SubElement(note, "time-modification")
        # actual-notes over normal-notes is the inverse of the sounded ratio: a
        # triplet sounds 2/3, and is 3 notes in the time of 2.
        ET.SubElement(modification, "actual-notes").text = str(event.tuplet_ratio.denominator)
        ET.SubElement(modification, "normal-notes").text = str(event.tuplet_ratio.numerator)
    # Schema order puts <beam> after <time-modification> and before
    # <notations>. Only on a chord's principal note: the beam belongs to the
    # stem, and the schema allows at most eight per note.
    if not chord:
        for beam in event.beams:
            ET.SubElement(note, "beam", number=str(beam.number)).text = beam.type
    # One <notations> holds both, in schema order: tied before articulations.
    # A chord's marks belong to the event, so only its principal note carries
    # them -- repeating per pitch would print the staccato three times.
    marks = () if chord else event.articulations
    digits = () if chord else event.fingerings
    if event.tie_start or event.tie_end or marks or digits:
        notations = ET.SubElement(note, "notations")
        if event.tie_end:
            ET.SubElement(notations, "tied", type="stop")
        if event.tie_start:
            ET.SubElement(notations, "tied", type="start")
        if marks:
            articulations = ET.SubElement(notations, "articulations")
            for name in marks:
                ET.SubElement(articulations, name)
        if digits:
            # All of a chord's fingerings sit on its principal note rather than
            # one per pitch. Enigma attaches them to the entry, not to a note,
            # so which finger goes with which pitch is not stored -- and
            # MusicXML allows several <fingering> in one <technical> for exactly
            # this case.
            technical = ET.SubElement(notations, "technical")
            for digit in digits:
                ET.SubElement(technical, "fingering").text = digit
    # Schema order puts <lyric> last, after <notations>. Only on a chord's
    # principal note: the syllable is sung once, not once per pitch.
    if not chord:
        for lyric in event.lyrics:
            _append_lyric(note, lyric)


def _append_lyric(note: ET.Element, lyric: Lyric) -> None:
    element = ET.SubElement(note, "lyric", number=str(lyric.number))
    ET.SubElement(element, "syllabic").text = lyric.syllabic
    ET.SubElement(element, "text").text = lyric.text
    if lyric.extend:
        ET.SubElement(element, "extend")
