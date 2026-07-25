"""Tuplets, and the sounded duration they produce.

`Entry.duration` is the *written* duration. Inside a tuplet the note sounds for a
different length, so anything that cares about time -- playback, MusicXML export,
checking that a measure adds up -- needs the ratio applied.

A tuplet is defined on the entry that *starts* it and covers a span of written
time from there, so scaling one entry means knowing which tuplets are in force at
it, which means walking the entry chain.

**Container-agnostic by construction.** The chain walk and the arithmetic work on
a plain `EntryChain`, which either container can build: `.musx` from its entries
pool, `.mus` from `read_mus_entries` plus the prev/next links in its slot headers.
Only `tuplets_by_entry` is `.musx`-specific, because the tuplet definitions live in
the `details` pool, which is not yet readable from `.mus`. When it is, `.mus` gets
tuplet scaling by supplying that one mapping -- nothing here changes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from fractions import Fraction

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.models import CorruptScoreError

__all__ = [
    "EntryChain",
    "entry_chain",
    "Tuplet",
    "read_tuplet",
    "sounded_durations",
    "tuplets_by_entry",
]

_TUPLET_TAG = "tupletDef"


def _scalar(record: Record, name: str) -> str | None:
    """A field's scalar text, or None if absent.

    `Record.fields` values may be nested records or repeated tuples; a field that
    should be a number but is not gets treated as missing so the caller raises a
    clear error rather than a TypeError from deep inside int().
    """
    value = record.fields.get(name)
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class Tuplet:
    """A tuplet: `symbolic` notes played in the time of `reference` notes.

    A triplet of eighths is symbolic 3x512 in the time of reference 2x512.
    """

    symbolic_number: int
    symbolic_duration: int
    reference_number: int
    reference_duration: int

    @property
    def ratio(self) -> Fraction:
        """Multiply a written duration by this to get the sounded duration."""
        return Fraction(
            self.reference_number * self.reference_duration,
            self.symbolic_number * self.symbolic_duration,
        )

    @property
    def span(self) -> int:
        """Written EDU the tuplet covers, starting at the entry it is defined on."""
        return self.symbolic_number * self.symbolic_duration


@dataclass(frozen=True)
class EntryChain:
    """Entries in playing order, with their written durations.

    The seam that keeps this container-agnostic: both `.musx` and `.mus` can
    produce one, and everything below works on it alone.
    """

    order: Sequence[int]
    """Entry numbers, in the order they are played."""

    written_edu: Mapping[int, int]
    """Entry number -> written duration in EDU."""

    grace_notes: Set[int] = frozenset()
    """Entries that are grace notes.

    A grace note carries a written duration but sounds for no time, so it neither
    contributes to a measure's total nor consumes any of a tuplet's span. Treating
    one as ordinary makes its measure overflow -- the effect is not subtle: four
    grace notes push a 4/4 measure to 6144 EDU against a capacity of 4096.
    """


def read_tuplet(record: Record) -> Tuplet:
    """Read a `tupletDef` record.

    Raises:
        CorruptScoreError: a required field is missing or not a positive integer.
    """

    def field(name: str) -> int:
        raw = _scalar(record, name)
        if raw is None:
            raise CorruptScoreError(f"tupletDef is missing {name!r}")
        try:
            value = int(raw)
        except ValueError as exc:
            raise CorruptScoreError(f"tupletDef {name}={raw!r} is not an integer") from exc
        if value <= 0:
            raise CorruptScoreError(f"tupletDef {name}={value} must be positive")
        return value

    return Tuplet(
        symbolic_number=field("symbolicNum"),
        symbolic_duration=field("symbolicDur"),
        reference_number=field("refNum"),
        reference_duration=field("refDur"),
    )


def tuplets_by_entry(document: EnigmaDocument) -> dict[int, tuple[Tuplet, ...]]:
    """Every tuplet, grouped by the entry that starts it.

    An entry can start more than one (nested tuplets), which is why the value is a
    tuple rather than a single tuplet.
    """
    out: dict[int, list[Tuplet]] = {}
    for record in document.details.records:
        if record.tag != _TUPLET_TAG:
            continue
        raw = record.attrs.get("entnum")
        if raw is None:
            raise CorruptScoreError("tupletDef has no entnum")
        out.setdefault(int(raw), []).append(read_tuplet(record))
    return {entnum: tuple(items) for entnum, items in out.items()}


def sounded_durations(
    chain: EntryChain,
    tuplets: Mapping[int, Sequence[Tuplet]],
) -> dict[int, Fraction]:
    """Sounded duration in EDU for every entry in `chain`.

    Zero for a grace note. Otherwise the written duration outside any tuplet, or
    inside one, the written duration times the tuplet's ratio; nested tuplets
    multiply, which is why the ratio is accumulated over all tuplets in force
    rather than only the innermost.

    A tuplet covers written time, not a number of entries, so its extent is found
    by accumulating written durations from its starting entry until its span is
    consumed. Counting entries instead would break on any tuplet whose notes are
    not all the same length.
    """
    active: list[tuple[Fraction, int]] = []  # (ratio, remaining written EDU)
    out: dict[int, Fraction] = {}

    for entnum in chain.order:
        written = chain.written_edu.get(entnum)
        if written is None:
            raise CorruptScoreError(f"entry {entnum} has no written duration")
        if entnum in chain.grace_notes:
            out[entnum] = Fraction(0)
            continue
        for tuplet in tuplets.get(entnum, ()):
            active.append((tuplet.ratio, tuplet.span))

        ratio = Fraction(1)
        for tuplet_ratio, _ in active:
            ratio *= tuplet_ratio
        out[entnum] = written * ratio

        # Retire tuplets once their written span is consumed. Done after scaling
        # so the entry that exhausts a tuplet is still scaled by it.
        active = [
            (tuplet_ratio, remaining - written)
            for tuplet_ratio, remaining in active
            if remaining - written > 0
        ]
    return out


def entry_chain(document: EnigmaDocument) -> EntryChain:
    """Build an `EntryChain` from a `.musx` document.

    The `.musx` adapter for the seam above. Entries form doubly-linked chains via
    their `prev`/`next` attributes -- one chain per frame -- so order is recovered
    by starting at each head (`prev == 0`) and following `next`.

    Chain order is used rather than document order because a tuplet's extent is
    measured in played time; reading records in file order would silently
    mis-assign spans wherever the two differ.
    """
    following: dict[int, int] = {}
    written: dict[int, int] = {}
    grace: set[int] = set()
    heads: list[int] = []
    for record in document.entries.records:
        entnum = int(record.attrs["entnum"])
        if "graceNote" in record.fields:
            grace.add(entnum)
        raw_duration = _scalar(record, "dura")
        if raw_duration is None:
            raise CorruptScoreError(f"entry {entnum} has no dura")
        written[entnum] = int(raw_duration)
        following[entnum] = int(record.attrs.get("next", 0) or 0)
        if not int(record.attrs.get("prev", 0) or 0):
            heads.append(entnum)

    order: list[int] = []
    seen: set[int] = set()
    for head in heads:
        entnum = head
        while entnum and entnum in written and entnum not in seen:
            seen.add(entnum)
            order.append(entnum)
            entnum = following.get(entnum, 0)
    # Any entry not reachable from a head still needs a duration reported; a
    # broken link must not silently drop notes.
    order.extend(entnum for entnum in written if entnum not in seen)
    return EntryChain(order=order, written_edu=written, grace_notes=frozenset(grace))
