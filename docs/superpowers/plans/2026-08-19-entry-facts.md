# Entry Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selecting an entry in the report's Records tree shows what points at that entry and what it decodes to.

**Architecture:** A new module `report/entry_facts.py` builds one index over the parsed `EnigmaDocument`: for each entry, its placements (via a tolerant re-walk of gfhold -> frameSpec that records broken links instead of raising), the details records naming its `entnum`, and its decode (`read_entry` plus `spell_note` when a key and transposition resolve). `report/model.py` calls it once and stores the result on `Inspection.entry_index`; `report/html.py` renders `entry_index[entnum]` and does no decoding or joining of its own.

**Tech Stack:** Python 3.12, dataclasses, pytest, mypy --strict, ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-19-entry-facts-design.md`

## Global Constraints

- Toolchain is `make` only: `make check` (lint + format + types + tests) between edits, `make check-full` before pushing. Never invoke pytest/ruff/mypy ad hoc as the gate.
- Prefix every make invocation with `UV_OFFLINE=1`; the sandbox has no PyPI access.
- `mypy --strict` must pass. Every new function is fully annotated.
- Line length 100. Run `make fmt` before committing if `make check` reports a format diff.
- Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- The walk must **never raise**. Every failure becomes a string in `unresolved`.
- No fabricated musical values. A missing key produces no spelling, never C major.
- Never `git add -A`. Add explicit paths — a `corpus` symlink may be present and untracked.
- Push with an explicit `git push origin <branch>` and confirm with `git ls-remote`; `push -u` cannot write `.git/config` in this sandbox.
- `corpus/` is gitignored and absent in CI. Corpus tests must carry the existing skip marker; unit tests must not need a corpus.

## Existing interfaces this plan consumes

Verbatim from the source, so no task has to guess:

```python
# enigma/document.py
Record(tag: str, attrs: Mapping[str, str], text: str,
       fields: Mapping[str, str | tuple[str, ...] | Record | tuple[Record, ...]])
EnigmaDocument.details.of_tag(tag) -> tuple[Record, ...]
EnigmaDocument.others.of_tag(tag)  -> tuple[Record, ...]
EnigmaDocument.others.all_with(tag, cmper) -> tuple[Record, ...]
EnigmaDocument.entries.of_tag("entry") -> tuple[Record, ...]

# enigma/location.py
locate_entries(doc) -> dict[int, tuple[EntryLocation, ...]]   # raises MalformedScoreError
effective_keys(doc) -> dict[int, int]                          # measure -> raw key
EntryLocation(entnum: int, staff: int, measure: int, key_signature: int, layer: int)
_FRAME_FIELDS = ("frame1", "frame2", "frame3", "frame4")

# enigma/music.py
read_entry(record: Record) -> Entry                            # raises MalformedEntryError
Entry(entnum: int, duration: Duration, is_rest: bool, notes: tuple[Note, ...])
Duration(edu: int, base: NoteValue, dots: int)
Note(harm_lev: int, harm_alt: int, tie_start: bool, tie_end: bool)
NoteValue.QUARTER = 1024   # .name is "QUARTER"

# enigma/key.py
decode_key(raw: int) -> KeySignature
KeySignature(fifths: int, mode: Mode, tonic: str)

# enigma/pitch.py
read_transposition(staff_spec: Record) -> StaffTransposition
StaffTransposition(interval: int, adjust: int)
spell_note(note: Note, concert_key: KeySignature,
           transposition: StaffTransposition) -> SpelledNote
SpelledNote(written: SpelledPitch, concert: SpelledPitch)
```

---
### Task 1: The types, and the references that name an entry

**Files:**
- Create: `src/finale_file_parser/report/entry_facts.py`
- Test: `tests/report/test_entry_facts.py`

**Interfaces:**
- Consumes: `EnigmaDocument`, `Record` from `enigma.document`.
- Produces: `Placement`, `Reference`, `NoteFacts`, `EntryDecode`, `EntryFacts` dataclasses, and `references_to(doc, entnum) -> tuple[Reference, ...]`.

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the report's entry facts. No corpus: every document here is
built in process, so CI runs these even though `corpus/` is gitignored."""

from __future__ import annotations

from finale_file_parser.enigma.document import EnigmaDocument, Record
from finale_file_parser.report.entry_facts import Reference, references_to


def _doc(details: tuple[Record, ...] = (), others: tuple[Record, ...] = (),
         entries: tuple[Record, ...] = ()) -> EnigmaDocument:
    """A document holding only the pools a test needs."""
    from finale_file_parser.enigma.document import parse_enigma
    raise NotImplementedError  # replaced in Step 3


def test_references_name_only_records_holding_this_entnum() -> None:
    """A record counts as a reference when it names the entry, not when it
    merely sits in the same measure -- otherwise "points at" becomes "is near"."""
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})
    other = Record(tag="articAssign", attrs={"entnum": "11", "inci": "0"}, text="", fields={})
    doc = _doc(details=(artic, other))

    assert references_to(doc, 9) == (Reference(pool="details", tag="articAssign", key="(entnum 9, inci 0)"),)
```

- [ ] **Step 2: Run it to see it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q`
Expected: FAIL — `ModuleNotFoundError: finale_file_parser.report.entry_facts`

- [ ] **Step 3: Replace the `_doc` helper with one that really builds a document**

`EnigmaDocument` is constructed from pools. Read `tests/enigma/test_location.py::_doc` and copy that construction exactly rather than inventing one — it is the established way to build a synthetic document in this repo, and it is already known to satisfy the pool types.

- [ ] **Step 4: Write the module**

```python
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

from dataclasses import dataclass, field

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
```

- [ ] **Step 5: Run the test to see it pass**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q`
Expected: PASS

- [ ] **Step 6: Run the gate**

Run: `UV_OFFLINE=1 make check`
Expected: all checks passed. Run `UV_OFFLINE=1 make fmt` first if it reports a format diff.

- [ ] **Step 7: Commit**

```bash
git add src/finale_file_parser/report/entry_facts.py tests/report/test_entry_facts.py
git commit -m "feat: name the records that point at an entry"
```

---
### Task 2: The tolerant placement walk

**Files:**
- Modify: `src/finale_file_parser/report/entry_facts.py`
- Test: `tests/report/test_entry_facts.py`

**Interfaces:**
- Consumes: `Placement` from Task 1; `_FRAME_FIELDS` from `enigma.location`.
- Produces: `placements_by_entry(doc) -> tuple[dict[int, list[Placement]], dict[int, list[str]]]` — placements per entnum, and unresolved messages per entnum. Both keyed by entnum.

- [ ] **Step 1: Write the failing tests — one per failure mode**

```python
def test_a_clean_chain_places_an_entry() -> None:
    gfhold = Record(tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="",
                    fields={"frame1": "12"})
    frame = Record(tag="frameSpec", attrs={"cmper": "12"}, text="",
                   fields={"startEntry": "9", "endEntry": "9"})
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="",
                   fields={"dura": "1024", "numNotes": "0"})
    places, unresolved = placements_by_entry(_doc(details=(gfhold,), others=(frame,), entries=(entry,)))

    assert places[9] == [Placement(staff=1, measure=3, layer=1, gfhold_key="(cmper1 1, cmper2 3)", frame=12)]
    assert unresolved.get(9, []) == []


def test_a_missing_frame_spec_still_places_what_it_knows() -> None:
    """The failure `locate_entries` raises on. Staff, measure and layer are all
    known from the gfhold -- only the entry range is lost -- so the report says
    where the entry was meant to sit and which link broke."""
    gfhold = Record(tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="",
                    fields={"frame1": "12"})
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, unresolved = placements_by_entry(_doc(details=(gfhold,), entries=(entry,)))

    assert places.get(9, []) == []
    assert unresolved[0] == ["gfhold (cmper1 1, cmper2 3) frame1 names frameSpec 12, which is absent"]


def test_an_entry_no_frame_reaches_is_named_as_such() -> None:
    """`locate_entries` raises "orphan entry"; here it is a fact about that
    entry rather than a verdict on the document."""
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, unresolved = placements_by_entry(_doc(entries=(entry,)))

    assert places.get(9, []) == []
    assert unresolved[9] == ["no frame reaches this entry"]


def test_a_part_variant_gfhold_does_not_place_a_second_time() -> None:
    """Score records only, exactly as `locate_entries` does: a linked-part
    gfhold would place the same entry twice and read as a mirror."""
    score = Record(tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="", fields={"frame1": "12"})
    part = Record(tag="gfhold", attrs={"cmper1": "1", "cmper2": "3", "part": "1"}, text="",
                  fields={"frame1": "12"})
    frame = Record(tag="frameSpec", attrs={"cmper": "12"}, text="",
                   fields={"startEntry": "9", "endEntry": "9"})
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, _ = placements_by_entry(_doc(details=(score, part), others=(frame,), entries=(entry,)))

    assert len(places[9]) == 1


def test_a_mirror_places_one_entry_twice() -> None:
    """Two gfholds naming one frame is a Finale mirror, and both placements are
    real -- this is the shape `locate_entries` was changed to allow."""
    a = Record(tag="gfhold", attrs={"cmper1": "4", "cmper2": "3"}, text="", fields={"frame1": "12"})
    b = Record(tag="gfhold", attrs={"cmper1": "14", "cmper2": "3"}, text="", fields={"frame1": "12"})
    frame = Record(tag="frameSpec", attrs={"cmper": "12"}, text="",
                   fields={"startEntry": "9", "endEntry": "9"})
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    places, _ = placements_by_entry(_doc(details=(a, b), others=(frame,), entries=(entry,)))

    assert sorted(p.staff for p in places[9]) == [4, 14]
```

The `unresolved[0]` key in the second test is deliberate: a failure that belongs to no single entry (the frame is missing, so no entnum is known) is filed under `0`. Say so in the implementation's docstring.

- [ ] **Step 2: Run them to see them fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q`
Expected: FAIL — `cannot import name 'placements_by_entry'`

- [ ] **Step 3: Implement the walk**

```python
def placements_by_entry(
    doc: EnigmaDocument,
) -> tuple[dict[int, list[Placement]], dict[int, list[str]]]:
    """Walk gfhold -> frameSpec -> entry range, recording breaks instead of raising.

    Mirrors `locate_entries`, and deliberately: see the module docstring. The
    differences are all in what happens when something is wrong.

    A failure that belongs to no single entry -- a frame that is absent, so no
    entry number is ever learned -- is filed under entnum `0`, which is not a
    valid entry number and so cannot collide with a real one.
    """
    from finale_file_parser.enigma.location import _FRAME_FIELDS

    placements: dict[int, list[Placement]] = {}
    unresolved: dict[int, list[str]] = {}
    known = {
        _as_int(record.attrs.get("entnum"))
        for record in doc.entries.of_tag("entry")
    } - {None}

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
                for entnum in range(start, end + 1):
                    placements.setdefault(entnum, []).append(
                        Placement(staff=staff, measure=measure, layer=layer,
                                  gfhold_key=key, frame=frame)
                    )

    for entnum in sorted(n for n in known if n is not None):
        if entnum not in placements:
            unresolved.setdefault(entnum, []).append("no frame reaches this entry")
    return placements, unresolved


def _as_int(value: object) -> int | None:
    """A field or attribute as an int, or None when it is not one. Absence is
    ordinary here and never an error."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
```

Note: the entry range is walked as `range(start, end + 1)` rather than by
following each entry's `next` chain. `locate_entries` follows the chain; the
agreement sweep in Task 7 is what proves the two produce the same placements on
every document it accepts. If that sweep fails, the chain walk is the correct
one and this must follow it — do not adjust the sweep to match this.

- [ ] **Step 4: Run the tests to see them pass**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q`
Expected: PASS (all five)

- [ ] **Step 5: Run the gate**

Run: `UV_OFFLINE=1 make check`

- [ ] **Step 6: Commit**

```bash
git add src/finale_file_parser/report/entry_facts.py tests/report/test_entry_facts.py
git commit -m "feat: walk gfhold to frameSpec tolerantly for the report"
```

---
### Task 3: The decode, raw and spelled

**Files:**
- Modify: `src/finale_file_parser/report/entry_facts.py`
- Test: `tests/report/test_entry_facts.py`

**Interfaces:**
- Consumes: `Placement`, `EntryDecode`, `NoteFacts` from Tasks 1-2.
- Produces: `decode_entry(record, key_raw, transposition) -> EntryDecode | None`, where `key_raw: int | None` and `transposition: StaffTransposition | None`.

- [ ] **Step 1: Write the failing tests**

```python
from finale_file_parser.enigma.pitch import StaffTransposition
from finale_file_parser.report.entry_facts import EntryDecode, NoteFacts, decode_entry


def _entry_record(dura: str = "1024", notes: tuple[Record, ...] = ()) -> Record:
    return Record(tag="entry", attrs={"entnum": "9"}, text="",
                  fields={"dura": dura, "numNotes": str(len(notes)), "note": notes})


def _note(harm_lev: str, harm_alt: str = "0") -> Record:
    return Record(tag="note", attrs={}, text="",
                  fields={"harmLev": harm_lev, "harmAlt": harm_alt})


def test_duration_and_raw_values_need_nothing_but_the_entry() -> None:
    """The half that always works: no key, no transposition, still a decode."""
    decode = decode_entry(_entry_record(notes=(_note("4"),)), key_raw=None, transposition=None)

    assert decode is not None
    assert (decode.duration_edu, decode.duration_name) == (1024, "QUARTER")
    assert decode.notes[0].harm_lev == 4
    assert decode.notes[0].spelled is None


def test_a_missing_key_produces_no_spelling_and_says_why() -> None:
    """Never a C-major default: an absent key means the pitch is unknown, and
    the report says which input was missing rather than inventing one."""
    decode = decode_entry(_entry_record(notes=(_note("4"),)), key_raw=None,
                          transposition=StaffTransposition(interval=0, adjust=0))

    assert decode is not None
    assert decode.notes[0].spelled is None
    assert decode.notes[0].why_not == "no key in force (placement unresolved)"


def test_a_missing_transposition_produces_no_spelling_and_says_why() -> None:
    decode = decode_entry(_entry_record(notes=(_note("4"),)), key_raw=2, transposition=None)

    assert decode is not None
    assert decode.notes[0].spelled is None
    assert decode.notes[0].why_not == "no staffSpec transposition for this staff"


def test_a_resolved_note_spells_a_pitch() -> None:
    """harmLev 4 in D major (raw key 2) is F#4 -- the fourth diatonic step above
    the tonic, with the sharp the key provides."""
    decode = decode_entry(_entry_record(notes=(_note("4"),)), key_raw=2,
                          transposition=StaffTransposition(interval=0, adjust=0))

    assert decode is not None
    assert decode.notes[0].spelled == "F#4"
    assert decode.notes[0].why_not is None


def test_an_entry_that_will_not_read_yields_no_decode() -> None:
    """`read_entry` raises `MalformedEntryError` on a record it cannot type.
    That is one entry's problem, not the report's: return None and let the
    caller record it in `unresolved`."""
    assert decode_entry(Record(tag="entry", attrs={}, text="", fields={}),
                        key_raw=2, transposition=None) is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q -k decode`
Expected: FAIL — `cannot import name 'decode_entry'`

- [ ] **Step 3: Implement**

```python
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
            NoteFacts(harm_lev=note.harm_lev, harm_alt=note.harm_alt,
                      spelled=spelled, why_not=why_not)
        )
    return EntryDecode(
        duration_edu=entry.duration.edu,
        duration_name=entry.duration.base.name,
        is_rest=entry.is_rest,
        notes=tuple(notes),
    )


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
    written = spelled.written
    return f"{written.step}{_ACCIDENTAL.get(written.alteration, '')}{written.octave}", None


_ACCIDENTAL = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}
"""How an alteration is written beside a step. Report text, not a decode: the
alteration itself comes from `spell_note` and is not reinterpreted here."""
```

Add to the module's imports:

```python
from finale_file_parser.enigma.key import decode_key
from finale_file_parser.enigma.music import Note, read_entry
from finale_file_parser.enigma.pitch import StaffTransposition, spell_note
from finale_file_parser.errors import FinaleFileError
```

and to `__all__`: `"decode_entry"`.

**Check `SpelledPitch`'s field names before running.** This plan assumes
`step`, `alteration` and `octave`. Run
`UV_OFFLINE=1 uv run python -c "from finale_file_parser.enigma.pitch import SpelledPitch; print(SpelledPitch.__dataclass_fields__.keys())"`
and use whatever it prints. If the names differ, fix `_spell` — do not adjust
the expected `"F#4"` in the test.

- [ ] **Step 4: Run the tests to see them pass**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q`
Expected: PASS

- [ ] **Step 5: Run the gate**

Run: `UV_OFFLINE=1 make check`

- [ ] **Step 6: Commit**

```bash
git add src/finale_file_parser/report/entry_facts.py tests/report/test_entry_facts.py
git commit -m "feat: decode an entry's duration and pitches for the report"
```

---

### Task 4: Compose the index

**Files:**
- Modify: `src/finale_file_parser/report/entry_facts.py`
- Test: `tests/report/test_entry_facts.py`

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: `build_entry_index(doc: EnigmaDocument) -> dict[str, EntryFacts]`, keyed by `str(entnum)` — a string because it is embedded as JSON, where object keys are strings.

- [ ] **Step 1: Write the failing test**

```python
def test_the_index_answers_both_questions_for_one_entry() -> None:
    gfhold = Record(tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="",
                    fields={"frame1": "12"})
    frame = Record(tag="frameSpec", attrs={"cmper": "12"}, text="",
                   fields={"startEntry": "9", "endEntry": "9"})
    meas = Record(tag="measSpec", attrs={"cmper": "3"}, text="",
                  fields={"keySig": Record(tag="keySig", attrs={}, text="", fields={"key": "2"})})
    staff = Record(tag="staffSpec", attrs={"cmper": "1"}, text="", fields={})
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="",
                   fields={"dura": "1024", "numNotes": "1",
                           "note": (Record(tag="note", attrs={}, text="",
                                           fields={"harmLev": "4", "harmAlt": "0"}),)})

    index = build_entry_index(_doc(details=(gfhold, artic), others=(frame, meas, staff),
                                   entries=(entry,)))

    facts = index["9"]
    assert facts.placements[0].staff == 1 and facts.placements[0].measure == 3
    assert facts.named_by[0].tag == "articAssign"
    assert facts.decode is not None and facts.decode.duration_name == "QUARTER"
    assert facts.decode.notes[0].spelled == "F#4"
    assert facts.unresolved == ()


def test_the_index_never_raises_on_a_broken_document() -> None:
    """The property the whole module exists for. `locate_entries` refuses this
    document; the index must still answer what it can."""
    gfhold = Record(tag="gfhold", attrs={"cmper1": "1", "cmper2": "3"}, text="",
                    fields={"frame1": "12"})   # frameSpec 12 absent
    entry = Record(tag="entry", attrs={"entnum": "9"}, text="", fields={"dura": "1024"})
    artic = Record(tag="articAssign", attrs={"entnum": "9", "inci": "0"}, text="", fields={})

    index = build_entry_index(_doc(details=(gfhold, artic), entries=(entry,)))

    assert index["9"].placements == ()
    assert index["9"].named_by[0].tag == "articAssign"      # survives independently
    assert index["9"].decode is not None                     # needs only the entry
    assert index["9"].unresolved == ("no frame reaches this entry",)
```

- [ ] **Step 2: Run to see it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q -k index`
Expected: FAIL — `cannot import name 'build_entry_index'`

- [ ] **Step 3: Implement**

```python
def build_entry_index(doc: EnigmaDocument) -> dict[str, EntryFacts]:
    """One `EntryFacts` per entry in the document.

    Keyed by `str(entnum)` because this is embedded as JSON, where an object
    key is a string. Every entry gets an entry in the index, including one
    nothing points at -- "nothing points at this" is an answer, and a reader
    chasing a missing note needs it more than the ordinary case.
    """
    placements, unresolved = placements_by_entry(doc)
    keys = effective_keys(doc)
    transpositions = _transpositions(doc)

    index: dict[str, EntryFacts] = {}
    for record in doc.entries.of_tag("entry"):
        entnum = _as_int(record.attrs.get("entnum"))
        if entnum is None:
            continue
        places = tuple(placements.get(entnum, ()))
        first = places[0] if places else None
        key_raw = keys.get(first.measure) if first and first.measure is not None else None
        transposition = transpositions.get(first.staff) if first and first.staff is not None else None
        decode = decode_entry(record, key_raw, transposition)
        messages = list(unresolved.get(entnum, ()))
        if decode is None:
            messages.append("this record does not read as an entry")
        index[str(entnum)] = EntryFacts(
            placements=places,
            named_by=references_to(doc, entnum),
            decode=decode,
            unresolved=tuple(messages),
        )
    return index


def _transpositions(doc: EnigmaDocument) -> dict[int, StaffTransposition]:
    """Each staff's written-to-sounding interval, by staff number.

    The same shape `to_ir._transpositions` builds, and for the same reason:
    score records only, since a linked-part staffSpec describes the part.
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
        except FinaleFileError:
            continue
    return out
```

Add `from finale_file_parser.enigma.location import effective_keys` and
`read_transposition` to the imports, and `"build_entry_index"` to `__all__`.

**A note on the first placement.** The key and transposition are taken from
`places[0]`. A mirrored entry has two placements on different staves, which may
transpose differently, so the spelled pitch is the one for the *first*
placement. Say so in the docstring; the pane in Task 6 shows all placements, so
a reader can see there was more than one.

- [ ] **Step 4: Run to see it pass**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts.py -x -q`
Expected: PASS

- [ ] **Step 5: Run the gate**

Run: `UV_OFFLINE=1 make check`

- [ ] **Step 6: Commit**

```bash
git add src/finale_file_parser/report/entry_facts.py tests/report/test_entry_facts.py
git commit -m "feat: build the report's entry index"
```

---
### Task 5: Carry the index on the Inspection

**Files:**
- Modify: `src/finale_file_parser/report/model.py`
- Test: `tests/report/test_model.py`

**Interfaces:**
- Consumes: `build_entry_index` from Task 4.
- Produces: `Inspection.entry_index: dict[str, object]`, and an `"entnum"` key on each entry record's report dict so the page can look one up.

- [ ] **Step 1: Write the failing test**

```python
def test_an_inspection_carries_facts_for_each_entry() -> None:
    """Both containers reach this through `_finish`, so one test covers both."""
    from finale_file_parser.report import model

    doc = ...  # build as tests/enigma/test_location.py does, with one placed entry
    inspection = model.Inspection(file={"name": "x.mus"})
    model._finish(model.Ladder(), doc, inspection, engrave_notation=False)

    assert "9" in inspection.entry_index
```

- [ ] **Step 2: Run to see it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_model.py -x -q -k entry_index`
Expected: FAIL — `Inspection` has no attribute `entry_index`

- [ ] **Step 3: Add the field**

In `Inspection`, after `xml`:

```python
    entry_index: dict[str, object] = field(default_factory=dict)
    """What points at each entry, and what it decodes to. See `report.entry_facts`.

    Keyed by entry number as a string, because this is embedded as JSON.
    Measured at 55 KB for a median `.musx` and 169 KB for the largest sampled,
    against reports of 617 KB to 7.6 MB -- small enough to build for every
    entry, which it must be: the report is a static file, so nothing can be
    computed after it is written.
    """
```

- [ ] **Step 4: Populate it in `_finish`**

`_finish` already holds the built document. After `inspection.document = summarise_document(document)`:

```python
    # Never fatal. `build_entry_index` does not raise by construction, but this
    # is a diagnostic depth on a report whose whole purpose is documents that
    # do not work -- it must not be what stops one being written.
    try:
        inspection.entry_index = {
            entnum: asdict(facts) for entnum, facts in build_entry_index(document).items()
        }
    except Exception:  # noqa: BLE001 -- a report is written or nothing is
        inspection.notes.append("entry facts unavailable: the index could not be built")
```

Import `build_entry_index` from `finale_file_parser.report.entry_facts`.

- [ ] **Step 5: Put the entnum on the entry's report row**

In `_pool_record_entry`, after the `entry` dict is built:

```python
    # The page looks facts up by entry number, so state it rather than making
    # the page parse it back out of the key text.
    entnum = record.attrs.get("entnum")
    if entnum is not None:
        entry["entnum"] = entnum
```

- [ ] **Step 6: Embed it**

In `render_html`'s payload dict in `html.py`, and in `_weight`'s dict in
`model.py`, add `"entryIndex": inspection.entry_index`. Both must list it: the
budget is computed over what is embedded, and a depth missing from `_weight` is
a depth the budget cannot see.

- [ ] **Step 7: Leave `apply_budget` alone, deliberately**

Add to `apply_budget`'s docstring:

```
    `entry_index` is not dropped. It is small next to `records` and the music
    tree, and it is the only depth that answers "what points at this entry" --
    dropping it would leave the pane that gained the feature empty while the
    two large depths it competes with stayed.
```

- [ ] **Step 8: Run the tests and the gate**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/ -x -q`
Then: `UV_OFFLINE=1 make check`
Expected: both pass.

- [ ] **Step 9: Commit**

```bash
git add src/finale_file_parser/report/model.py src/finale_file_parser/report/html.py tests/report/test_model.py
git commit -m "feat: carry entry facts on an inspection"
```

---

### Task 6: Show it in the record pane

**Files:**
- Modify: `src/finale_file_parser/report/html.py`
- Test: `tests/report/test_html.py`

**Interfaces:**
- Consumes: `data.entryIndex` in the page's JSON island; `entnum` on an entry row.
- Produces: two blocks in `showRecord`, and a clickable reference row.

- [ ] **Step 1: Write the failing test**

```python
def test_the_record_pane_shows_entry_facts_when_one_is_selected() -> None:
    """The page renders `entryIndex[entnum]` and does nothing else -- no
    decoding, no joining. That line is what keeps a second decoder out of the
    page, which is why the index is built in Python."""
    html = render_html(_inspection(entry_index={"9": {"placements": [], "named_by": [],
                                                      "decode": None, "unresolved": []}}))
    assert '"entryIndex"' in html
    assert "function renderEntryFacts(" in html
    assert "Decodes as" in html
    assert "Pointed to by" in html


def test_the_page_does_no_decoding_of_its_own() -> None:
    """A guard, not a formality: a spelled pitch computed in JavaScript would be
    a second decoder, and the two would drift."""
    html = render_html(_inspection())
    for forbidden in ("harmLev +", "decodeKey(", "spellNote("):
        assert forbidden not in html
```

- [ ] **Step 2: Run to see it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_html.py -x -q -k entry_facts`
Expected: FAIL — `renderEntryFacts` not in the page

- [ ] **Step 3: Add the renderer to `_SCRIPT`**

```javascript
// Entry facts: what points at this entry, and what it decodes to. Rendered
// from `data.entryIndex` and nothing else -- this function does no decoding
// and no joining, which is why the index is built in Python.
function renderEntryFacts(right, entnum) {
  const facts = (data.entryIndex || {})[entnum];
  if (!facts) { return; }

  if (facts.decode) {
    const head = document.createElement('h4');
    head.textContent = 'Decodes as';
    right.appendChild(head);
    const box = document.createElement('div');
    const d = facts.decode;
    const dur = document.createElement('div');
    dur.className = 'leaf';
    dur.textContent = 'dura ' + d.duration_edu + '  ->  ' +
                      d.duration_name.toLowerCase() + (d.is_rest ? '  (rest)' : '');
    box.appendChild(dur);
    (d.notes || []).forEach((n, i) => {
      const line = document.createElement('div');
      line.className = 'leaf';
      const raw = 'note ' + (i + 1) + '   harmLev ' + n.harm_lev + '  harmAlt ' + n.harm_alt;
      line.textContent = raw + '  ->  ' + (n.spelled || ('— ' + (n.why_not || 'unknown')));
      box.appendChild(line);
    });
    right.appendChild(box);
  }

  const refs = (facts.placements || []).length + (facts.named_by || []).length;
  if (refs || (facts.unresolved || []).length) {
    const head = document.createElement('h4');
    head.textContent = 'Pointed to by';
    right.appendChild(head);
    const box = document.createElement('div');
    for (const p of facts.placements || []) {
      const line = document.createElement('div');
      line.className = 'leaf';
      line.textContent = 'placed by   gfhold ' + (p.gfhold_key || '?') +
                         '  staff ' + p.staff + ', measure ' + p.measure +
                         ', layer ' + p.layer + '   frameSpec ' + p.frame;
      box.appendChild(line);
    }
    for (const r of facts.named_by || []) {
      const line = document.createElement('div');
      line.className = 'leaf rec';
      line.textContent = 'named by    ' + r.pool + ' / ' + r.tag + ' ' + r.key;
      line.addEventListener('click', () => selectRecord(r.pool, r.tag, r.key));
      box.appendChild(line);
    }
    for (const why of facts.unresolved || []) {
      const line = document.createElement('div');
      line.className = 'leaf stopped';
      line.textContent = 'unresolved  ' + why;
      box.appendChild(line);
    }
    right.appendChild(box);
  }
}
```

- [ ] **Step 4: Call it from `showRecord`**

At the end of `showRecord`, after the fields are appended:

```javascript
  if (rec.entnum) { renderEntryFacts(right, rec.entnum); }
```

- [ ] **Step 5: Write `selectRecord`**

`showRecord` is reached today by clicking a row in the tree. Making a reference
clickable needs a function that finds that row and clicks it. Read how the tree
rows are built in `renderRecords` and write `selectRecord(pool, tag, key)` to
find the matching `.rec` element and dispatch a click on it, so selection stays
in one place rather than being reimplemented. If no row matches — the reference
names a record in a pool the tree did not render — do nothing.

- [ ] **Step 6: Run the tests and the gate**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_html.py -x -q`
Then: `UV_OFFLINE=1 make check`

- [ ] **Step 7: Verify in a browser, against a real file**

```bash
UV_OFFLINE=1 uv run finale-parser inspect "$(find -L corpus -name '2_Aura Lee.mus' | head -1)" \
  --report /tmp/entry-facts-check.html --force
```

Open it, go to Records, expand `entries`, click an entry. Confirm both blocks
appear and that a `named by` row selects the record it names. **Use a fresh
`?v=N` query string if serving over `http.server`** — it answers
`If-Modified-Since`, and a cached page has cost this project a wrong diagnosis
more than once.

- [ ] **Step 8: Commit**

```bash
git add src/finale_file_parser/report/html.py tests/report/test_html.py
git commit -m "feat: show entry facts in the record pane"
```

---
### Task 7: Prove the two walkers agree

**Files:**
- Create: `tests/report/test_entry_facts_corpus_sweep.py`
- Test: itself

**Interfaces:**
- Consumes: `build_entry_index`, `placements_by_entry` from Tasks 2 and 4; `locate_entries`, `build_score`.
- Produces: nothing. This is the containment for the duplication the design accepted.

- [ ] **Step 1: Write the sweep**

```python
"""The report re-walks a join `locate_entries` already walks. This is what
stops the two drifting.

The duplication is deliberate -- `locate_entries` raises on exactly the
documents a diagnostic report exists for, so the report needs a walk that does
not. What it must not do is disagree about a document they can both read.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.report.entry_facts import build_entry_index, placements_by_entry

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


def test_the_report_walk_agrees_with_locate_entries() -> None:
    """Same entries, same (staff, measure, layer), same count -- wherever
    `locate_entries` accepts the document at all."""
    compared = 0
    for path in corpus_paths(".musx")[:60]:
        try:
            document = parse_enigma(score_xml(path))
            expected = locate_entries(document)
        except Exception:  # noqa: BLE001 -- no oracle for a document it refuses
            continue
        placements, _ = placements_by_entry(document)
        theirs = {
            entnum: sorted((p.staff, p.measure, p.layer) for p in places)
            for entnum, places in expected.items()
        }
        ours = {
            entnum: sorted((p.staff, p.measure, p.layer) for p in places)
            for entnum, places in placements.items()
        }
        assert ours == theirs, "the report's walk disagrees with locate_entries"
        compared += 1
    assert compared >= 40, f"only {compared} documents compared; the sweep is not exercising much"


def test_the_index_never_raises_anywhere_in_the_corpus() -> None:
    """Including the documents `locate_entries` refuses, which is the whole
    reason the report has its own walk."""
    built = refused_by_locate = 0
    for path in corpus_paths(".musx")[:60]:
        try:
            document = parse_enigma(score_xml(path))
        except Exception:  # noqa: BLE001 -- container failures are other sweeps' business
            continue
        try:
            locate_entries(document)
        except Exception:  # noqa: BLE001
            refused_by_locate += 1
        build_entry_index(document)   # must not raise, for either kind
        built += 1
    assert built >= 40
```

- [ ] **Step 2: Run it**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts_corpus_sweep.py -q`
Expected: PASS.

**If the agreement test fails**, the report's `range(start, end + 1)` walk
disagrees with `locate_entries`' `next`-chain walk. `locate_entries` is
correct — it is pinned by the mirror evidence and four other sweeps. Change
`placements_by_entry` to follow the chain, and do **not** relax the sweep.

- [ ] **Step 3: Measure what it costs**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/report/test_entry_facts_corpus_sweep.py -q --durations=5`

Record the number in the commit message. The corpus sweeps already run about
ten minutes in total and the suite cannot finish faster than its slowest single
test, so a sweep that lands badly should be cut to fewer documents rather than
left to grow the gate.

- [ ] **Step 4: Add the IR agreement test**

In the same file:

```python
def test_a_spelled_pitch_matches_the_ir() -> None:
    """The report must not develop its own opinion of a pitch. Same document,
    same entry: what the pane shows and what the score holds are one answer."""
    from finale_file_parser.enigma.to_ir import build_score

    checked = 0
    for path in corpus_paths(".musx")[:20]:
        try:
            document = parse_enigma(score_xml(path))
            score = build_score(document)
        except Exception:  # noqa: BLE001
            continue
        index = build_entry_index(document)
        for part in score.parts:
            for measure in part.measures:
                for voice in measure.voices:
                    for event in voice.events:
                        facts = index.get(str(event.entnum))
                        if facts is None or facts.decode is None:
                            continue
                        for note, pitch in zip(facts.decode.notes, event.pitches, strict=False):
                            if note.spelled is None:
                                continue
                            assert note.spelled == f"{pitch.step}{_written(pitch)}{pitch.octave}"
                            checked += 1
    assert checked >= 100, f"only {checked} pitches compared"
```

**`Event` may not carry `entnum`, and `Pitch`'s alteration spelling may differ.**
Check both before writing this:
`UV_OFFLINE=1 uv run python -c "from finale_file_parser.ir import Event, Pitch; print(Event.__dataclass_fields__.keys(), Pitch.__dataclass_fields__.keys())"`.
If `Event` has no entry number, this comparison cannot be made through the IR —
in that case drop this test and say so in the commit message rather than
inventing a join. The spec asks for agreement with the IR; if the IR does not
carry the identity needed to make it, that is a finding to report, not to work
around.

- [ ] **Step 5: Run the whole gate**

Run: `UV_OFFLINE=1 make check-full`
Expected: all checks passed. Record the total in the commit message.

- [ ] **Step 6: Commit**

```bash
git add tests/report/test_entry_facts_corpus_sweep.py
git commit -m "test: pin the report's entry walk against locate_entries"
```

---

### Task 8: Documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Add a paragraph under the report section**

State three things: that the report re-walks the gfhold -> frameSpec join
rather than calling `locate_entries`; that it does so because `locate_entries`
raises on the documents the report exists for; and that
`tests/report/test_entry_facts_corpus_sweep.py` is what keeps the two from
drifting. Anyone who finds the duplication should find its reason in the same
breath.

- [ ] **Step 2: Run the gate and commit**

```bash
UV_OFFLINE=1 make check
git add docs/ARCHITECTURE.md
git commit -m "docs: record why the report walks the entry join twice"
```

---

## Notes for whoever executes this

**The one thing that would make this wrong.** Every task after Task 2 assumes
the report's walk agrees with `locate_entries`. Task 7 is where that is
checked, and it is deliberately last so the agreement is measured against
finished code. If it fails, the fix is in `placements_by_entry` — never in the
sweep.

**Where the corpus is.** `corpus/` is gitignored and exists only in the main
checkout. If working in a worktree, symlink it (`ln -s /path/to/repo/corpus
corpus`) and note that `find` needs `-L` to follow it. Never `git add -A` — the
symlink is untracked and not ignored.

**Branch.** Work off current `main`. The design lives on `docs/entry-facts-design`;
merging that branch is not a prerequisite for the code, only for the document.
