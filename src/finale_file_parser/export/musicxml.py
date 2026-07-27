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
from finale_file_parser.ir import Event, Lyric, Measure, Part, Pitch, Score, Voice

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

    part_list = ET.SubElement(root, "part-list")
    for part in score.parts:
        score_part = ET.SubElement(part_list, "score-part", id=part.id)
        ET.SubElement(score_part, "part-name").text = part.name or part.id

    for part in score.parts:
        _append_part(root, part)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{_DOCTYPE}\n{body}\n'.encode()


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
    _append_attributes(element, measure, divisions, emit_divisions=emit_divisions)

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
        ET.SubElement(note, "rest")
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
    ET.SubElement(note, "type").text = _note_type(event)
    for _ in range(event.dots):
        ET.SubElement(note, "dot")
    if event.tuplet_ratio is not None:
        modification = ET.SubElement(note, "time-modification")
        # actual-notes over normal-notes is the inverse of the sounded ratio: a
        # triplet sounds 2/3, and is 3 notes in the time of 2.
        ET.SubElement(modification, "actual-notes").text = str(event.tuplet_ratio.denominator)
        ET.SubElement(modification, "normal-notes").text = str(event.tuplet_ratio.numerator)
    # One <notations> holds both, in schema order: tied before articulations.
    # A chord's marks belong to the event, so only its principal note carries
    # them -- repeating per pitch would print the staccato three times.
    marks = () if chord else event.articulations
    if event.tie_start or event.tie_end or marks:
        notations = ET.SubElement(note, "notations")
        if event.tie_end:
            ET.SubElement(notations, "tied", type="stop")
        if event.tie_start:
            ET.SubElement(notations, "tied", type="start")
        if marks:
            articulations = ET.SubElement(notations, "articulations")
            for name in marks:
                ET.SubElement(articulations, name)
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
