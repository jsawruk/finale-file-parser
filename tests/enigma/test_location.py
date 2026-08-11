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
# (frame 11) has entry 3. Measure 1 sets key 2; measure 2 omits keySig, which
# means C major rather than a continuation of key 2.
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


# A mirror: one entry span, two frameSpec records naming it, two gfholds naming
# those frames. Staff 1 and staff 2 both display entries 1-2 in measure 1.
# Nothing in the file marks either staff as the copy.
MIRROR = _doc(
    _entries("1:2", "2:0")
    + """
    <others>
      <frameSpec cmper="10" inci="0">
        <startEntry>1</startEntry><endEntry>2</endEntry>
      </frameSpec>
      <frameSpec cmper="20" inci="0">
        <startEntry>1</startEntry><endEntry>2</endEntry>
      </frameSpec>
      <measSpec cmper="1"><keySig><key>3</key></keySig></measSpec>
      <staffSpec cmper="1"><x>a</x></staffSpec>
      <staffSpec cmper="2"><x>a</x></staffSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>
      <gfhold cmper1="2" cmper2="1"><frame1>20</frame1></gfhold>
    </details>
    """
)

# The same gfhold slot reaching one entry twice, via two frameSpec incidences
# that both carry the span. Not a mirror -- a mirror puts the entry in two
# DIFFERENT places. This is one place claimed twice, which is malformed.
SAME_PLACE_TWICE = _doc(
    _entries("1:0")
    + """
    <others>
      <frameSpec cmper="10" inci="0">
        <startEntry>1</startEntry><endEntry>1</endEntry>
      </frameSpec>
      <frameSpec cmper="10" inci="1">
        <startEntry>1</startEntry><endEntry>1</endEntry>
      </frameSpec>
      <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
      <staffSpec cmper="1"><x>a</x></staffSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>
    </details>
    """
)


def test_a_mirrored_entry_holds_one_location_per_staff() -> None:
    """Finale's mirror: one staff displays another's music.

    Both placements are peers. The file marks neither as the copy, so the
    order of the tuple carries no meaning and this asserts on the set.
    """
    loc = locate_entries(parse_enigma(MIRROR))
    assert len(loc[1]) == 2
    assert {place.staff for place in loc[1]} == {1, 2}
    assert {place.measure for place in loc[1]} == {1}
    assert {place.key_signature for place in loc[1]} == {3}
    assert {place.layer for place in loc[1]} == {1}
    # the whole span mirrors, not just its first entry
    assert {place.staff for place in loc[2]} == {1, 2}


def test_an_unmirrored_entry_holds_exactly_one_location() -> None:
    """The common case keeps the same shape: a one-element tuple, not a bare
    location. Guards against a fix that special-cases mirrors."""
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[1] == (EntryLocation(entnum=1, staff=1, measure=1, layer=1, key_signature=2),)
    assert len(loc[3]) == 1


def test_the_same_place_claimed_twice_still_raises() -> None:
    """Distinct locations are a mirror; the same location twice is malformed.

    Across 133 readable DCL documents no entry is ever placed twice at one
    (staff, measure, layer), so nothing legitimate depends on tolerating it.
    """
    with pytest.raises(MalformedScoreError, match="placed twice at staff 1 measure 1 layer 1"):
        locate_entries(parse_enigma(SAME_PLACE_TWICE))


def test_many_gfholds_claiming_one_chain_hit_the_placement_cap() -> None:
    """A hostile file cannot make resolution allocate gfholds x entries locations.

    Every placement is legal on its own -- 100 staves, each with its own
    `gfhold`, all naming the frame that spans the whole entry chain, so no place
    is ever claimed twice. What bounds it is the total: `_CHAIN_GUARD` bounds a
    single walk, and this is the guard on how many walks a document may pay for.
    Three entries allow 192 placements; 100 staves ask for 300.
    """
    staves = 100
    holds = "".join(
        f'<gfhold cmper1="{staff}" cmper2="1"><frame1>10</frame1></gfhold>'
        for staff in range(1, staves + 1)
    )
    doc = _doc(
        _entries("1:2", "2:3", "3:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>3</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        """
        + f"<details>{holds}</details>"
    )
    with pytest.raises(MalformedScoreError, match="entry placements exceed 192"):
        locate_entries(parse_enigma(doc))


def test_places_entries_in_staff_and_measure() -> None:
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[1] == (EntryLocation(entnum=1, staff=1, measure=1, layer=1, key_signature=2),)
    assert loc[2] == (EntryLocation(entnum=2, staff=1, measure=1, layer=1, key_signature=2),)
    assert loc[3][0].measure == 2


def test_a_measure_without_a_keysig_is_c_major_not_the_previous_key() -> None:
    """Finale writes C major by omitting the element, never by storing 0.

    Reading the absence as inheritance keeps a piece in its opening key through
    every passage that returns to C. The corpus case is `Easy Holiday Ukulele
    Songbook.musx`: key=1 through measure 32, no element for 33-52, key=1 again
    from 53, and Finale renders 33 with a natural cancelling the sharp and
    chords of C, G7 and F. Inheriting spelled twenty measures a step sharp.
    """
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[3][0].key_signature == 0


def test_a_key_returns_after_an_absent_measure() -> None:
    """The shape that exposed the bug: stated, absent, stated again."""
    doc = _doc(
        _entries("1:0", "2:0", "3:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <frameSpec cmper="11" inci="0">
            <startEntry>2</startEntry><endEntry>2</endEntry>
          </frameSpec>
          <frameSpec cmper="12" inci="0">
            <startEntry>3</startEntry><endEntry>3</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>1</key></keySig></measSpec>
          <measSpec cmper="2"><width>100</width></measSpec>
          <measSpec cmper="3"><keySig><key>1</key></keySig></measSpec>
          <staffSpec cmper="1"><x>a</x></staffSpec>
        </others>
        <details>
          <gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>
          <gfhold cmper1="1" cmper2="2"><frame1>11</frame1></gfhold>
          <gfhold cmper1="1" cmper2="3"><frame1>12</frame1></gfhold>
        </details>
        """
    )
    loc = locate_entries(parse_enigma(doc))
    assert [loc[n][0].key_signature for n in (1, 2, 3)] == [1, 0, 1]


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
    assert locate_entries(parse_enigma(doc))[1][0].key_signature == 0


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
    assert locate_entries(parse_enigma(doc))[1][0].key_signature == 253  # verbatim, not -3


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
    assert loc[1][0].measure == 1 and loc[2][0].measure == 1  # both layers placed


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


def test_frame_with_no_entries_is_skipped_not_malformed() -> None:
    """A `frameSpec` may exist (with other fields, e.g. startTime) but hold no

    entries at all: no `startEntry` and no `endEntry`. A legitimate empty
    layer, not a broken link.
    """
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <frameSpec cmper="20" inci="0">
            <startTime>0</startTime>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details>
          <gfhold cmper1="1" cmper2="1"><frame1>10</frame1><frame2>20</frame2></gfhold>
        </details>
        """
    )
    loc = locate_entries(parse_enigma(doc))
    assert loc[1][0].measure == 1
    assert len(loc) == 1


def test_frame_cmper_with_a_second_empty_incidence_still_resolves() -> None:
    """A frame cmper can carry two `frameSpec` incidences (`inci="0"` and

    `inci="1"`) where the default (`inci="0"`) is empty and the real entry
    chain lives on the other incidence. `others.get` defaults to `inci=0`
    alone, which would silently miss the entries -- resolution must check
    every incidence sharing the cmper. Observed on 73 of 67,558 corpus
    frame cmpers (20 of 401 files).
    """
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0"><startTime>0</startTime></frameSpec>
          <frameSpec cmper="10" inci="1">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    loc = locate_entries(parse_enigma(doc))
    assert loc[1] == (EntryLocation(entnum=1, staff=1, measure=1, layer=1, key_signature=0),)


def test_frame_with_only_start_entry_still_raises() -> None:
    """Asymmetric -- only one of startEntry/endEntry present -- is still malformed."""
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0"><startEntry>1</startEntry></frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    with pytest.raises(MalformedScoreError):
        locate_entries(parse_enigma(doc))


def test_empty_and_zero_frame_slots_are_skipped_not_errors() -> None:
    """An unused layer slot (empty or "0") is skipped, not a broken frame.

    Finale omits unused slots, but Enigma may write frameN=0; either must not
    raise, and the real frames must still resolve.
    """
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details>
          <gfhold cmper1="1" cmper2="1">
            <frame1>10</frame1><frame2>0</frame2><frame3></frame3>
          </gfhold>
        </details>
        """
    )
    loc = locate_entries(parse_enigma(doc))
    assert loc[1][0].measure == 1


def test_measure_with_entries_but_no_measspec_key_raises() -> None:
    """A measure holding entries but defining no key is malformed: this is the
    foundation later slices read the key from, so it raises rather than
    fabricating C major (key 0)."""
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    with pytest.raises(MalformedScoreError, match="no measSpec key"):
        locate_entries(parse_enigma(doc))


def test_part_variant_framespec_is_ignored() -> None:
    """A linked-part frameSpec incidence must not re-place the score's entries.
    all_with returns part variants; resolution filters them out."""
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <frameSpec cmper="10" part="1">
            <startEntry>1</startEntry><endEntry>1</endEntry>
          </frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    # without the part filter, the part-variant frameSpec would double-place entry 1
    loc = locate_entries(parse_enigma(doc))
    assert loc[1][0].measure == 1
