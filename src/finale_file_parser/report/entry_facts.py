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
