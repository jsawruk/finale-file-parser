"""What points at an entry, and what that entry decodes to.

The reader walks one direction: a `gfhold` names a frame, a `frameSpec` names
an entry range, and details hang off an `entnum`. `locate_entries` is that
walk. Reading a report the question is the reverse, and this module answers it.

It re-walks rather than calling `locate_entries`, and that duplication is
deliberate: `locate_entries` raises `MalformedScoreError` on exactly the
documents a diagnostic report exists for. Nothing here raises. A broken link
becomes a sentence in `unresolved`, and the rest of the answer still arrives.

The duplication is contained in two places, and it needs both.
`tests/report/test_entry_facts_corpus_sweep.py` asserts the two agree on every
corpus document `locate_entries` accepts -- wide, but `corpus/` is gitignored,
so it is skipped in CI and the bet would be undefended exactly where nobody is
watching. `test_the_two_walks_agree_on_a_document_locate_entries_accepts` in
`tests/report/test_entry_facts.py` runs both walks over synthetic documents
that need no corpus, so the realistic drifts are caught everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.enigma.key import decode_key
from finale_file_parser.enigma.location import effective_keys
from finale_file_parser.enigma.music import Note, NoteValue, read_entry
from finale_file_parser.enigma.pitch import StaffTransposition, read_transposition, spell_note
from finale_file_parser.errors import FinaleFileError

__all__ = [
    "DOCUMENT_KEY",
    "EntryDecode",
    "EntryFacts",
    "NoteFacts",
    "Placement",
    "Reference",
    "build_entry_index",
    "decode_entry",
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

    tree_tag: str | None = None
    tree_key: str | None = None
    """Which Records-tree row this reference selects, or None for neither.

    Separate from `tag`/`key` because the two are not always the same record
    *name*. A `.musx` tree renders the very records this walk read, so the two
    pairs are equal. A `.mus` tree is built from the raw numeric pool instead
    (`report.model._mus_detail_entry`), so its rows are keyed
    `(cmper1, cmper2, inci)` under a numeric tag and nothing here could match
    one -- `report.model` retargets these two fields against the raw records
    after the index is built.

    None on either means the reference has no row to point at, and the page
    must render it as plain text with no click affordance. Pointing at the
    wrong record would be worse than pointing at nothing.
    """


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
    duration_base: str
    """The base note value alone, e.g. "quarter" -- no dots folded in."""

    dots: int
    duration_name: str
    """The readable, dotted name, e.g. "dotted quarter" -- composed from
    `duration_base` and `dots` here in Python, not in the page's JavaScript
    (see the module docstring on why this feature never decodes client-side)."""

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


DOCUMENT_KEY = "document"
"""Index key for the failures that belong to no single entry.

Not an entry number. Every real key in the index is `str(entnum)`, so no
document can produce this one however it numbers its entries -- which is the
point: these messages used to be filed under entnum `0`, on the reasoning that
0 is not a valid entry number. Nothing enforced that. `entnum` comes out of the
file and `EntriesPool` accepts `entnum="0"`, so a hostile document could
declare one and collect every document-level failure into that single entry's
facts, from where `report.model` promotes them into the notes as though one
entry had caused them all.
"""

_MAX_DOCUMENT_FAILURES = 200
"""How many document-level failures one document's walk records, at most.

The allocation guard for the tolerant walk, and the counterpart of
`_MAX_PLACEMENTS_PER_ENTRY`. A failure that belongs to no single entry -- an
absent `frameSpec`, a chain that breaks, a frame slot that is not a number --
is recorded and the walk continues, so the count is `gfholds x 4 slots x
frameSpec incidences`, every factor of it read out of the file and none of
them bounded relative to the others. A crafted document of a few hundred
kilobytes can ask for millions of ~80-character messages, which are held in
memory and then embedded in the report. `locate_entries` cannot reach this
shape because it raises at the first failure; tolerance is what creates it.

Sized well above any honest document: a document broken in more than 200
distinct places is one nobody reads message 201 of, and the count of what was
dropped is kept, so nothing is silently lost. Per-entry messages are not
capped here -- there are at most two of those per entry ("no frame reaches
this entry" and the placement cap), so they are already bounded by the entry
pool itself.
"""


@dataclass
class _Failures:
    """The unresolved messages a walk has recorded, under the document cap.

    Document-level failures are capped and counted here rather than at the
    consumer, because it is the accumulation itself that costs memory: a cap
    applied when the list is copied into the report would have held the whole
    list first.
    """

    by_entry: dict[str, list[str]] = field(default_factory=dict)
    dropped: int = 0

    def document(self, message: str) -> None:
        """Record a failure that belongs to no single entry, or count it as
        dropped once the cap is reached."""
        here = self.by_entry.setdefault(DOCUMENT_KEY, [])
        if len(here) >= _MAX_DOCUMENT_FAILURES:
            self.dropped += 1
            return
        here.append(message)

    def entry(self, entnum: int, message: str) -> None:
        """Record a failure that belongs to one entry. Bounded by the entry
        pool: the walk writes at most two of these per entry."""
        self.by_entry.setdefault(str(entnum), []).append(message)

    def result(self) -> dict[str, list[str]]:
        """The messages, with a counted tail when the cap dropped any."""
        if self.dropped:
            self.by_entry.setdefault(DOCUMENT_KEY, []).append(
                f"... and {self.dropped} further document-level failures, which are not "
                f"recorded: this document broke more than {_MAX_DOCUMENT_FAILURES} links "
                "and only the first are kept"
            )
        return self.by_entry


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
            key = _identity(record)
            # The `.musx` targeting, which is the identity itself: there the
            # tree renders these same records. `report.model` replaces both
            # fields on the `.mus` path, where it does not.
            out.append(
                Reference(
                    pool="details",
                    tag=record.tag,
                    key=key,
                    tree_tag=record.tag,
                    tree_key=key,
                )
            )
    return tuple(out)


def _references_by_entnum(doc: EnigmaDocument) -> dict[str, tuple[Reference, ...]]:
    """`references_to`, grouped for every entnum in one pass.

    `references_to(doc, entnum)` rescans all of `doc.details.records` on every
    call; called once per entry from `build_entry_index`'s loop that makes the
    whole index cost `entries x details`, both counts read straight out of the
    file and uncapped relative to each other. This groups once instead: one
    pass over `doc.details.records`, and the loop then does a dict lookup per
    entry -- linear in each count rather than their product.

    Grouped by the record's raw `entnum` attribute string, not by an `int` of
    it, so an entnum this can't parse still groups (and simply never matches
    any real entry's `str(entnum)` lookup) -- the same fate `references_to`
    gives it via its `== str(entnum)` string comparison. Keeping the two
    string-keyed lets them agree by construction rather than by two separate
    int-parsing rules staying in sync.
    """
    grouped: dict[str, list[Reference]] = {}
    for record in doc.details.records:
        raw_entnum = record.attrs.get("entnum")
        if not isinstance(raw_entnum, str):
            continue
        key = _identity(record)
        grouped.setdefault(raw_entnum, []).append(
            Reference(
                pool="details",
                tag=record.tag,
                key=key,
                tree_tag=record.tag,
                tree_key=key,
            )
        )
    return {entnum: tuple(references) for entnum, references in grouped.items()}


def placements_by_entry(
    doc: EnigmaDocument,
) -> tuple[dict[int, list[Placement]], dict[str, list[str]]]:
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
    -- is filed under `DOCUMENT_KEY`, which no entry number can equal, so a
    document that declares an entry numbered 0 does not absorb them. How many
    of those a document has is a number the file decides, so they are capped at
    `_MAX_DOCUMENT_FAILURES` with a counted tail; see that constant.

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
    failures = _Failures()
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
                failures.document(
                    f"gfhold {key} {field_name} is {value!r}, which is not a frame number"
                )
                continue
            specs = tuple(
                f for f in doc.others.all_with("frameSpec", frame) if "part" not in f.attrs
            )
            if not specs:
                failures.document(
                    f"gfhold {key} {field_name} names frameSpec {frame}, which is absent"
                )
                continue
            for spec in specs:
                raw_start = spec.fields.get("startEntry")
                raw_end = spec.fields.get("endEntry")
                if raw_start is None and raw_end is None:
                    # Neither bound is a legitimate empty layer, exactly as
                    # `locate_entries` reads it: the incidence exists, with
                    # other fields, and simply never got an entry chain.
                    continue
                start = _as_int(raw_start)
                end = _as_int(raw_end)
                if start is None or end is None:
                    # One bound, or a bound that is not a number: malformed,
                    # and `locate_entries` raises. Say so -- skipped silently,
                    # the entries reported "no frame reaches this entry" and
                    # nothing anywhere said why, which is the wrong absence.
                    failures.document(
                        f"gfhold {key} {field_name} frameSpec {frame} has startEntry "
                        f"{raw_start!r} and endEntry {raw_end!r}: an entry range needs both"
                    )
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
                    failures=failures,
                    guard=_CHAIN_GUARD,
                    cap=_MAX_PLACEMENTS_PER_ENTRY,
                    capped=capped,
                )

    for entnum in sorted(entries_by_num):
        if entnum not in placements:
            failures.entry(entnum, "no frame reaches this entry")
    return placements, failures.result()


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
    failures: _Failures,
    guard: int,
    cap: int,
    capped: set[int],
) -> None:
    """Follow one entry chain from `start` to `end` via each entry's `next`.

    Mirrors `locate_entries._walk_entry_chain`, but every place that function
    raises, this records a message against the document (`_Failures.document`,
    which is capped) and stops -- the entries already placed on this walk stay
    placed.

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
            failures.document(
                f"gfhold {key} frame {frame} entry chain exceeded {guard} steps (cycle?)"
            )
            return
        entry = entries_by_num.get(entnum)
        if entry is None:
            failures.document(f"gfhold {key} frame {frame} chain references missing entry {entnum}")
            return
        if len(placements.get(entnum, ())) >= cap:
            if entnum not in capped:
                capped.add(entnum)
                failures.entry(
                    entnum,
                    f"entry {entnum} reached the {cap}-placement cap; further claims on it "
                    "are not recorded (a real mirror places one entry on a few staves, not "
                    "this many)",
                )
            return
        placements.setdefault(entnum, []).append(
            Placement(staff=staff, measure=measure, layer=layer, gfhold_key=key, frame=frame)
        )
        if entnum == end:
            return
        next_entnum = _as_int(entry.attrs.get("next"))
        if next_entnum is None:
            failures.document(
                f"gfhold {key} frame {frame} chain broke before reaching entry {end}: "
                f"entry {entnum} has no valid next"
            )
            return
        entnum = next_entnum


def decode_entry(
    record: Record,
    key_raw: int | None,
    transposition: StaffTransposition | None,
) -> EntryDecode | None:
    """What this entry decodes to: duration always, pitch where it is knowable.

    `read_entry` needs nothing but the record, so the duration and each note's
    stored values are always available. Spelling needs the key in force and the
    staff's transposition, both of which come from the placement -- so both can
    be missing, and when either is the note carries `why_not` instead of a
    pitch. There is no default key: a spelled pitch here is one the document
    supports, or there is none.

    Returns None when the record will not read as an entry at all, which is the
    caller's cue to record that in `unresolved`.
    """
    try:
        entry = read_entry(record)
    except FinaleFileError:
        return None

    notes: list[NoteFacts] = []
    for note in entry.notes:
        spelled, why_not = _spell(note, key_raw, transposition)
        notes.append(
            NoteFacts(
                harm_lev=note.harm_lev, harm_alt=note.harm_alt, spelled=spelled, why_not=why_not
            )
        )
    base_name = _base_name(entry.duration.base)
    return EntryDecode(
        duration_edu=entry.duration.edu,
        duration_base=base_name,
        dots=entry.duration.dots,
        duration_name=_dotted_name(base_name, entry.duration.dots),
        is_rest=entry.is_rest,
        notes=tuple(notes),
    )


_DURATION_NAMES: dict[NoteValue, str] = {
    NoteValue.BREVE: "breve",
    NoteValue.WHOLE: "whole",
    NoteValue.HALF: "half",
    NoteValue.QUARTER: "quarter",
    NoteValue.EIGHTH: "eighth",
    NoteValue.SIXTEENTH: "16th",
    NoteValue.THIRTY_SECOND: "thirty-second",
    NoteValue.SIXTY_FOURTH: "64th",
    NoteValue.ONE_TWENTY_EIGHTH: "128th",
}
"""What a musician calls each note value.

Spelled out rather than derived from the member name: `NoteValue.name` lowered
with its underscores turned to spaces gives "thirty second" and "one twenty
eighth", which are the enum's spelling of a number and not notation's spelling
of a duration. Every member is covered, and
`test_every_note_value_is_spelled_the_way_a_musician_writes_it` fails if a
member is added without one.
"""


def _base_name(base: NoteValue) -> str:
    """The readable name of a base note value.

    Falls back to the member name for a value added without an entry above --
    ugly, and deliberately so: this is a diagnostic report and a wrong-but-tidy
    name would be worse than an obviously unnamed one. The test pins the table
    complete so the fallback stays unreachable.
    """
    return _DURATION_NAMES.get(base, base.name.lower().replace("_", " "))


def _dotted_name(base_name: str, dots: int) -> str:
    """The readable name for a base note value plus its augmentation dots.

    One dot is "dotted", two is "double dotted" -- the only two words actual
    notation uses. Beyond that there is no established word (and inventing one
    would be a guess this project does not make elsewhere), so the count is
    spelled out instead: "3-dot quarter".
    """
    if dots <= 0:
        return base_name
    if dots == 1:
        return f"dotted {base_name}"
    if dots == 2:
        return f"double dotted {base_name}"
    return f"{dots}-dot {base_name}"


def _spell(
    note: Note, key_raw: int | None, transposition: StaffTransposition | None
) -> tuple[str | None, str | None]:
    """`(spelled, why_not)` -- exactly one of the two is ever set."""
    if key_raw is None:
        return None, "no key in force (placement unresolved)"
    if transposition is None:
        return None, "no staffSpec transposition for this staff"
    try:
        spelled = spell_note(note, decode_key(key_raw), transposition)
    except FinaleFileError as error:
        return None, f"{type(error).__name__}: {error}"
    return spelled.written.name, None


def _as_int(value: object) -> int | None:
    """A field or attribute as an int, or None when it is not one. Absence is
    ordinary here and never an error."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def build_entry_index(doc: EnigmaDocument) -> dict[str, EntryFacts]:
    """One `EntryFacts` per entry in the document.

    Keyed by `str(entnum)` because this is embedded as JSON, where an object
    key is a string. Every entry gets an entry in the index, including one
    nothing points at -- "nothing points at this" is an answer, and a reader
    chasing a missing note needs it more than the ordinary case.

    A mirrored entry carries two placements, on different staves that may
    transpose differently, so the key and transposition used for spelling are
    always the *first* placement's. The pane in Task 6 shows every placement,
    so a reader can see there was more than one and that the spelling shown is
    only one of them.

    `effective_keys` is not tolerant -- unlike `placements_by_entry` and
    `_transpositions`, it raises `MalformedScoreError` on a `measSpec` this
    document gets wrong (a non-integer `cmper`, a missing or non-scalar
    `keySig.key`, or cmpers spanning more measures than `_MAX_MEASURE_SPAN`
    resolves), and deliberately: it carries the rule that an absent
    `keySig` means C major, not a continuation of the previous key, and a
    second, degrade-per-measure copy of that rule here would risk getting it
    wrong the way the original getting it wrong once already mis-spelled 18
    passages across this project. So on failure this loses every spelling
    for the whole document, rather than guessing measure by measure: every
    note reports `spelled=None` with the existing "no key in force" reason,
    and the one message below says why, filed under `DOCUMENT_KEY` the same
    way `placements_by_entry` files failures that belong to no single entry.
    """
    placements, unresolved = placements_by_entry(doc)
    try:
        keys = effective_keys(doc)
    except FinaleFileError as error:
        keys = {}
        unresolved.setdefault(DOCUMENT_KEY, []).append(
            f"no key could be resolved for this document, so no note can be spelled: "
            f"{type(error).__name__}: {error}"
        )
    transpositions = _transpositions(doc)
    references = _references_by_entnum(doc)

    index: dict[str, EntryFacts] = {}
    for record in doc.entries.of_tag("entry"):
        entnum = _as_int(record.attrs.get("entnum"))
        if entnum is None:
            continue
        places = tuple(placements.get(entnum, ()))
        first = places[0] if places else None
        key_raw = keys.get(first.measure) if first and first.measure is not None else None
        transposition = (
            transpositions.get(first.staff) if first and first.staff is not None else None
        )
        decode = decode_entry(record, key_raw, transposition)
        messages = list(unresolved.get(str(entnum), ()))
        if decode is None:
            messages.append("this record does not read as an entry")
        index[str(entnum)] = EntryFacts(
            placements=places,
            named_by=references.get(str(entnum), ()),
            decode=decode,
            unresolved=tuple(messages),
        )

    if unresolved.get(DOCUMENT_KEY):
        # Its own key, which no entry number can equal, so a document that
        # declares an entry numbered 0 keeps that entry's facts and this bucket
        # separate rather than merging the two.
        index[DOCUMENT_KEY] = EntryFacts(unresolved=tuple(unresolved[DOCUMENT_KEY]))
    return index


def _transpositions(doc: EnigmaDocument) -> dict[int, StaffTransposition]:
    """Each staff's written-to-sounding interval, by staff number.

    The same shape `to_ir._transpositions` builds, and for the same reason:
    score records only, since a linked-part staffSpec describes the part.

    It duplicates rather than importing that function because
    `read_transposition` raises plain `ValueError` on a malformed
    `transposition`/`keysig` sub-record, and `to_ir._transpositions` lets that
    propagate -- correct there, where a bad document should fail the whole
    conversion. Here it must not: a malformed staffSpec becomes "no
    transposition for this staff" on the affected notes, and every other
    staff's transposition stays available.
    """
    out: dict[int, StaffTransposition] = {}
    for record in doc.others.of_tag("staffSpec"):
        if "part" in record.attrs:
            continue
        cmper = _as_int(record.attrs.get("cmper"))
        if cmper is None:
            continue
        try:
            out[cmper] = read_transposition(record)
        except (ValueError, FinaleFileError):
            continue
    return out
