import pytest

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.location import (
    EntryLocation,
    MalformedScoreError,
    locate_entries,
)

NS = "http://www.makemusic.com/2012/finale"


def _doc(body: str) -> bytes:
    return f'<finale version="18.0" xmlns="{NS}">{body}</finale>'.encode()


def _entries(*specs: str) -> str:
    # each spec: "entnum:next" e.g. "1:2"
    out = []
    for s in specs:
        en, nx = s.split(":")
        out.append(f'<entry entnum="{en}" prev="0" next="{nx}"><dura>1024</dura></entry>')
    return "<entries>" + "".join(out) + "</entries>"


# Two measures on one staff. Measure 1 (frame 10) has entries 1->2; measure 2
# (frame 11) has entry 3. Measure 1 sets key 2; measure 2 omits keySig (inherits).
BASIC = _doc(
    _entries("1:2", "2:0", "3:0")
    + """
    <others>
      <frameSpec cmper="10" inci="0">
        <startEntry>1</startEntry><endEntry>2</endEntry>
      </frameSpec>
      <frameSpec cmper="11" inci="0">
        <startEntry>3</startEntry><endEntry>3</endEntry>
      </frameSpec>
      <measSpec cmper="1"><keySig><key>2</key></keySig></measSpec>
      <measSpec cmper="2"><width>100</width></measSpec>
      <staffSpec cmper="1"><x>a</x></staffSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>
      <gfhold cmper1="1" cmper2="2"><frame1>11</frame1></gfhold>
    </details>
    """
)


def test_places_entries_in_staff_and_measure() -> None:
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[1] == EntryLocation(entnum=1, staff=1, measure=1, key_signature=2)
    assert loc[2] == EntryLocation(entnum=2, staff=1, measure=1, key_signature=2)
    assert loc[3].measure == 2


def test_key_inheritance() -> None:
    # measure 2 has no keySig -> inherits key 2 from measure 1
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[3].key_signature == 2


def test_first_measure_without_keysig_defaults_to_zero() -> None:
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <measSpec cmper="1"><width>100</width></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    assert locate_entries(parse_enigma(doc))[1].key_signature == 0


def test_raw_key_is_not_decoded() -> None:
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>253</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    assert locate_entries(parse_enigma(doc))[1].key_signature == 253  # verbatim, not -3


def test_layers_frame2_entries_are_located() -> None:
    # one measure, two layers: frame 10 (entry 1), frame 20 (entry 2)
    doc = _doc(
        _entries("1:0", "2:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <frameSpec cmper="20" inci="0">
            <startEntry>2</startEntry><endEntry>2</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details>
          <gfhold cmper1="1" cmper2="1"><frame1>10</frame1><frame2>20</frame2></gfhold>
        </details>
        """
    )
    loc = locate_entries(parse_enigma(doc))
    assert loc[1].measure == 1 and loc[2].measure == 1  # both layers placed


def test_orphan_entry_raises() -> None:
    # entry 2 is not reachable from any frame
    doc = _doc(
        _entries("1:0", "2:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    with pytest.raises(MalformedScoreError, match="orphan|not placed|2"):
        locate_entries(parse_enigma(doc))


def test_frame_pointing_at_missing_framespec_raises() -> None:
    doc = _doc(
        _entries("1:0")
        + """
        <others><measSpec cmper="1"><keySig><key>0</key></keySig></measSpec></others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>99</frame1></gfhold></details>
        """
    )
    with pytest.raises(MalformedScoreError):
        locate_entries(parse_enigma(doc))


def test_next_chain_cycle_raises() -> None:
    # 1 -> 2 -> 1 ... cycle
    doc = _doc(
        _entries("1:2", "2:1")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>999</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    with pytest.raises(MalformedScoreError):
        locate_entries(parse_enigma(doc))
