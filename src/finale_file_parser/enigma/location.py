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

A `gfhold` holds up to four frames -- Finale's layers/voices -- and all
present frames must be resolved, or layer-2+ entries go unlocated (299 of
6332 corpus gfholds carry frame2/frame3). Not every measure carries a
`keySig` (449 of 2622 omit it); a measure without one inherits the previous
measure's effective key, computed by walking measures in cmper order. The
key is exposed raw (undecoded) -- decoding it is a later slice.
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
    not an integer, or a `next`-chain that exceeds the guard (a cycle).
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


def locate_entries(doc: EnigmaDocument) -> dict[int, EntryLocation]:
    """Resolve every entry to its (staff, measure) and the effective raw key.

    Pure over the parsed document -- no I/O. Builds the whole index in one
    pass since the effective-key inheritance needs a full measure-order pass
    anyway, and callers iterate entries far more than once.

    Raises:
        MalformedScoreError: an entry is not reachable from any frame, a
            frame points at a missing `frameSpec`, a `keySig.key` or
            `startEntry`/`endEntry` is not an integer, an entry is placed by
            more than one frame, or a `next`-chain exceeds the guard.
    """
    entries_by_num = {_int(e.attrs.get("entnum"), "entnum"): e for e in doc.entries.of_tag("entry")}
    key_by_measure = _effective_keys(doc)

    location: dict[int, EntryLocation] = {}
    for gfhold in doc.details.of_tag("gfhold"):
        staff = _int(gfhold.attrs.get("cmper1"), "gfhold cmper1")
        measure = _int(gfhold.attrs.get("cmper2"), "gfhold cmper2")
        key_signature = key_by_measure.get(measure, 0)
        for field_name in _FRAME_FIELDS:
            frame_value = gfhold.fields.get(field_name)
            if not isinstance(frame_value, str) or frame_value in ("", "0"):
                # An absent, empty, or "0" frame slot is an unused layer, not a
                # frame — skip it. Real files omit unused slots, but Enigma may
                # also write 0; either way it names no frameSpec.
                continue
            frame_cmper = _int(frame_value, field_name)
            _place_frame_entries(
                doc, frame_cmper, staff, measure, key_signature, entries_by_num, location
            )

    orphans = set(entries_by_num) - set(location)
    if orphans:
        raise MalformedScoreError(
            f"{len(orphans)} orphan entry(ies) not placed by any frame: {sorted(orphans)}"
        )
    return location


def _effective_keys(doc: EnigmaDocument) -> dict[int, int]:
    """Effective raw key per measure, carrying the last seen `keySig.key` forward."""
    meas_specs = [r for r in doc.others.of_tag("measSpec") if "part" not in r.attrs]
    by_measure = {_int(r.attrs.get("cmper"), "measSpec cmper"): r for r in meas_specs}
    if not by_measure:
        return {}

    result: dict[int, int] = {}
    last = 0
    for measure in range(min(by_measure), max(by_measure) + 1):
        record = by_measure.get(measure)
        key_sig = record.fields.get("keySig") if record is not None else None
        if isinstance(key_sig, Record):
            key_value = key_sig.fields.get("key")
            if not isinstance(key_value, str):
                raise MalformedScoreError(f"measSpec {measure} keySig.key is missing or not scalar")
            last = _int(key_value, "keySig.key")
        result[measure] = last
    return result


def _place_frame_entries(
    doc: EnigmaDocument,
    frame_cmper: int,
    staff: int,
    measure: int,
    key_signature: int,
    entries_by_num: dict[int, Record],
    location: dict[int, EntryLocation],
) -> None:
    frame_spec = doc.others.get("frameSpec", frame_cmper)
    if frame_spec is None:
        raise MalformedScoreError(
            f"gfhold staff={staff} measure={measure} frame {frame_cmper} has no matching frameSpec"
        )
    start = frame_spec.fields.get("startEntry")
    end = frame_spec.fields.get("endEntry")
    if not isinstance(start, str) or not isinstance(end, str):
        raise MalformedScoreError(f"frameSpec {frame_cmper} startEntry/endEntry missing")
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
        if entnum in location:
            raise MalformedScoreError(f"entry {entnum} placed by more than one frame")
        location[entnum] = EntryLocation(
            entnum=entnum, staff=staff, measure=measure, key_signature=key_signature
        )
        if entnum == end_entnum:
            break
        entnum = _int(entry.attrs.get("next"), "next")


def _int(value: str | None, name: str) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MalformedScoreError(f"{name} is not an integer: {value!r}") from exc
