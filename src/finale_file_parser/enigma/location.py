"""Resolve entries to their place in the score: staff, measure, and raw key.

The first cross-pool link resolution: an entry does not name its staff,
measure, or key. The path, confirmed against the corpus (see
docs/superpowers/specs/2026-07-23-entry-location-design.md):

    entry (entnum)
      <- reached by walking a frame's entry chain (startEntry, then each
         entry's `next` attribute, until endEntry)
    frameSpec (others, cmper = frame number)
      <- referenced by
    gfhold (details, cmper1 = staff, cmper2 = measure) -- frame1..frame4
    measSpec (others, cmper = measure) -- keySig (nested Record {key: <int>})

A `gfhold` holds up to four frames -- Finale's layers -- and all present frames
must be resolved, or layer-2+ entries go unlocated (299 of 6332 corpus gfholds
carry frame2/frame3). Which slot placed an entry is recorded as `layer`, because
each layer independently fills the measure: durations must be grouped by layer or
a multi-layer measure appears to hold two or three times its time signature.

Not every measure carries a `keySig` (449 of 2622 omit it), and **a measure
without one is C major** -- Finale writes C major by omitting the element rather
than by storing zero. See `effective_keys` for the evidence, and for why reading
the absence as inheritance is wrong. The key is exposed raw (undecoded) --
decoding it is a later slice.

A frame number (`gfhold`'s `frame1..4`) can name more than one `frameSpec`
*incidence* sharing that `cmper`: 73 of 67,558 corpus frame cmpers carry two
incidences (`inci="0"` and `inci="1"`) rather than the usual one, and in
every such pair exactly one incidence carries `startEntry`/`endEntry` -- the
other has neither (only unrelated fields, e.g. `startTime`). `others.get`
defaults to `inci=0`, which for these 73 is the *empty* incidence, so
resolution must use `all_with(tag, cmper)` (every incidence sharing that
cmper) and walk whichever incidence(s) actually carry an entry chain, not
just the default. Full corpus sweep:
docs/superpowers/plans/2026-07-23-entry-location.md.

An entry can be placed **more than once**. That is Finale's *mirror*: one staff
displaying another's music, stored as one entry span with two `frameSpec`
records naming it and two `gfhold` records naming those frames. Nothing marks
either placement as the copy, so `locate_entries` returns them as peers, in
frame-walk order. One place claimed twice is still an error -- see
`MalformedScoreError`.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.errors import FinaleFileError

_FRAME_FIELDS = ("frame1", "frame2", "frame3", "frame4")
_CHAIN_GUARD = 1_000_000


class MalformedScoreError(FinaleFileError):
    """The document's cross-pool links do not resolve to a consistent score.

    Raised for an entry no frame places (an orphan), a `gfhold` frame
    pointing at a missing `frameSpec`, a `keySig.key`/`startEntry` that is
    not an integer, a `frameSpec` incidence with only one of `startEntry`/
    `endEntry` present (an incidence with neither is a legitimate empty
    layer, not an error), an entry placed twice at the same staff, measure
    and layer (an entry in several *different* places is a mirror, and is
    legal), or a `next`-chain that exceeds the guard (a cycle).
    """


@dataclass(frozen=True)
class EntryLocation:
    """Where one entry sits in the score, and the raw key signature in force."""

    entnum: int
    staff: int
    """gfhold cmper1."""

    measure: int
    """gfhold cmper2."""

    key_signature: int
    """Effective raw measSpec keySig 'key' (inheritance applied; NOT decoded)."""

    layer: int
    """Which of the gfhold's four frame slots placed this entry, 1-4.

    Finale's layers. Each layer independently fills the measure, so anything
    that adds up durations must group by layer as well as by (staff, measure) --
    summing a measure across layers double-counts its time. Measured: 78 corpus
    measures sum to exactly twice their time signature, and 4 to exactly three
    times, matching their layer count.
    """


def locate_entries(doc: EnigmaDocument) -> dict[int, tuple[EntryLocation, ...]]:
    """Resolve every entry to the place(s) it sounds, and the effective raw key.

    Pure over the parsed document -- no I/O. Builds the whole index in one
    pass since the effective-key inheritance needs a full measure-order pass
    anyway, and callers iterate entries far more than once.

    Raises:
        MalformedScoreError: an entry is not reachable from any frame, a
            frame points at a missing `frameSpec`, a `keySig.key` or
            `startEntry`/`endEntry` is not an integer, an entry is placed
            twice at one (staff, measure, layer), or a `next`-chain exceeds
            the guard.
    """
    entries_by_num = {_int(e.attrs.get("entnum"), "entnum"): e for e in doc.entries.of_tag("entry")}
    key_by_measure = effective_keys(doc)

    location: dict[int, list[EntryLocation]] = {}
    for gfhold in doc.details.of_tag("gfhold"):
        # Score records only. A linked-part gfhold would place the same entries
        # a second time and trip the double-place check; the score placement is
        # authoritative. (No part-variant gfhold occurs in the corpus, but this
        # keeps resolution correct by construction rather than by that accident.)
        if "part" in gfhold.attrs:
            continue
        staff = _int(gfhold.attrs.get("cmper1"), "gfhold cmper1")
        measure = _int(gfhold.attrs.get("cmper2"), "gfhold cmper2")
        if measure not in key_by_measure:
            # A measure that holds entries but defines no key is malformed: this
            # is the foundation every later slice reads its key from, so fabricate
            # nothing — raise rather than silently return C major.
            raise MalformedScoreError(
                f"gfhold places entries in measure {measure}, which has no measSpec key"
            )
        key_signature = key_by_measure[measure]
        for layer, field_name in enumerate(_FRAME_FIELDS, start=1):
            frame_value = gfhold.fields.get(field_name)
            if not isinstance(frame_value, str) or frame_value in ("", "0"):
                # An absent, empty, or "0" frame slot is an unused layer, not a
                # frame — skip it. Real files omit unused slots, but Enigma may
                # also write 0; either way it names no frameSpec.
                continue
            frame_cmper = _int(frame_value, field_name)
            _place_frame_entries(
                doc, frame_cmper, staff, measure, layer, key_signature, entries_by_num, location
            )

    orphans = set(entries_by_num) - set(location)
    if orphans:
        raise MalformedScoreError(
            f"{len(orphans)} orphan entry(ies) not placed by any frame: {sorted(orphans)}"
        )
    return {entnum: tuple(places) for entnum, places in location.items()}


def effective_keys(doc: EnigmaDocument) -> dict[int, int]:
    """Effective raw key per measure.

    **A measure whose `measSpec` carries no `keySig` is C major, not a
    continuation of the previous key.** Finale writes C major by omitting the
    element rather than by storing zero: across 401 corpus documents not one of
    19,644 `keySig` elements holds the value 0.

    Reading the absence as inheritance is the tempting mistake, and it is wrong.
    `Easy Holiday Ukulele Songbook.musx` runs `key=1` for measures 1-32, no
    element for 33-52, then `key=1` again from 53. Finale renders measure 33
    with a natural cancelling the sharp and chords of C, G7 and F: a key change
    to C major, at the start of a new song. Inheriting there spells twenty
    measures a step sharp -- F# where the file means F.

    A measure with no `measSpec` at all is a different case: nothing is stated
    about it, so the running key carries across the gap.
    """
    meas_specs = [r for r in doc.others.of_tag("measSpec") if "part" not in r.attrs]
    by_measure = {_int(r.attrs.get("cmper"), "measSpec cmper"): r for r in meas_specs}
    if not by_measure:
        return {}

    result: dict[int, int] = {}
    last = 0
    for measure in range(min(by_measure), max(by_measure) + 1):
        record = by_measure.get(measure)
        if record is None:
            result[measure] = last  # no measure stated; carry across the gap
            continue
        key_sig = record.fields.get("keySig")
        if isinstance(key_sig, Record):
            key_value = key_sig.fields.get("key")
            if not isinstance(key_value, str):
                raise MalformedScoreError(f"measSpec {measure} keySig.key is missing or not scalar")
            last = _int(key_value, "keySig.key")
        else:
            last = 0  # no keySig element: C major
        result[measure] = last
    return result


def _place_frame_entries(
    doc: EnigmaDocument,
    frame_cmper: int,
    staff: int,
    measure: int,
    layer: int,
    key_signature: int,
    entries_by_num: dict[int, Record],
    location: dict[int, list[EntryLocation]],
) -> None:
    # Every incidence sharing this cmper (a frame cmper can carry two, where the
    # first is empty and the second holds the entry chain — see module docstring),
    # but score records only: a linked-part frameSpec would re-place the same
    # entries. all_with returns part variants too, so filter them out here.
    frame_specs = tuple(
        f for f in doc.others.all_with("frameSpec", frame_cmper) if "part" not in f.attrs
    )
    if not frame_specs:
        raise MalformedScoreError(
            f"gfhold staff={staff} measure={measure} frame {frame_cmper} has no matching frameSpec"
        )
    for frame_spec in frame_specs:
        start = frame_spec.fields.get("startEntry")
        end = frame_spec.fields.get("endEntry")
        if start is None and end is None:
            # This incidence may legitimately hold zero entries -- it exists
            # (with other fields, e.g. startTime) but never got an entry
            # chain. A frame cmper can carry a second incidence that does
            # (see module docstring); nothing to place from this one.
            continue
        if not isinstance(start, str) or not isinstance(end, str):
            raise MalformedScoreError(f"frameSpec {frame_cmper} startEntry/endEntry missing")
        _walk_entry_chain(
            frame_cmper, start, end, staff, measure, layer, key_signature, entries_by_num, location
        )


def _walk_entry_chain(
    frame_cmper: int,
    start: str,
    end: str,
    staff: int,
    measure: int,
    layer: int,
    key_signature: int,
    entries_by_num: dict[int, Record],
    location: dict[int, list[EntryLocation]],
) -> None:
    entnum = _int(start, "startEntry")
    end_entnum = _int(end, "endEntry")

    steps = 0
    while True:
        steps += 1
        if steps > _CHAIN_GUARD:
            raise MalformedScoreError(
                f"frameSpec {frame_cmper} entry chain exceeded {_CHAIN_GUARD} steps (cycle?)"
            )
        entry = entries_by_num.get(entnum)
        if entry is None:
            raise MalformedScoreError(
                f"frameSpec {frame_cmper} chain references missing entry {entnum}"
            )
        here = EntryLocation(
            entnum=entnum,
            staff=staff,
            measure=measure,
            layer=layer,
            key_signature=key_signature,
        )
        if here in location.get(entnum, ()):
            raise MalformedScoreError(
                f"entry {entnum} placed twice at staff {staff} measure {measure} layer {layer}"
            )
        location.setdefault(entnum, []).append(here)
        if entnum == end_entnum:
            break
        entnum = _int(entry.attrs.get("next"), "next")


def _int(value: str | None, name: str) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MalformedScoreError(f"{name} is not an integer: {value!r}") from exc
