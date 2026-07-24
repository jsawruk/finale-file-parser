# Entry Location Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `locate_entries(doc) -> dict[int, EntryLocation]` — resolve each entry to its staff, measure, and the raw key signature in force (inheritance applied, not decoded).

**Architecture:** A pure `enigma/location.py`. It walks `gfhold → frameSpec → entry next-chain` to place each entry in a (staff, measure), and computes the effective key per measure by forward-inheritance over `measSpec`. The first cross-pool link resolution.

**Design spec:** `docs/superpowers/specs/2026-07-23-entry-location-design.md`. Read it first.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`. Stdlib + defusedxml only.
- **`locate_entries` is pure over the parsed `EnigmaDocument`** — no I/O, no `score_xml`/`open_musx`. Uses the document's pools (`of_tag`, keyed lookup). A caller composes `locate_entries(parse_enigma(score_xml(path)))`.
- **The link chain (verified against the corpus):** `gfhold` (details) has `cmper1` = staff, `cmper2` = measure, and fields `frame1…frame4`; each frame value is a `frameSpec` (others) cmper; `frameSpec.startEntry` begins an entry chain followed via each entry's **`next` attribute** (`prev`/`next`/`entnum` are attributes, not fields) until `endEntry`.
- **Resolve all of `frame1…frame4`** (layers) — `frame2`/`frame3` occur on 299 of 6332 corpus gfholds; resolving only `frame1` would leave layer-2+ entries unlocated. A frame field absent, empty, or `"0"` is skipped.
- **Coverage is exact:** every entry lands in exactly one (staff, measure). Verified: 24,159 entries over 30 files, 0 orphans, 0 double-coverage. An entry placed twice is malformed input → raise.
- **Key is per measure** (`measSpec` keyed by measure, `part`-less records only). Effective key by inheritance: walk measures in order, carry the last `keySig.key` forward; a measure without `keySig` inherits; the first measure with no `keySig` defaults to `0`.
- **The key is exposed RAW (an int), not decoded.** Do not interpret it.
- **`MalformedScoreError`** (new, subclasses `FinaleFileError`) — an orphan entry (no frame places it), a frame pointing at a missing `frameSpec`, a non-integer `keySig.key` or `startEntry`, or a `next`-chain that exceeds a guard (cycle).
- `corpus/` is gitignored copyrighted material — no corpus bytes in fixtures; every test input built in-test; never print a record value.
- Verify by mutation. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

## Reference: the verified algorithm

This exact logic was run end-to-end on a real file (361/361 located, 0 orphans). The implementation
should follow it; the module wraps it with typed results, error handling, and the guard.

```python
# effective key per measure, by inheritance
last = 0
key_by_measure: dict[int, int] = {}
measures = sorted(m for m in part_less_measspec_cmpers)
for m in range(measures[0], measures[-1] + 1):
    rec = measspec.get("measSpec", m)      # part-less
    if rec is not None:
        ks = rec.fields.get("keySig")
        if isinstance(ks, Record):
            last = _int(ks.fields.get("key"))   # raises MalformedScoreError if not int
    key_by_measure[m] = last

# place each entry via gfhold -> frame -> next-chain
location: dict[int, EntryLocation] = {}
for gf in doc.details.of_tag("gfhold"):
    staff, measure = int(cmper1), int(cmper2)
    for fk in ("frame1", "frame2", "frame3", "frame4"):
        v = gf.fields.get(fk)
        if not (isinstance(v, str) and v and v != "0"):
            continue
        frame = others.get("frameSpec", int(v))       # or None -> MalformedScoreError
        cur, end, steps = int(startEntry), (int(endEntry) if endEntry else None), 0
        while cur is not None and cur in entries_by_num:
            if cur in location:
                raise MalformedScoreError(f"entry {cur} placed in two frames")
            location[cur] = EntryLocation(cur, staff, measure, key_by_measure.get(measure, 0))
            if cur == end:
                break
            steps += 1
            if steps > _CHAIN_GUARD:
                raise MalformedScoreError("entry chain exceeded guard (cycle?)")
            nxt = entries_by_num[cur].attrs.get("next")
            cur = int(nxt) if (nxt and nxt != "0") else None
```

---

### Task 1: `EntryLocation` and `locate_entries`

**Files:**
- Create: `src/finale_file_parser/enigma/location.py`
- Modify: `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/__init__.py`, `tests/test_public_api.py`
- Test: `tests/enigma/test_location.py`

**Interfaces:**
- Consumes: `EnigmaDocument`, `Record` from `enigma.document`; `FinaleFileError` from `finale_file_parser.errors`.
- Produces: `EntryLocation` (frozen: `entnum: int`, `staff: int`, `measure: int`, `key_signature: int`), `locate_entries(doc) -> dict[int, EntryLocation]`, `MalformedScoreError`. All exported from `finale_file_parser.enigma` and the package root.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/test_location.py`. Build documents via `parse_enigma` of synthetic XML so the test exercises the real pools:

```python
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
# (frame 11) has entry 3. Measure 1 sets key 2; measure 2 omits keySig (inherits).
BASIC = _doc(
    _entries("1:2", "2:0", "3:0")
    + """
    <others>
      <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>2</endEntry></frameSpec>
      <frameSpec cmper="11" inci="0"><startEntry>3</startEntry><endEntry>3</endEntry></frameSpec>
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


def test_places_entries_in_staff_and_measure() -> None:
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[1] == EntryLocation(entnum=1, staff=1, measure=1, key_signature=2)
    assert loc[2] == EntryLocation(entnum=2, staff=1, measure=1, key_signature=2)
    assert loc[3].measure == 2


def test_key_inheritance() -> None:
    # measure 2 has no keySig -> inherits key 2 from measure 1
    loc = locate_entries(parse_enigma(BASIC))
    assert loc[3].key_signature == 2


def test_first_measure_without_keysig_defaults_to_zero() -> None:
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>1</endEntry></frameSpec>
          <measSpec cmper="1"><width>100</width></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    assert locate_entries(parse_enigma(doc))[1].key_signature == 0


def test_raw_key_is_not_decoded() -> None:
    doc = _doc(
        _entries("1:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>1</endEntry></frameSpec>
          <measSpec cmper="1"><keySig><key>253</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    assert locate_entries(parse_enigma(doc))[1].key_signature == 253  # verbatim, not -3


def test_layers_frame2_entries_are_located() -> None:
    # one measure, two layers: frame 10 (entry 1), frame 20 (entry 2)
    doc = _doc(
        _entries("1:0", "2:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>1</endEntry></frameSpec>
          <frameSpec cmper="20" inci="0"><startEntry>2</startEntry><endEntry>2</endEntry></frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details>
          <gfhold cmper1="1" cmper2="1"><frame1>10</frame1><frame2>20</frame2></gfhold>
        </details>
        """
    )
    loc = locate_entries(parse_enigma(doc))
    assert loc[1].measure == 1 and loc[2].measure == 1   # both layers placed


def test_orphan_entry_raises() -> None:
    # entry 2 is not reachable from any frame
    doc = _doc(
        _entries("1:0", "2:0")
        + """
        <others>
          <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>1</endEntry></frameSpec>
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
          <frameSpec cmper="10" inci="0"><startEntry>1</startEntry><endEntry>999</endEntry></frameSpec>
          <measSpec cmper="1"><keySig><key>0</key></keySig></measSpec>
        </others>
        <details><gfhold cmper1="1" cmper2="1"><frame1>10</frame1></gfhold></details>
        """
    )
    with pytest.raises(MalformedScoreError):
        locate_entries(parse_enigma(doc))
```

Note the cycle test: `1 -> 2 -> 1` re-visits entry 1, which is already in `location`, so the
"placed in two frames" check fires — that is an acceptable way for the cycle to raise. If your guard
catches it first, also fine; either raises `MalformedScoreError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma/test_location.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.enigma.location'`

- [ ] **Step 3: Write the implementation**

Create `src/finale_file_parser/enigma/location.py`, following the verified algorithm in the plan
header. Key points:

- Build `entries_by_num = {int(e.attrs["entnum"]): e for e in doc.entries.of_tag("entry")}`.
- Effective key: iterate `range(min_measure, max_measure + 1)` over the `part`-less `measSpec`
  cmpers; carry `last` forward; default `0`.
- Place entries by walking `frame1…frame4`; use `doc.others.get("frameSpec", cmper)` and
  `doc.others.get("measSpec", cmper)` (keyed lookup). A frame value that resolves to no `frameSpec`
  raises `MalformedScoreError`.
- After placing, **verify no orphan**: every entnum in `entries_by_num` must be in `location`, else
  raise `MalformedScoreError` naming the orphan count.
- Guard the chain at a generous constant (e.g. `_CHAIN_GUARD = 1_000_000`); exceeding it raises.
- `_int(value, name)` helper raising `MalformedScoreError` on a non-integer.

Export `EntryLocation`, `locate_entries`, `MalformedScoreError` from `enigma/__init__.py` and the
package root; add them to `EXPECTED_PUBLIC_NAMES` in `tests/test_public_api.py`. Satisfy the derived
public-API test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: PASS — the new location tests plus everything else unchanged.

- [ ] **Step 5: Mutation-verify**

| Mutation | Test that must fail |
|---|---|
| Resolve only `frame1` (skip frame2–4) | `test_layers_frame2_entries_are_located` |
| Drop key inheritance (`key_by_measure[m]` = only this measure's keySig or 0) | `test_key_inheritance` |
| Skip the orphan check | `test_orphan_entry_raises` |
| Decode the key (e.g. `256 - k` for k > 127) instead of raw | `test_raw_key_is_not_decoded` |
| Remove the chain guard AND the double-place check | `test_next_chain_cycle_raises` (should hang without one of them — keep at least the double-place check) |

The layers and inheritance mutations are the important ones — they are the two behaviours the survey
proved necessary.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests
git commit -m "feat: resolve entries to staff/measure/key via cross-pool links"
```

---

### Task 2: Corpus sweep

**Files:** Create `tests/enigma/test_location_corpus_sweep.py`. Skips when `corpus/` is absent.

- [ ] **Step 1: Write the test**

Over all 401 archives, `locate_entries(parse_enigma(score_xml(path)))` and assert:

- **every entry is located exactly once** — `len(locate_entries(doc)) == number of entry records`,
  and `locate_entries` did not raise (the orphan/double-place checks are inside it). This is the
  guarantee the resolution rests on; the survey found 0 orphans over 24,159 entries, so any failure
  is a real finding.
- every location's `key_signature` is an `int`.
- every `staff` is among the document's `staffSpec` cmpers.
- across the sweep, at least one multi-layer measure is exercised (a gfhold with a `frame2`) — so
  layered resolution is covered against real data. (Detect by checking any gfhold has a `frame2`
  field; assert at least one file did.)

Assert the file list is non-empty first. **If an observed value disagrees, report it rather than
adjusting the assertion.** Report counts only — never a record value.

Note the enigma corpus sweeps are slow (~80-120s). Keep this focused.

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/enigma/test_location_corpus_sweep.py -v` — expected pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/enigma -v; mv /tmp/corpus-parked corpus`

Expected: this sweep skipped, other enigma tests pass. **Confirm `corpus/` is restored and reports
639 files** (case-insensitive — 101 files are uppercase `.MUS`).

- [ ] **Step 3: Commit**

```bash
git add tests/enigma/test_location_corpus_sweep.py
git commit -m "test: locate every corpus entry via the link chain"
```

---

### Task 3: Documentation

**Files:** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Add `enigma/location.py` to Modules. Add a "Known format facts — score linkage" subsection: an
entry names no staff/measure/key; the chain is `gfhold` (cmper1 = staff, cmper2 = measure, fields
`frame1…4` = layers) → `frameSpec` (cmper = frame; `startEntry` begins the entry `next`-chain) →
entries; `measSpec` (cmper = measure) carries `keySig` and the key is per-measure and **inherited**
(a measure without `keySig` uses the prior). Note the key value is exposed raw and its decoding is a
separate slice, and record the decode hints: fifths-style signed accidental count (−1 = F major,
+2 = D major), and the traps — enharmonic equivalents are distinct keys, a signature does not fix
major/minor, transposing instruments differ from concert pitch.

- [ ] **Step 2: `docs/ROADMAP.md`**

Mark link resolution done. Set the next items to: **decode the key signature** (raw int →
tonic/mode/accidentals, per the recorded hints), then **pitch spelling** (key + `harmLev`/`harmAlt`
→ spelled pitch). Then clefs, time signatures, tuplet scaling, the detail records, toward a
MusicXML exporter.

- [ ] **Step 3: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record the score link chain and queue key decoding"
```

---

## Completion

After Task 3, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed (`locate_entries` → `EntryLocation` per entry); the link chain
(`gfhold → frameSpec → entry next-chain`, all four frame layers, per-measure key with inheritance);
that the key is exposed raw and decoding is the next slice; the mutation results (especially layers
and inheritance); that the corpus sweep locates every entry in 401 archives with 0 orphans and skips
in CI; and that `locate_entries` raises `MalformedScoreError` on an orphan or broken link rather than
degrading.
