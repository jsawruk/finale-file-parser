# Mirrored Entries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one entry sound in more than one place, so a document containing a Finale *mirror* reads instead of being rejected.

**Architecture:** `locate_entries` stops mapping an entry to a single `EntryLocation` and returns a tuple of every place the file puts it. `build_score` loops over that tuple instead of taking one location. The two placements are peers — nothing infers which staff is the copy, because the file marks neither.

**Tech Stack:** Python ≥3.12, `uv`, `ruff`, `mypy --strict`, `pytest`.

**Design spec:** `docs/superpowers/specs/2026-08-10-mirrored-entries-design.md` — read it before Task 1.

## Global Constraints

- `locate_entries` returns `dict[int, tuple[EntryLocation, ...]]`. `EntryLocation` itself is **unchanged** — no `is_mirror` field; mirroring is a property of the mapping.
- **Never infer which staff is the source and which is the mirror.** The file marks neither. Any code or comment implying a direction is a defect.
- The double-place check **narrows, it does not disappear**: several distinct locations are legal, the same `(staff, measure, layer)` twice is still `MalformedScoreError`.
- Corpus pins are **measured, never predicted**. Where this plan states an expected number, it is a value to confirm — if the measurement differs, stop and investigate rather than writing down whatever came out.
- A count that *drops* means semantics changed, not coverage. Do not bump a pin downward without explaining why in its docstring.
- **Every new test gets a mutation check**: delete or invert the thing it guards, confirm the test fails, restore. A test that passes against unfixed code is not evidence. Restore by editing the file back, never `git checkout <file>`.
- This breaks a published API (`locate_entries` is in `finale_file_parser.__all__`, shipped in 0.2.0), so the version becomes **0.3.0**.
- `mypy --strict` covers `src`, `tests` **and** `scripts` (`CODE = src tests scripts`). Test helpers need full annotations too — an unannotated `def` or an `object`-typed parameter whose attributes you then access will fail the gate.
- Run the gate with `make check > /tmp/gate.log 2>&1; ec=$?` and test `$ec` on its own line. **Never pipe `make check` into `tail`** — the pipe makes the exit status `tail`'s and a failing gate looks passing.

---

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `src/finale_file_parser/enigma/location.py` | Resolve entries to their place(s). The model change lives here. | 1 |
| `tests/enigma/test_location.py` | Unit tests for placement, synthetic XML only. | 1 |
| `tests/enigma/test_location_corpus_sweep.py` | `.musx` sweep; asserts every entry is located. | 1 |
| `src/finale_file_parser/enigma/to_ir.py` | Build the IR. Consumes the location map. | 2 |
| `tests/enigma/test_mirrors.py` | **New.** Synthetic end-to-end: a mirror reaches both parts. | 2 |
| `tests/enigma/test_tuplet_corpus_sweep.py` | Sums duration per (staff, measure, layer). **Must count every placement.** | 2 |
| `tests/enigma/test_transposition_octave_corpus_sweep.py` | Checks each placement's staff transposition. | 2 |
| `tests/enigma/test_pitch_corpus_sweep.py`, `test_key_corpus_sweep.py`, `test_mus_entries_corpus_sweep.py` | Read a placement's key or staff; one representative suffices. | 2 |
| `tests/enigma/test_mus_dcl_score_corpus_sweep.py` | DCL coverage pins. | 3 |
| `tests/export/test_export_audit_corpus_sweep.py` | Export-level corpus assertions. | 3 |
| `src/finale_file_parser/enigma/mus_document.py` | `UNTRANSLATED` list. | 4 |
| `scripts/format_spec/__main__.py`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, `pyproject.toml` | Documentation and version. | 4 |

---

### Task 1: `locate_entries` returns a location per placement

**Files:**
- Modify: `src/finale_file_parser/enigma/location.py`
- Test: `tests/enigma/test_location.py`
- Test: `tests/enigma/test_location_corpus_sweep.py:34-61`

**Interfaces:**
- Produces: `locate_entries(doc: EnigmaDocument) -> dict[int, tuple[EntryLocation, ...]]`. Every entry that any frame reaches appears as a key; its value holds one `EntryLocation` per placement, in frame-walk order, and is never empty. `EntryLocation` keeps its five fields (`entnum`, `staff`, `measure`, `key_signature`, `layer`) unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/enigma/test_location.py`, after `BASIC`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/enigma/test_location.py -k "mirrored or claimed_twice or unmirrored" -v`

Expected: `test_a_mirrored_entry_holds_one_location_per_staff` FAILS with `MalformedScoreError: entry 1 placed by more than one frame`; `test_an_unmirrored_entry_holds_exactly_one_location` FAILS on comparing an `EntryLocation` to a 1-tuple; `test_the_same_place_claimed_twice_still_raises` FAILS because the message is the old one.

- [ ] **Step 3: Change the signature and the placement loop**

In `src/finale_file_parser/enigma/location.py`:

Change the return annotation of `locate_entries`:

```python
def locate_entries(doc: EnigmaDocument) -> dict[int, tuple[EntryLocation, ...]]:
```

Change the accumulator (it collects while building, and freezes on return):

```python
    location: dict[int, list[EntryLocation]] = {}
```

Change the return statement at the end of `locate_entries`:

```python
    return {entnum: tuple(places) for entnum, places in location.items()}
```

Change the `location` parameter annotation on **both** `_place_frame_entries` and `_walk_entry_chain`:

```python
    location: dict[int, list[EntryLocation]],
```

Replace the double-place check and assignment in `_walk_entry_chain`:

```python
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
```

(Comparing whole `EntryLocation`s is equivalent to comparing the triple: `key_signature` is derived from `measure`, so two placements agreeing on staff/measure/layer necessarily agree on the key.)

- [ ] **Step 4: Update the docstrings that state the old rule**

Module docstring of `location.py` — append after the paragraph about `gfhold` holding four frames:

```
An entry can be placed **more than once**. That is Finale's *mirror*: one staff
displaying another's music, stored as one entry span with two `frameSpec`
records naming it and two `gfhold` records naming those frames. Nothing marks
either placement as the copy, so `locate_entries` returns them as peers, in
frame-walk order. One place claimed twice is still an error -- see
`MalformedScoreError`.
```

`MalformedScoreError`'s docstring — replace `an entry placed by more than one frame` with:

```
an entry placed twice at the same staff, measure and layer (an entry in
several *different* places is a mirror, and is legal),
```

`locate_entries`' own docstring — replace the `Raises:` clause `an entry is placed by more than one frame` with `an entry is placed twice at one (staff, measure, layer)`, and change the summary line to:

```
    """Resolve every entry to the place(s) it sounds, and the effective raw key.
```

- [ ] **Step 5: Update every existing assertion in `test_location.py`**

The rule: `loc[n]` is now a tuple. Comparisons to a bare `EntryLocation` gain a trailing comma; attribute access gains `[0]`. There are ten call sites; work through the file top to bottom. Examples of each shape:

```python
# was: assert loc[1] == EntryLocation(entnum=1, staff=1, measure=1, layer=1, key_signature=2)
assert loc[1] == (EntryLocation(entnum=1, staff=1, measure=1, layer=1, key_signature=2),)

# was: assert loc[3].measure == 2
assert loc[3][0].measure == 2

# was: assert [loc[n].key_signature for n in (1, 2, 3)] == [1, 0, 1]
assert [loc[n][0].key_signature for n in (1, 2, 3)] == [1, 0, 1]

# was: assert locate_entries(parse_enigma(doc))[1].key_signature == 0
assert locate_entries(parse_enigma(doc))[1][0].key_signature == 0

# was: assert loc[1].measure == 1 and loc[2].measure == 1
assert loc[1][0].measure == 1 and loc[2][0].measure == 1
```

Do **not** change what any existing test asserts about keys, layers or errors — only the indexing.

- [ ] **Step 6: Update the `.musx` corpus sweep**

`tests/enigma/test_location_corpus_sweep.py`, in `test_every_corpus_entry_is_located_exactly_once`, replace the per-location loop:

```python
        for places in locations.values():
            # Every .musx entry is located exactly ONCE: 0 of 401 corpus
            # archives carries a shared entry span, so no mirror reaches this
            # container. Measured 2026-08-10 -- this assertion is what would
            # notice if one ever did.
            assert len(places) == 1, path
            for location in places:
                assert isinstance(location.key_signature, int), path
                assert location.staff in staff_cmpers, path
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/enigma/test_location.py tests/enigma/test_location_corpus_sweep.py -v`

Expected: PASS, all of them.

- [ ] **Step 8: Mutation-check the two new guarantees**

1. In `_walk_entry_chain`, delete the `if here in location.get(entnum, ()):` raise. Run `uv run pytest tests/enigma/test_location.py -k claimed_twice`. Expected: **FAILS** (`DID NOT RAISE`). Restore by editing the lines back.
2. Change the return to `{entnum: (places[0],) for entnum, places in location.items()}`. Run `uv run pytest tests/enigma/test_location.py -k mirrored`. Expected: **FAILS** on `len(loc[1]) == 2`. Restore by editing it back.

Confirm `git diff --stat src/finale_file_parser/enigma/location.py` matches what you intended before moving on.

- [ ] **Step 9: Typecheck and commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src
git add src/finale_file_parser/enigma/location.py tests/enigma/test_location.py tests/enigma/test_location_corpus_sweep.py
git commit -m "feat: let an entry hold a location per placement

A Finale mirror is one staff displaying another's music: one entry span,
two frameSpec records naming it, two gfholds naming those frames. Placement
rejected the second claim, so a document Finale wrote on purpose was refused.

locate_entries now returns a tuple of placements per entry. The two are peers
-- nothing infers which staff is the copy, because the file marks neither.
The double-place check narrows rather than disappears: the same (staff,
measure, layer) twice is still malformed."
```

---

### Task 2: `build_score` emits the entry into each location

**Files:**
- Modify: `src/finale_file_parser/enigma/to_ir.py:118-139`
- Test: `tests/enigma/test_mirrors.py` (create)

**Interfaces:**
- Consumes: `locate_entries(doc) -> dict[int, tuple[EntryLocation, ...]]` from Task 1.
- Produces: no signature change. `build_score(document) -> Score` gains the behaviour that a mirrored entry appears in every part that displays it.

- [ ] **Step 1: Write the failing test**

Create `tests/enigma/test_mirrors.py`:

```python
"""A mirror reaches the IR as music on both staves.

Finale's mirror is a *display* device -- one staff shows another's notes rather
than holding a copy. MusicXML has no such concept, so the faithful rendering of
what Finale draws is the notes written onto both staves. That is what this
covers, end to end from XML to Score.
"""

from __future__ import annotations

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Event, Score

NS = "http://www.makemusic.com/2012/finale"

# Two quarter notes, C4 then D4, mirrored onto staff 2. One entry span, two
# frameSpec records naming it, two gfholds naming those frames.
MIRROR = f'''<finale version="18.0" xmlns="{NS}">
    <entries>
      <entry entnum="1" prev="0" next="2">
        <numNotes>1</numNotes><dura>1024</dura><isNote/>
        <note id="1"><harmLev>0</harmLev><harmAlt>0</harmAlt></note>
      </entry>
      <entry entnum="2" prev="1" next="0">
        <numNotes>1</numNotes><dura>1024</dura><isNote/>
        <note id="1"><harmLev>1</harmLev><harmAlt>0</harmAlt></note>
      </entry>
    </entries>
    <others>
      <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>2</endEntry></frameSpec>
      <frameSpec cmper="20" inci="0"><startEntry>1</startEntry><endEntry>2</endEntry></frameSpec>
      <measSpec cmper="1">
        <keySig><key>0</key></keySig><beats>4</beats><divbeat>1024</divbeat>
      </measSpec>
      <staffSpec cmper="1"><x>a</x></staffSpec>
      <staffSpec cmper="2"><x>a</x></staffSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold>
      <gfhold cmper1="2" cmper2="1"><frame1>20</frame1></gfhold>
    </details>
</finale>'''.encode()


def _events(score: Score, part_id: str) -> list[Event]:
    part = next(p for p in score.parts if p.id == part_id)
    return [e for m in part.measures for v in m.voices for e in v.events]


def test_a_mirrored_span_reaches_both_parts() -> None:
    score = build_score(parse_enigma(MIRROR))
    assert [p.id for p in score.parts] == ["P1", "P2"]

    first, second = _events(score, "P1"), _events(score, "P2")
    assert len(first) == 2
    assert [(p.step, p.octave) for e in first for p in e.pitches] == [("C", 4), ("D", 4)]
    assert [(p.step, p.octave) for e in second for p in e.pitches] == [("C", 4), ("D", 4)]
    assert [e.duration for e in first] == [e.duration for e in second]


def test_the_mirror_does_not_double_the_source_staff() -> None:
    """Both staves get the music once, not the source staff twice.

    The failure this guards is a loop that appends every placement into the
    first location's cell, which would leave P1 holding four events and P2
    holding none.
    """
    score = build_score(parse_enigma(MIRROR))
    assert len(_events(score, "P1")) == 2
    assert len(_events(score, "P2")) == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/enigma/test_mirrors.py -v`

Expected: both FAIL with `AttributeError: 'tuple' object has no attribute 'staff'`, raised inside `build_score`. Task 1 already made placement succeed for this document; what has not caught up is the consumer.

- [ ] **Step 3: Loop over the locations**

In `src/finale_file_parser/enigma/to_ir.py`, replace the body of the `for entnum in chain.order:` loop:

```python
    for entnum in chain.order:
        record = records.get(entnum)
        if record is None:
            continue
        # An entry can sound in more than one place -- a mirror. Each placement
        # builds its own event, because the staff decides the transposition and
        # so the spelling: a mirror onto a transposing staff is not the same
        # written note.
        for here in location.get(entnum, ()):
            cell = cells.setdefault(
                (here.staff, here.measure),
                _Cell(events_by_layer=defaultdict(list), key_raw=here.key_signature),
            )
            cell.starts_beam[here.layer].append("beam" in record.fields)
            cell.events_by_layer[here.layer].append(
                _event(
                    record=record,
                    key_raw=here.key_signature,
                    transposition=transpositions.get(here.staff, _NO_TRANSPOSITION),
                    written_edu=chain.written_edu[entnum],
                    sounded_edu=sounded[entnum],
                    lyrics=lyrics.get(entnum, ()),
                    articulations=articulations.get(entnum, ()),
                    fingerings=fingerings.get(entnum, ()),
                )
            )
```

Note the `here is None` guard is gone: an absent entry yields an empty tuple and the loop simply does not run.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/enigma/test_mirrors.py -v`

Expected: PASS. Do **not** run the wider suite yet — the five sweeps in Step 5 still read the old shape and will fail until adapted.

- [ ] **Step 5: Adapt the five corpus sweeps that read a location**

These consume `locate_entries` and stop typechecking under the new signature. **The right change differs per file — do not apply a blanket `[0]`.** Where an entry's placements can disagree, taking the first silently drops half a mirror.

**`tests/enigma/test_tuplet_corpus_sweep.py:83-89` — must count every placement.** It sums each entry's duration into a `(staff, measure, layer)` bucket and checks the bucket fills its time signature. A mirrored staff's measure really does hold that music, so dropping a placement makes that measure look empty and drags `balanced_sounded` down. Replace:

```python
        for entnum, duration in sounded.items():
            for here in location.get(entnum, ()):
                # every placement, not just the first: a mirrored staff's measure
                # genuinely holds this music, and skipping it would read as a
                # measure that fails to fill its time signature
                key = (here.staff, here.measure, here.layer)
                by_measure[key] += duration
                written_by_measure[key] += chain.written_edu[entnum]
```

**`tests/enigma/test_transposition_octave_corpus_sweep.py:83-84` — every placement.** Each placement sits on a real staff whose transposition is worth checking. Change `for entnum, where in location.items():` to iterate the tuple:

```python
        for entnum, places in location.items():
            for where in places:
                interval = transposing.get(where.staff)
```

keeping the existing body and its `continue` guards unchanged beneath.

**`tests/enigma/test_pitch_corpus_sweep.py:69-72` and `tests/enigma/test_key_corpus_sweep.py:67-68` — one representative is correct.** Both read only `key_signature`, which is derived from the measure, and every placement of an entry shares its measure. Take the first, and say why:

```python
            placed = location.get(entnum)
            if not placed:
                continue
            # any placement will do: key comes from the measure, and a mirror's
            # placements all sit in the same measure
            concert_key = decode_key(placed[0].key_signature)
```

**`tests/enigma/test_mus_entries_corpus_sweep.py:153-155` — one representative.** This compares a `.mus` entry against its `.musx` twin; it measures entry *decoding*, and how many staves display an entry does not change what the entry holds. The staff only supplies a transposition shift. Use `places[0].staff` with a comment to that effect.

**Expect some of these sweeps to change what they measure, and handle it carefully.** `locate_entries` used to *raise* on `Bach Concerto.MUS`; whatever these sweeps did with that exception, the document now resolves and its ~5,400 entries may enter their totals for the first time. So a moved number here is not automatically a bug.

The rule: change a pinned constant only if you can say in its docstring *why* it moved, and only if it moved in the direction that explanation predicts. A count that **drops** is the dangerous case — it means the sweep is now measuring less than it did, which is the opposite of what this change should do. If any number drops, or moves for a reason you cannot name, **stop and report it to me rather than writing it down**. Include the old value, the new value, and what you think happened.

- [ ] **Step 6: Mutation-check**

Change `for here in location.get(entnum, ()):` in `to_ir.py` to `for here in location.get(entnum, ())[:1]:`. Run `uv run pytest tests/enigma/test_mirrors.py`. Expected: **FAILS** — `P2` holds no events. Restore by editing it back.

- [ ] **Step 7: Run the suite, typecheck, and commit**

Now the wider suite should be green, and `mypy --strict` should report **zero** errors across `src tests scripts` — Task 1 left `to_ir.py` and these five sweeps failing, and this task closes all of them.

```bash
uv run pytest tests/enigma tests/export -q > /tmp/t2.log 2>&1; ec=$?
echo "pytest exit=$ec"; tail -5 /tmp/t2.log
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src tests scripts
git add -A
git commit -m "feat: build a mirrored span into every staff that displays it

MusicXML has no mirror concept, so the faithful rendering of what Finale
draws is the notes on both staves. Each placement builds its own event
because the staff decides the transposition, and so the spelling.

Adapts the five corpus sweeps that read a placement. Where an entry's
placements can disagree the sweep now visits all of them -- the tuplet sweep
sums duration per staff, measure and layer, and skipping a mirrored staff
would read as a measure that fails to fill its time signature."
```

---

### Task 3: Re-measure the corpus pins

**Files:**
- Modify: `tests/enigma/test_mus_dcl_score_corpus_sweep.py:30-42,71-77,209-241`
- Modify: `tests/export/test_export_audit_corpus_sweep.py`

**Interfaces:**
- Consumes: the behaviour from Tasks 1 and 2. No new production code.

`Bach Concerto.MUS` is the one corpus document a mirror stops from building. With Tasks 1–2 done it builds, so several pins move **upward**. These are the values measured during design on 2026-08-10 — confirm each, and if a measurement differs, stop and find out why before writing it down:

| Pin | From | Expect |
| --- | --- | --- |
| `EXPECTED_SCORES` | 131 | 132 |
| `EXPECTED_MALFORMED` | 2 | 1 |
| `EXPECTED_PARTS` | 410 | 416 (+6) |
| `EXPECTED_MEASURES` | 14107 | 15283 (+1176) |
| `EXPECTED_EVENTS` | 61851 | 67795 (+5944) |
| `EXPECTED_PITCHES` | 68530 | 73962 (+5432) |
| `EXPECTED_DEAD_ENTRIES` | 4946 | unchanged — pruning is independent of whether a score builds. If it moves, explain why before touching it. |

- [ ] **Step 1: Run the sweep and read the real numbers**

```bash
uv run pytest tests/enigma/test_mus_dcl_score_corpus_sweep.py -v > /tmp/sweep.log 2>&1; echo "exit=$?"
grep -E "^E +assert|Expected|assert [0-9]+ ==" /tmp/sweep.log | head -20
```

Expected: failures naming the pins above, with the measured value on the left of each `assert`.

- [ ] **Step 2: Update the pins and their docstrings**

Set each constant to its measured value. Then rewrite the two docstrings that describe the old world.

`EXPECTED_SCORES`:

```python
EXPECTED_SCORES = 132
"""Documents that build. Before this reader, none of the 139 did.

Was 131. The document that joined is `Bach Concerto.MUS`, whose 42 mirrored
spans made it the last DCL failure attributable to the reader rather than to
the file. See `MIRRORED_ENTRIES` below.
"""
```

`EXPECTED_MALFORMED`:

```python
EXPECTED_MALFORMED = 1
"""Documents `build_score` rejects: one `gfhold` placing entries in a measure
that defines no key.

Was 2. The other was an entry two frames both claimed -- a mirror, now read
rather than refused.

Pinned rather than tolerated: this is a known, named gap, and the number should
fall, never rise. See `docs/formats/mus-dcl-container.md`.
"""
```

- [ ] **Step 3: Add the mirror pins**

Replace the `DOCUMENTS_WITH_MIRRORED_FRAMES` docstring's last paragraph (it currently explains the failure) and add two pins beside it:

```python
DOCUMENTS_WITH_MIRRORED_FRAMES = 5
"""Documents where two `frameSpec` records name the same entry span.

That is Finale's **mirror**: one staff displays another's music, so both point
at one passage. `docs/eeppd.txt` warns that "mirrors and voice 2 create
complications", and this was the complication.

In four of the five the duplicate frame is never named by a `gfhold`, so the
mirror never reaches the score. Counted separately from the one that does
because these four would read identically whether mirrors were modelled or not.
"""

DOCUMENTS_WHERE_A_MIRROR_REACHES_THE_SCORE = 1
"""Documents where two `gfhold` records name a shared span, so an entry really
is placed twice. `Bach Concerto.MUS`, staves 4 and 14, 42 measures."""

MIRRORED_ENTRIES = 239
"""Entries across the corpus holding more than one location.

**The pin that keeps mirroring honest.** A reader that quietly went back to one
location per entry would still build 132 scores and still pass every count
above -- the mirrored staff would simply come out empty, and no other number
here would notice. This is what notices. Every one of the 239 holds exactly two
locations; none holds three.
"""
```

- [ ] **Step 4: Write the test for the new pins**

Add to `tests/enigma/test_mus_dcl_score_corpus_sweep.py`:

```python
def test_a_mirror_places_its_entries_on_every_staff_that_shows_them() -> None:
    """See `MIRRORED_ENTRIES`."""
    documents = 0
    mirrored = 0
    for path in _dcl_files():
        try:
            document = read_mus_document(path)
            locations = locate_entries(document)
        except (CorruptScoreError, MalformedScoreError):
            continue
        here = [places for places in locations.values() if len(places) > 1]
        if not here:
            continue
        documents += 1
        mirrored += len(here)
        for places in here:
            # a mirror puts one entry in several places, never one place twice
            assert len({(p.staff, p.measure, p.layer) for p in places}) == len(places), path
            # and always within one measure -- the staves differ, the bar does not
            assert len({p.measure for p in places}) == 1, path

    assert documents == DOCUMENTS_WHERE_A_MIRROR_REACHES_THE_SCORE
    assert mirrored == MIRRORED_ENTRIES
```

Add `locate_entries` to the imports from `finale_file_parser.enigma.location` if it is not already there.

- [ ] **Step 5: Add the export-level assertion**

In `tests/export/test_export_audit_corpus_sweep.py`, add:

```python
MIRRORED_MEASURES = 42
"""Measures of `Bach Concerto.MUS` that staves 4 and 14 both display.

Asserted at the export level, not just at placement: this is the layer a user
actually sees, and it is where a mirror that resolved but never got written
would show up.
"""


_Contents = dict[int, list[tuple[tuple[tuple[str, int, int], ...], Fraction]]]


def _by_measure(part: Part) -> _Contents:
    """Measure number -> the pitches and durations it holds, spelling included."""
    return {
        m.number: [
            (tuple((p.step, p.octave, p.alteration) for p in e.pitches), e.duration)
            for v in m.voices
            for e in v.events
        ]
        for m in part.measures
    }


def test_a_mirrored_staff_exports_the_music_it_displays(
    mus_scores: list[tuple[Path, Score]],
) -> None:
    """See `MIRRORED_MEASURES`."""
    score = next(s for path, s in mus_scores if path.name == "Bach Concerto.MUS")
    parts = {p.id: p for p in score.parts}
    source, mirror = _by_measure(parts["P4"]), _by_measure(parts["P14"])
    agreeing = [
        number
        for number, events in source.items()
        if events and mirror.get(number) == events
    ]
    assert len(agreeing) >= MIRRORED_MEASURES
```

`mypy --strict` covers `tests` as well as `src` (`CODE = src tests scripts` in the Makefile), so every helper in these test files needs full annotations — an unannotated `def` or an `object`-typed parameter fails the gate. Add `from fractions import Fraction` and extend the existing `finale_file_parser.ir` import to `Part, Score`.

This module has no `_dcl_files` helper — it works from the session-scoped `mus_scores` fixture in `tests/conftest.py:65`, which yields `(path, Score)` for every `.mus` that builds. `Bach Concerto.MUS` only appears in that fixture once Tasks 1–2 are done, so `next(...)` raising `StopIteration` means the earlier tasks regressed, not that the test is wrong. `Path` and `Score` are already imported in this module.

- [ ] **Step 6: Run and verify**

Run: `uv run pytest tests/enigma/test_mus_dcl_score_corpus_sweep.py tests/export -q`

Expected: PASS.

- [ ] **Step 7: Mutation-check the mirror pins**

In `to_ir.py`, change the placement loop back to `location.get(entnum, ())[:1]`. Run:

`uv run pytest tests/enigma/test_mus_dcl_score_corpus_sweep.py tests/export -q`

Expected: **FAILS** on `MIRRORED_MEASURES` and on the event/pitch counts. Restore by editing it back, then re-run to confirm green. If it does **not** fail, the pins are not guarding anything — fix them before continuing.

- [ ] **Step 8: Commit**

```bash
git add tests/enigma/test_mus_dcl_score_corpus_sweep.py tests/export/test_export_audit_corpus_sweep.py
git commit -m "test: pin the corpus mirroring that now reads

Bach Concerto.MUS builds, taking DCL coverage to 132 of 139 and leaving one
malformed document. Its 42 mirrored measures are pinned at the export level,
and the 239 multi-placed entries at the placement level -- a reader that
silently went back to one location per entry would still build every score
and pass every other count in this file."
```

---

### Task 4: Documentation, spec, and version

**Files:**
- Modify: `src/finale_file_parser/enigma/mus_document.py:132-141`
- Modify: `docs/ROADMAP.md:191-195`
- Modify: `docs/DECISIONS.md`
- Modify: `scripts/format_spec/__main__.py:166-186`
- Modify: `pyproject.toml:8`
- Regenerate: `docs/formats/finale-formats.{html,pdf}`

**Interfaces:**
- Consumes: the finished behaviour from Tasks 1–3. No code changes.

- [ ] **Step 1: Replace the `UNTRANSLATED` entry**

In `src/finale_file_parser/enigma/mus_document.py`, replace the whole "Mirrors: ..." string with a narrower one. The gap is no longer *mirrors*; it is what a mirror might carry that we cannot see:

```python
    "Mirror transposition: Finale's Mirror Tool appears to let a mirrored "
    "staff carry its own transposition or octave displacement. Mirrors "
    "themselves ARE read -- an entry holds a location per placement and the "
    "music is built onto every staff that displays it -- but no field carrying "
    "a per-mirror offset has been identified, and the only corpus document "
    "where a mirror reaches the score has both staves transposing by zero. So "
    "nothing here can test one, and fitting an offset to a single point would "
    "be a guess. A mirror is therefore read as the same music in both places, "
    "which is right for this corpus and may be incomplete in general. "
    "Pinned as MIRRORED_ENTRIES.",
```

- [ ] **Step 2: Close the roadmap item**

In `docs/ROADMAP.md`, delete item 2 ("**Mirrors.** ...") from the numbered "What remains" list, renumber the items after it, and in item 3 change "One is a mirror (above)." to:

```
   One was a mirror and now reads.
```

- [ ] **Step 3: Record the decision**

Append to `docs/DECISIONS.md`:

```markdown
## Mirror direction is not inferred

**Decided 2026-08-10.** A Finale mirror stores one entry span, two `frameSpec`
records naming it, and two `gfhold` records naming those frames. Nothing marks
either placement as the original and the other as the copy.

`locate_entries` therefore returns the placements as **peers**, in frame-walk
order, and the order carries no meaning. Direction could only be inferred — from
the lower frame `cmper`, or from `gfhold` order — and neither is evidence.

This costs nothing: a mirrored passage stays identifiable as an entry whose
location tuple holds more than one member, so "is this staff independent music
or a duplicate?" remains answerable without inventing an answer to "which came
first?".

**Reopen if** a field carrying mirror direction or a per-mirror transposition is
identified, at which point the offset in `UNTRANSLATED` closes too.
```

- [ ] **Step 4: Rewrite the format spec's mirror paragraph**

In `scripts/format_spec/__main__.py`, the `<dt>One mirror</dt>` block sits in a list of documents the reader does not read. It no longer belongs there. Move it out of that list, and replace the final two paragraphs (from "<p>Five DCL documents in the corpus contain mirrors" to the end of that `<dd>`) with:

```
<p>Five DCL documents in the corpus contain mirrors. In four, the duplicate
frame is never named by a <code>gfhold</code>, so the mirror never reaches the
score. In the fifth, two <code>gfhold</code> records name the same span across
42 measures, and the entries really are in two places at once.</p>

<p>This reader places an entry once per <code>gfhold</code> that claims it, and
builds the music onto every staff that displays it. Both placements are treated
as peers: since nothing in the file marks either as the copy, nothing here
guesses. MusicXML has no mirror of its own, so writing the notes onto both
staves is what Finale's own display amounts to.</p>
```

Three counts in the same section must move with it, all just above the `<dl>` at `scripts/format_spec/__main__.py:148-162`:

```python
                ("DCL .mus, 132 of 139", 132, "#c9954a"),
                ("Other", 7, "#b5534a"),
```

and the heading `<h4>The other eight files</h4>` becomes `<h4>The other seven files</h4>`.

The `<dt>One mirror</dt>` entry is removed from that `<dl>` entirely — it is a list of files the reader does *not* read, and a mirror no longer belongs in it. Keep the explanation of what a mirror is: move the whole block into §6 (Records), after the paragraph ending "frames naming the same entry span is how a <em>mirror</em> is stored" at line 528, converting the `<dt>/<dd>` into ordinary `<p>` elements. That paragraph already introduces the subject, so the moved text continues it rather than repeating it.

- [ ] **Step 5: Bump the version**

In `pyproject.toml`, change `version = "0.2.0"` to `version = "0.3.0"`.

- [ ] **Step 6: Regenerate the specification**

Run: `make spec`

Expected: `wrote finale-formats.html` and `wrote finale-formats.pdf`. The build is reproducible, so re-running gives byte-identical output; a diff in these files means the text really changed.

Verify the rendered result rather than trusting the edit: `grep -c "never reaches the score" docs/formats/finale-formats.html` should return 1.

- [ ] **Step 7: Run the full gate**

```bash
make check > /tmp/gate.log 2>&1; ec=$?
echo "exit=$ec"
tail -20 /tmp/gate.log
```

Expected: `exit=0`. **Do not commit on a non-zero exit.** If anything fails, fix it and re-run the whole gate.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "docs: mirrors are read, not refused

Replaces the UNTRANSLATED entry for mirrors with a narrower one for what a
mirror might carry that this corpus cannot show: a per-mirror transposition,
for which no field is identified and no test is possible.

Closes roadmap item 2, records in DECISIONS.md that mirror direction is
deliberately not inferred, and rewrites the specification's mirror paragraph,
which described why the reader refused a file it understood. Version 0.3.0:
locate_entries' signature is a published export and it changed."
```

---

## Verification

After Task 4, the branch should show:

- `make check` exits 0.
- `uv run pytest tests/enigma/test_mirrors.py -v` passes.
- DCL coverage is 132 of 139, with 1 malformed and 6 refused as blank.
- `MIRRORED_ENTRIES` is pinned at 239 and fails if placement returns to one location per entry.
- `docs/formats/finale-formats.pdf` no longer lists a mirror among the documents that fail to read.
- No file, comment or docstring claims to know which staff of a mirror is the copy.
