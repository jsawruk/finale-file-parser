"""What points at an entry, and what that entry decodes to.

The reader walks one direction: a `gfhold` names a frame, a `frameSpec` names
an entry range, and details hang off an `entnum`. `locate_entries` is that
walk. Reading a report the question is the reverse, and this module answers it.

It re-walks rather than calling `locate_entries`, and that duplication is
deliberate: `locate_entries` raises `MalformedScoreError` on exactly the
documents a diagnostic report exists for. Nothing here raises. A broken link
becomes a sentence in `unresolved`, and the rest of the answer still arrives.

The duplication is contained by `tests/report/test_entry_facts_corpus_sweep.py`,
which asserts the two agree on every corpus document `locate_entries` accepts.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record

__all__ = [
    "EntryDecode",
    "EntryFacts",
    "NoteFacts",
    "Placement",
    "Reference",
    "placements_by_entry",
    "references_to",
]


@dataclass(frozen=True)
class Placement:
    """Where a frame put this entry. Any field may be None: a placement is
    recorded even when the chain that produced it broke part way."""

    staff: int | None = None
    measure: int | None = None
    layer: int | None = None
    gfhold_key: str | None = None
    frame: int | None = None


@dataclass(frozen=True)
class Reference:
    """A record that names this entry, identified the way the report names it."""

    pool: str
    tag: str
    key: str


@dataclass(frozen=True)
class NoteFacts:
    """One note's stored values, and the pitch they spell where that is known."""

    harm_lev: int
    harm_alt: int
    spelled: str | None = None
    why_not: str | None = None
    """Which input was missing, when `spelled` is None. Never a guess."""


@dataclass(frozen=True)
class EntryDecode:
    duration_edu: int
    duration_name: str
    is_rest: bool
    notes: tuple[NoteFacts, ...] = ()


@dataclass(frozen=True)
class EntryFacts:
    placements: tuple[Placement, ...] = ()
    named_by: tuple[Reference, ...] = ()
    decode: EntryDecode | None = None
    unresolved: tuple[str, ...] = ()
    """Which links failed, in words.

    Prose rather than an enumeration: this is read by someone staring at a file
    that does not work, and the failure modes are open-ended enough that a code
    would either lose information or grow one member per message.
    """


def _identity(record: Record) -> str:
    """The record's key as the Records tree writes it, so a reference can be
    matched to the row it names."""
    from finale_file_parser.report.model import _musx_key

    return _musx_key(record, 0)


def references_to(doc: EnigmaDocument, entnum: int) -> tuple[Reference, ...]:
    """Every details record naming this entry.

    Needs only the `entnum`, so it resolves whether or not the placement chain
    does -- which is the point: on a document whose frames are broken, this is
    the half that still answers.
    """
    out: list[Reference] = []
    for record in doc.details.records:
        if record.attrs.get("entnum") == str(entnum):
            out.append(Reference(pool="details", tag=record.tag, key=_identity(record)))
    return tuple(out)


def placements_by_entry(
    doc: EnigmaDocument,
) -> tuple[dict[int, list[Placement]], dict[int, list[str]]]:
    """Walk gfhold -> frameSpec -> entry chain, recording breaks instead of raising.

    Mirrors `locate_entries`, and deliberately: see the module docstring. The
    differences are all in what happens when something is wrong.

    The entry range is walked by following each entry's `next` attribute, the
    same as `locate_entries._walk_entry_chain` -- not by treating
    `[startEntry, endEntry]` as a dense arithmetic range. `startEntry` and
    `endEntry` are file-supplied integers with no ceiling, so an arithmetic
    range can be asked to iterate without bound; following `next` bounds the
    walk to real entries and the same `_CHAIN_GUARD` step limit
    `locate_entries` uses for exactly this reason.

    A failure that belongs to no single entry -- a frame that is absent, a
    chain that breaks before reaching its declared end, or a chain that loops
    -- is filed under entnum `0`, which is not a valid entry number and so
    cannot collide with a real one.

    Placements per entry are capped at `_MAX_PLACEMENTS_PER_ENTRY`, the same
    bound `locate_entries` enforces and for the same reason: `_CHAIN_GUARD`
    only bounds one chain walk, and nothing else bounds how many separate
    gfhold/frame chains a hostile file can point at one entry. A real Finale
    mirror places one entry on a handful of staves at most -- the cap is a
    hostile-input bound, not a statement that more than a couple of
    placements is wrong.
    """
    from finale_file_parser.enigma.location import (
        _CHAIN_GUARD,
        _FRAME_FIELDS,
        _MAX_PLACEMENTS_PER_ENTRY,
    )

    placements: dict[int, list[Placement]] = {}
    unresolved: dict[int, list[str]] = {}
    capped: set[int] = set()
    entries_by_num: dict[int, Record] = {}
    for record in doc.entries.of_tag("entry"):
        n = _as_int(record.attrs.get("entnum"))
        if n is not None:
            entries_by_num[n] = record

    for gfhold in doc.details.of_tag("gfhold"):
        if "part" in gfhold.attrs:
            continue
        staff = _as_int(gfhold.attrs.get("cmper1"))
        measure = _as_int(gfhold.attrs.get("cmper2"))
        key = _identity(gfhold)
        for layer, field_name in enumerate(_FRAME_FIELDS, start=1):
            value = gfhold.fields.get(field_name)
            if not isinstance(value, str) or value in ("", "0"):
                continue
            frame = _as_int(value)
            if frame is None:
                unresolved.setdefault(0, []).append(
                    f"gfhold {key} {field_name} is {value!r}, which is not a frame number"
                )
                continue
            specs = tuple(
                f for f in doc.others.all_with("frameSpec", frame) if "part" not in f.attrs
            )
            if not specs:
                unresolved.setdefault(0, []).append(
                    f"gfhold {key} {field_name} names frameSpec {frame}, which is absent"
                )
                continue
            for spec in specs:
                start = _as_int(spec.fields.get("startEntry"))
                end = _as_int(spec.fields.get("endEntry"))
                if start is None or end is None:
                    continue
                _walk_chain(
                    key=key,
                    frame=frame,
                    start=start,
                    end=end,
                    staff=staff,
                    measure=measure,
                    layer=layer,
                    entries_by_num=entries_by_num,
                    placements=placements,
                    unresolved=unresolved,
                    guard=_CHAIN_GUARD,
                    cap=_MAX_PLACEMENTS_PER_ENTRY,
                    capped=capped,
                )

    for entnum in sorted(entries_by_num):
        if entnum not in placements:
            unresolved.setdefault(entnum, []).append("no frame reaches this entry")
    return placements, unresolved


def _walk_chain(
    *,
    key: str,
    frame: int,
    start: int,
    end: int,
    staff: int | None,
    measure: int | None,
    layer: int,
    entries_by_num: dict[int, Record],
    placements: dict[int, list[Placement]],
    unresolved: dict[int, list[str]],
    guard: int,
    cap: int,
    capped: set[int],
) -> None:
    """Follow one entry chain from `start` to `end` via each entry's `next`.

    Mirrors `locate_entries._walk_entry_chain`, but every place that function
    raises, this records a message under entnum `0` and stops -- the entries
    already placed on this walk stay placed.

    `cap` bounds placements for a single entry, shared across every call this
    document's walk makes (via the shared `placements` dict) -- it is what
    stops both a hostile file naming the same entry from many separate
    gfhold/frame chains, and a chain that cycles back onto one entry inside a
    single walk. `capped` records which entnums have already had their
    one-time cap message written, so a document that keeps re-claiming an
    over-capped entry reports it once, not once per claim.
    """
    entnum = start
    steps = 0
    while True:
        steps += 1
        if steps > guard:
            unresolved.setdefault(0, []).append(
                f"gfhold {key} frame {frame} entry chain exceeded {guard} steps (cycle?)"
            )
            return
        entry = entries_by_num.get(entnum)
        if entry is None:
            unresolved.setdefault(0, []).append(
                f"gfhold {key} frame {frame} chain references missing entry {entnum}"
            )
            return
        if len(placements.get(entnum, ())) >= cap:
            if entnum not in capped:
                capped.add(entnum)
                unresolved.setdefault(entnum, []).append(
                    f"entry {entnum} reached the {cap}-placement cap; further claims on it "
                    "are not recorded (a real mirror places one entry on a few staves, not "
                    "this many)"
                )
            return
        placements.setdefault(entnum, []).append(
            Placement(staff=staff, measure=measure, layer=layer, gfhold_key=key, frame=frame)
        )
        if entnum == end:
            return
        next_entnum = _as_int(entry.attrs.get("next"))
        if next_entnum is None:
            unresolved.setdefault(0, []).append(
                f"gfhold {key} frame {frame} chain broke before reaching entry {end}: "
                f"entry {entnum} has no valid next"
            )
            return
        entnum = next_entnum


def _as_int(value: object) -> int | None:
    """A field or attribute as an int, or None when it is not one. Absence is
    ordinary here and never an error."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
