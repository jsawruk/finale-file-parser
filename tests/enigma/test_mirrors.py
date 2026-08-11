"""A mirror reaches the IR as music on both staves.

Finale's mirror is a *display* device -- one staff shows another's notes rather
than holding a copy. MusicXML has no such concept, so the faithful rendering of
what Finale draws is the notes written onto both staves. That is what this
covers, end to end from XML to Score.
"""

from __future__ import annotations

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Event, Score

NS = "http://www.makemusic.com/2012/finale"

# Two quarter notes, C4 then D4, mirrored onto staff 2. One entry span, two
# frameSpec records naming it, two gfholds naming those frames.
MIRROR = f'''<finale version="18.0" xmlns="{NS}">
    <entries>
      <entry entnum="1" prev="0" next="2">
        <numNotes>1</numNotes><dura>1024</dura><isNote/>
        <note id="1"><harmLev>0</harmLev><harmAlt>0</harmAlt></note>
      </entry>
      <entry entnum="2" prev="1" next="0">
        <numNotes>1</numNotes><dura>1024</dura><isNote/>
        <note id="1"><harmLev>1</harmLev><harmAlt>0</harmAlt></note>
      </entry>
    </entries>
    <others>
      <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>2</endEntry></frameSpec>
      <frameSpec cmper="20" inci="0"><startEntry>1</startEntry><endEntry>2</endEntry></frameSpec>
      <measSpec cmper="1">
        <keySig><key>0</key></keySig><beats>4</beats><divbeat>1024</divbeat>
      </measSpec>
      <staffSpec cmper="1"><x>a</x></staffSpec>
      <staffSpec cmper="2"><x>a</x></staffSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>
      <gfhold cmper1="2" cmper2="1"><frame1>20</frame1></gfhold>
    </details>
</finale>'''.encode()


def _events(score: Score, part_id: str) -> list[Event]:
    part = next(p for p in score.parts if p.id == part_id)
    return [e for m in part.measures for v in m.voices for e in v.events]


def test_a_mirrored_span_reaches_both_parts() -> None:
    score = build_score(parse_enigma(MIRROR))
    assert [p.id for p in score.parts] == ["P1", "P2"]

    first, second = _events(score, "P1"), _events(score, "P2")
    assert len(first) == 2
    assert [(p.step, p.octave) for e in first for p in e.pitches] == [("C", 4), ("D", 4)]
    assert [(p.step, p.octave) for e in second for p in e.pitches] == [("C", 4), ("D", 4)]
    assert [e.duration for e in first] == [e.duration for e in second]


def test_the_mirror_does_not_double_the_source_staff() -> None:
    """Both staves get the music once, not the source staff twice.

    The failure this guards is a loop that appends every placement into the
    first location's cell, which would leave P1 holding four events and P2
    holding none.
    """
    score = build_score(parse_enigma(MIRROR))
    assert len(_events(score, "P1")) == 2
    assert len(_events(score, "P2")) == 2
