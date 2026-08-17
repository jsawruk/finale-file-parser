# Percussion Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed, placement-aware Enigma resolver for percussion note assignments without changing the IR or any output.

**Architecture:** A focused `enigma/percussion.py` module owns the complete `percussionNoteCode -> entry placement -> playbackRoute -> percussionNoteInfo` join. It returns tuples parallel to each placed entry's notes, preserves selected-but-undefined codes explicitly, and decodes only palette rows that score placements actually use.

**Tech Stack:** Python 3.12, frozen dataclasses, the existing `EnigmaDocument`/`locate_entries`/`read_entry` APIs, pytest, Ruff, mypy strict, and Make targets through uv.

**Spec:** `docs/superpowers/specs/2026-08-17-percussion-resolver-design.md`

## Global Constraints

- This PR changes no `Score`, IR, MusicXML, CLI, report, or conversion output.
- Export `PercussionAppearance`, `PercussionNote`, `MalformedPercussionError`, and `percussion_notes` from `finale_file_parser.enigma` only; do not add them to `finale_file_parser.__init__`.
- Support parsed `.musx` records only. Do not translate DCL `^DF`/`^DN` or later-era `.mus` records.
- Treat `percussionNoteInfo` as a palette. Decode a definition's six fields only after a placed staff selects its map and a note selects its code.
- Preserve a valid assignment whose selected map lacks its code as `PercussionNote(appearance=None)`; never consult another map.
- Every parser input is hostile: all file-supplied integers and tuple positions are checked before indexing or allocating.
- Corpus tests report aggregate counts only—never paths, filenames, titles, text, or individual note values.
- Use only Make targets: targeted units with `make test`, the targeted sweep with `make test-sweeps`, and `make check-full` before pushing.
- Conventional Commits; one commit per task.

---

### Task 1: Typed placement-aware resolver

**Files:**
- Create: `src/finale_file_parser/enigma/percussion.py`
- Create: `tests/enigma/test_percussion.py`
- Modify: `src/finale_file_parser/enigma/__init__.py`

**Interfaces:**
- Consumes: `EnigmaDocument`, `Record`, and `field_int` from `enigma.document`; `locate_entries(document)`; `read_entry(record)`.
- Produces: `PercussionAppearance`, `PercussionNote`, `MalformedPercussionError`, and `percussion_notes(document) -> dict[tuple[int, int], tuple[PercussionNote | None, ...]]`.

- [ ] **Step 1: Write the synthetic document builder and failing happy-path tests**

Create `tests/enigma/test_percussion.py`. Construct the document model directly so the test isolates resolution rather than XML parsing:

```python
from __future__ import annotations

from finale_file_parser.enigma import (
    PercussionAppearance,
    PercussionNote,
    percussion_notes,
)
from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
)

EMPTY: tuple[Record, ...] = ()


def _note(harm_lev: int) -> Record:
    return Record(
        tag="note",
        attrs={"id": "1"},
        text="",
        fields={"harmLev": str(harm_lev), "harmAlt": "0"},
    )


def _appearance_fields(harm_lev: str = "9") -> dict[str, str]:
    return {
        "harmLev": harm_lev,
        "percNoteType": "38",
        "dwholeNotehead": "250",
        "wholeNotehead": "119",
        "halfNotehead": "250",
        "closedNotehead": "207",
    }


def _document(
    *,
    routes: dict[int, str | None],
    definitions: dict[tuple[str, str], dict[str, str]],
    assignments: tuple[tuple[str, str, str], ...],
) -> EnigmaDocument:
    notes = (_note(0), _note(1))
    entry = Record(
        tag="entry",
        attrs={"entnum": "1", "prev": "0", "next": "0"},
        text="",
        fields={"numNotes": "2", "dura": "1024", "note": notes},
    )
    others: list[Record] = [
        Record(
            tag="measSpec",
            attrs={"cmper": "1"},
            text="",
            fields={
                "keySig": Record(tag="keySig", attrs={}, text="", fields={"key": "0"})
            },
        )
    ]
    details: list[Record] = []
    for staff, map_id in routes.items():
        frame = staff * 10
        others.extend(
            (
                Record(
                    tag="staffSpec",
                    attrs={"cmper": str(staff)},
                    text="",
                    fields={},
                ),
                Record(
                    tag="frameSpec",
                    attrs={"cmper": str(frame), "inci": "0"},
                    text="",
                    fields={"startEntry": "1", "endEntry": "1"},
                ),
                Record(
                    tag="playbackRoute",
                    attrs={"cmper": str(staff)},
                    text="",
                    fields={} if map_id is None else {"percMapRefID": map_id},
                ),
            )
        )
        details.append(
            Record(
                tag="gfhold",
                attrs={"cmper1": str(staff), "cmper2": "1"},
                text="",
                fields={"frame1": str(frame)},
            )
        )
    others.extend(
        Record(
            tag="percussionNoteInfo",
            attrs={"cmper": map_id, "inci": note_code},
            text="",
            fields=fields,
        )
        for (map_id, note_code), fields in definitions.items()
    )
    details.extend(
        Record(
            tag="percussionNoteCode",
            attrs={"entnum": "1", "inci": inci},
            text="",
            fields={"noteID": note_id, "noteCode": note_code},
        )
        for inci, note_id, note_code in assignments
    )
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=tuple(others)),
        details=DetailsPool(records=tuple(details)),
        entries=EntriesPool(records=(entry,)),
        texts=TextsPool(records=EMPTY),
    )


def test_resolves_the_selected_map_row_in_entry_note_order() -> None:
    document = _document(
        routes={1: "7"},
        definitions={("7", "42"): _appearance_fields()},
        assignments=(("1", "2", "42"),),
    )
    appearance = PercussionAppearance(
        harm_lev=9,
        percussion_type=38,
        double_whole_notehead=250,
        whole_notehead=119,
        half_notehead=250,
        closed_notehead=207,
    )
    assert percussion_notes(document) == {
        (1, 1): (None, PercussionNote(map_id=7, note_code=42, appearance=appearance))
    }


def test_a_mirror_resolves_against_each_staffs_own_map() -> None:
    document = _document(
        routes={1: "7", 2: "8"},
        definitions={
            ("7", "42"): _appearance_fields("9"),
            ("8", "42"): _appearance_fields("12"),
        },
        assignments=(("0", "1", "42"),),
    )
    found = percussion_notes(document)
    first = found[(1, 1)][0]
    second = found[(1, 2)][0]
    assert first is not None and first.appearance is not None
    assert second is not None and second.appearance is not None
    assert first.appearance.harm_lev == 9
    assert second.appearance.harm_lev == 12


def test_an_ordinary_staff_does_not_turn_a_stale_code_into_percussion() -> None:
    document = _document(
        routes={1: None},
        definitions={("7", "42"): _appearance_fields()},
        assignments=(("0", "1", "42"),),
    )
    assert percussion_notes(document) == {}


def test_a_code_absent_from_the_selected_map_remains_explicitly_unresolved() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "13"),),
    )
    assert percussion_notes(document) == {
        (1, 1): (PercussionNote(map_id=7, note_code=13, appearance=None), None)
    }
```

- [ ] **Step 2: Run the focused test and verify red**

Run:

```bash
UV_OFFLINE=1 make test JOBS=0 PYTEST_ARGS='tests/enigma/test_percussion.py -q'
```

Expected: collection fails because `finale_file_parser.enigma.percussion` does not exist.

- [ ] **Step 3: Implement the typed resolver**

Create `src/finale_file_parser/enigma/percussion.py` with the public types and a single public function. Keep palette rows as raw `Record`s until a selected map/code pair asks for one:

```python
"""Resolve Finale percussion assignments onto placed entry notes."""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument, Record, field_int
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.music import read_entry
from finale_file_parser.errors import FinaleFileError

__all__ = [
    "MalformedPercussionError",
    "PercussionAppearance",
    "PercussionNote",
    "percussion_notes",
]

_ASSIGNMENT = "percussionNoteCode"
_DEFINITION = "percussionNoteInfo"
_ROUTE = "playbackRoute"


class MalformedPercussionError(FinaleFileError):
    """Percussion records do not form a consistent placed-note mapping."""


@dataclass(frozen=True)
class PercussionAppearance:
    harm_lev: int
    percussion_type: int
    double_whole_notehead: int
    whole_notehead: int
    half_notehead: int
    closed_notehead: int


@dataclass(frozen=True)
class PercussionNote:
    map_id: int
    note_code: int
    appearance: PercussionAppearance | None


def percussion_notes(
    document: EnigmaDocument,
) -> dict[tuple[int, int], tuple[PercussionNote | None, ...]]:
    assignments, note_counts = _assignments(document)
    if not assignments:
        return {}
    placements = locate_entries(document)
    routes = _routes(document)
    definitions = _definitions(document)
    out: dict[tuple[int, int], tuple[PercussionNote | None, ...]] = {}
    for entnum, by_index in assignments.items():
        for placement in placements.get(entnum, ()):
            map_id = routes.get(placement.staff)
            if map_id is None:
                continue
            notes: list[PercussionNote | None] = [None] * note_counts[entnum]
            for note_index, note_code in by_index.items():
                record = definitions.get((map_id, note_code))
                notes[note_index] = PercussionNote(
                    map_id=map_id,
                    note_code=note_code,
                    appearance=None if record is None else _appearance(record),
                )
            value = tuple(notes)
            previous = out.setdefault((entnum, placement.staff), value)
            if previous != value:
                raise MalformedPercussionError(
                    f"entry {entnum} resolves differently twice on staff {placement.staff}"
                )
    return out


def _assignments(document: EnigmaDocument) -> tuple[dict[int, dict[int, int]], dict[int, int]]:
    out: dict[int, dict[int, int]] = {}
    note_counts: dict[int, int] = {}
    for record in document.details.of_tag(_ASSIGNMENT):
        if "part" in record.attrs:
            continue
        entnum = field_int(record.attrs.get("entnum"))
        note_id = field_int(record.fields.get("noteID"))
        note_code = field_int(record.fields.get("noteCode"))
        if entnum is None or note_id is None or note_code is None:
            continue
        entry_record = document.entries.get(entnum)
        if entry_record is None:
            continue
        note_counts.setdefault(entnum, len(read_entry(entry_record).notes))
        out.setdefault(entnum, {})[note_id - 1] = note_code
    return out, note_counts


def _routes(document: EnigmaDocument) -> dict[int, int]:
    out: dict[int, int] = {}
    for record in document.others.of_tag(_ROUTE):
        if "part" in record.attrs:
            continue
        staff = field_int(record.attrs.get("cmper"))
        map_id = field_int(record.fields.get("percMapRefID"))
        if staff is not None and map_id is not None:
            out[staff] = map_id
    return out


def _definitions(document: EnigmaDocument) -> dict[tuple[int, int], Record]:
    out: dict[tuple[int, int], Record] = {}
    for record in document.others.of_tag(_DEFINITION):
        if "part" in record.attrs:
            continue
        map_id = field_int(record.attrs.get("cmper"))
        note_code = field_int(record.attrs.get("inci", "0"))
        if map_id is not None and note_code is not None:
            out[(map_id, note_code)] = record
    return out


def _appearance(record: Record) -> PercussionAppearance:
    harm_lev = field_int(record.fields.get("harmLev"))
    percussion_type = field_int(record.fields.get("percNoteType"))
    double_whole = field_int(record.fields.get("dwholeNotehead"))
    whole = field_int(record.fields.get("wholeNotehead"))
    half = field_int(record.fields.get("halfNotehead"))
    closed = field_int(record.fields.get("closedNotehead"))
    if harm_lev is None:
        raise MalformedPercussionError("harmLev is not an integer")
    if percussion_type is None:
        raise MalformedPercussionError("percNoteType is not an integer")
    if double_whole is None:
        raise MalformedPercussionError("dwholeNotehead is not an integer")
    if whole is None:
        raise MalformedPercussionError("wholeNotehead is not an integer")
    if half is None:
        raise MalformedPercussionError("halfNotehead is not an integer")
    if closed is None:
        raise MalformedPercussionError("closedNotehead is not an integer")
    return PercussionAppearance(
        harm_lev=harm_lev,
        percussion_type=percussion_type,
        double_whole_notehead=double_whole,
        whole_notehead=whole,
        half_notehead=half,
        closed_notehead=closed,
    )
```

Add imports and `__all__` entries for all four public names in `src/finale_file_parser/enigma/__init__.py`. Do not edit the package-root `src/finale_file_parser/__init__.py`.

- [ ] **Step 4: Run formatting and the focused test**

Run:

```bash
UV_OFFLINE=1 make fmt
UV_OFFLINE=1 make test JOBS=0 PYTEST_ARGS='tests/enigma/test_percussion.py -q'
```

Expected: four tests pass.

- [ ] **Step 5: Run the normal gate**

Run:

```bash
UV_OFFLINE=1 make check
```

Expected: Ruff, formatting, mypy strict, and all non-corpus tests pass without a type ignore.

- [ ] **Step 6: Commit the typed resolver**

```bash
git add src/finale_file_parser/enigma/percussion.py src/finale_file_parser/enigma/__init__.py tests/enigma/test_percussion.py
git commit -m "feat: resolve percussion note appearances"
```

---

### Task 2: Strict percussion validation

**Files:**
- Modify: `src/finale_file_parser/enigma/percussion.py`
- Modify: `tests/enigma/test_percussion.py`

**Interfaces:**
- Consumes: Task 1's public types and `percussion_notes` function.
- Produces: deterministic `MalformedPercussionError` failures for malformed assignment identities, route identities, note positions, and selected definition fields.

- [ ] **Step 1: Add failing malformed-input tests**

Extend the synthetic builder's `assignments` values as raw strings, then add these tests:

```python
import pytest

from finale_file_parser.enigma.percussion import MalformedPercussionError


def test_rejects_a_non_integer_note_code() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "not-an-integer"),),
    )
    with pytest.raises(MalformedPercussionError, match="noteCode is not an integer"):
        percussion_notes(document)


def test_rejects_inci_that_is_not_zero_based_note_id() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("1", "1", "42"),),
    )
    with pytest.raises(MalformedPercussionError, match="inci=1 disagrees with noteID=1"):
        percussion_notes(document)


def test_rejects_a_note_id_outside_the_entry() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("2", "3", "42"),),
    )
    with pytest.raises(MalformedPercussionError, match="noteID=3 outside entry 1"):
        percussion_notes(document)


def test_rejects_two_assignments_for_one_entry_note() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "42"), ("1", "1", "43")),
    )
    with pytest.raises(MalformedPercussionError, match="duplicate percussion assignment"):
        percussion_notes(document)


def test_rejects_an_incomplete_selected_definition() -> None:
    fields = _appearance_fields()
    del fields["harmLev"]
    document = _document(
        routes={1: "7"},
        definitions={("7", "42"): fields},
        assignments=(("0", "1", "42"),),
    )
    with pytest.raises(MalformedPercussionError, match="harmLev is not an integer"):
        percussion_notes(document)
```

- [ ] **Step 2: Run the validation tests and verify red**

Run:

```bash
UV_OFFLINE=1 make test JOBS=0 PYTEST_ARGS='tests/enigma/test_percussion.py -q'
```

Expected: the new tests fail because Task 1 skips malformed identities, overwrites duplicates, and does not validate `inci`.

- [ ] **Step 3: Add one required-integer boundary and enforce identities before indexing**

Add this helper and use it for assignment `entnum`, `inci`, `noteID`, and `noteCode`; route `cmper` and `percMapRefID` when present; definition `cmper`/`inci`; and the six selected appearance fields:

```python
def _required_int(value: object, name: str) -> int:
    parsed = field_int(value)
    if parsed is None:
        raise MalformedPercussionError(f"{name} is not an integer: {value!r}")
    return parsed
```

Replace `_assignments` with validation in this order so duplicate assignments have a stable error even when their second `inci` is also inconsistent:

```python
def _assignments(document: EnigmaDocument) -> tuple[dict[int, dict[int, int]], dict[int, int]]:
    out: dict[int, dict[int, int]] = {}
    note_counts: dict[int, int] = {}
    seen: set[tuple[int, int]] = set()
    for record in document.details.of_tag(_ASSIGNMENT):
        if "part" in record.attrs:
            continue
        entnum = _required_int(record.attrs.get("entnum"), "entnum")
        inci = _required_int(record.attrs.get("inci", "0"), "inci")
        note_id = _required_int(record.fields.get("noteID"), "noteID")
        note_code = _required_int(record.fields.get("noteCode"), "noteCode")
        identity = (entnum, note_id)
        if identity in seen:
            raise MalformedPercussionError(
                f"duplicate percussion assignment for entry {entnum} noteID {note_id}"
            )
        seen.add(identity)
        if inci != note_id - 1:
            raise MalformedPercussionError(
                f"percussion assignment inci={inci} disagrees with noteID={note_id}"
            )
        entry_record = document.entries.get(entnum)
        if entry_record is None:
            raise MalformedPercussionError(f"percussion assignment names missing entry {entnum}")
        note_count = len(read_entry(entry_record).notes)
        if not 1 <= note_id <= note_count:
            raise MalformedPercussionError(
                f"noteID={note_id} outside entry {entnum} with {note_count} note(s)"
            )
        note_counts[entnum] = note_count
        out.setdefault(entnum, {})[note_id - 1] = note_code
    return out, note_counts
```

In `_routes`, reject two score routes for the same staff after parsing their integer identities. Omit a route only when `percMapRefID` is absent; a present non-integer value raises. In `_definitions`, reject duplicate parsed `(map_id, note_code)` identities. In `_appearance`, call `_required_int` separately for every field so the error names the field and no type ignore is needed.

- [ ] **Step 4: Run the focused test and normal gate**

Run:

```bash
UV_OFFLINE=1 make fmt
UV_OFFLINE=1 make test JOBS=0 PYTEST_ARGS='tests/enigma/test_percussion.py -q'
UV_OFFLINE=1 make check
```

Expected: all percussion tests and the normal gate pass.

- [ ] **Step 5: Commit validation**

```bash
git add src/finale_file_parser/enigma/percussion.py tests/enigma/test_percussion.py
git commit -m "feat: validate percussion note mappings"
```

---

### Task 3: Corpus evidence and current-state documentation

**Files:**
- Create: `tests/enigma/test_percussion_corpus_sweep.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: Task 2's strict `percussion_notes(document)` API.
- Produces: aggregate regression pins for the complete corpus and tracked documentation of what is decoded versus deliberately deferred.

- [ ] **Step 1: Add the aggregate corpus sweep**

Create `tests/enigma/test_percussion_corpus_sweep.py`:

```python
"""Pin percussion usage without mistaking Finale's palette for score content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from corpus_files import corpus_paths

from finale_file_parser.enigma.document import field_int, parse_enigma
from finale_file_parser.enigma.percussion import percussion_notes
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"
pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


@dataclass
class Reading:
    archives: int = 0
    palette_rows: int = 0
    documents: int = 0
    assignments: int = 0
    unique_assignments: int = 0
    zero_based_identities: int = 0
    used: int = 0
    resolved: int = 0
    unresolved: int = 0


@pytest.fixture(scope="module")
def reading() -> Reading:
    out = Reading()
    for path in corpus_paths(".musx"):
        document = parse_enigma(score_xml(path))
        out.archives += 1
        out.palette_rows += len(document.others.of_tag("percussionNoteInfo"))
        assignments = document.details.of_tag("percussionNoteCode")
        if not assignments:
            continue
        out.documents += 1
        out.assignments += len(assignments)
        identities: set[tuple[int, int]] = set()
        for record in assignments:
            entnum = field_int(record.attrs.get("entnum"))
            inci = field_int(record.attrs.get("inci", "0"))
            note_id = field_int(record.fields.get("noteID"))
            assert entnum is not None and inci is not None and note_id is not None
            identities.add((entnum, note_id))
            out.zero_based_identities += int(inci == note_id - 1)
        out.unique_assignments += len(identities)
        for notes in percussion_notes(document).values():
            for note in notes:
                if note is None:
                    continue
                out.used += 1
                if note.appearance is None:
                    out.unresolved += 1
                else:
                    out.resolved += 1
    return out


def test_the_palette_is_not_mistaken_for_score_usage(reading: Reading) -> None:
    assert reading.archives == 401
    assert reading.palette_rows == 149_533
    assert reading.documents == 10
    assert reading.assignments == 4_692


def test_every_assignment_identity_is_unique_and_zero_based(reading: Reading) -> None:
    assert reading.unique_assignments == 4_692
    assert reading.zero_based_identities == 4_692


def test_only_selected_staff_maps_produce_percussion_notes(reading: Reading) -> None:
    assert reading.used == 605
    assert reading.resolved == 597
    assert reading.unresolved == 8
```

- [ ] **Step 2: Run the targeted sweep**

Run:

```bash
UV_OFFLINE=1 make test-sweeps JOBS=0 PYTEST_ARGS='tests/enigma/test_percussion_corpus_sweep.py -q'
```

Expected: three tests pass. A resolver exception is itself the zero-incomplete-used-definitions assertion.

- [ ] **Step 3: Document the confirmed linkage and scope**

In `docs/ARCHITECTURE.md`, add a “Known format facts — percussion mapping” section beside the other typed Enigma readers. Record:

- `percussionNoteInfo` is a 149,533-row palette present in all 401 archives;
- actual use is the five-hop linkage pinned by the resolver;
- `playbackRoute.cmper` is the staff and `percMapRefID` is the selected map;
- `percussionNoteCode.noteID` is one-based while `inci` is exactly zero-based;
- 597 used rows resolve and eight remain explicit unresolved code-13 assignments;
- all resolved `harmLev` values differ from the currently interpreted pitch;
- notehead meaning, MIDI/drum naming, IR consumption, output, and `.mus` translation remain deferred.

In `docs/ROADMAP.md`, add a checked item for the typed `.musx` percussion resolver and an unchecked follow-up for unpitched IR/MusicXML consumption. State the measured 605 used placements rather than the universal palette count as feature usage. Do not change README support claims.

- [ ] **Step 4: Run documentation and normal checks**

Run:

```bash
git diff --check
UV_OFFLINE=1 make check
```

Expected: no whitespace errors; Ruff, formatting, mypy strict, and all non-corpus tests pass.

- [ ] **Step 5: Commit corpus evidence and documentation**

```bash
git add tests/enigma/test_percussion_corpus_sweep.py docs/ARCHITECTURE.md docs/ROADMAP.md
git commit -m "docs: record percussion mapping evidence"
```

---

### Task 4: Full verification and handoff

**Files:**
- Modify only if a verification failure identifies a defect in a file already owned by Tasks 1–3.

**Interfaces:**
- Consumes: the complete resolver, validation, corpus sweep, and documentation.
- Produces: a branch proven ready for review, with no output-layer changes.

- [ ] **Step 1: Verify the intended scope**

Run:

```bash
git diff --stat e5d8949addf2a03e17ccc320eafb119f317af762..HEAD
git diff --name-only e5d8949addf2a03e17ccc320eafb119f317af762..HEAD
```

Expected changed implementation files are only the percussion module/export, its unit and corpus tests, architecture/roadmap documentation, and the approved design/plan documents. `ir.py`, `enigma/to_ir.py`, `export/musicxml.py`, CLI, and report files must be absent.

- [ ] **Step 2: Run the complete required gate**

Ensure the local corpus is available in this worktree, then run:

```bash
UV_OFFLINE=1 make check-full
```

Expected: Ruff, format check, mypy strict, all unit tests, and all corpus sweeps pass. Record the exact passed/skipped counts in `.remember/now.md`; do not commit that local handoff file.

- [ ] **Step 3: Verify clean state and commit history**

Run:

```bash
git status --short
git log --oneline e5d8949addf2a03e17ccc320eafb119f317af762..HEAD
```

Expected: clean worktree and conventional commits for the design/plan, resolver, validation, and evidence/docs.

- [ ] **Step 4: Wait for PR #119 before publishing**

Confirm PR #119 is merged, fetch `origin/main`, and verify `e5d8949` is an ancestor of the updated main branch before pushing `codex/percussion-resolver`. If #119 remains open, keep this branch local rather than opening a stacked PR.
