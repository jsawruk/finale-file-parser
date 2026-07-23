# EnigmaXML Keyed Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add O(1) keyed lookup (`get`, `all_with`) to the EnigmaXML document model, keyed by each record's surveyed identity, without dropping any record.

**Architecture:** Five keyed subclasses of the existing frozen `Pool` dataclass, each building an exact-key index and a cmper multimap at construction. `parse_enigma` constructs the typed pools. A duplicate full identity raises `MalformedEnigmaError`.

**Design spec:** `docs/superpowers/specs/2026-07-23-enigma-keyed-lookup-design.md`. Read it first — the per-pool identity table is measured across 3.1M corpus records.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`. Stdlib + defusedxml only.
- **Per-pool identity (measured, exact):**
  - `options`: tag alone
  - `others`: tag + `cmper` + `inci` + `part`
  - `details`: tag + (`cmper1`+`cmper2`) + `inci` + `part`, **or** tag + `entnum` + `inci` + `part`
  - `entries`: `entnum` (single tag `entry`)
  - `texts`: tag + `number` **xor** `type`
- **`get` returns one `Record | None`** (full identity is unique over 3.1M records). Omitting `part` targets the score record (no `part` attribute); passing `part` targets that variant.
- **`all_with(tag, cmper[, cmper2])` returns every record sharing that cmper** in document order — score record plus all per-part variants. Nothing dropped.
- **Key arguments normalize to `str`** — the model stores attrs as strings, so `get(t, 1)` == `get(t, "1")`.
- **A duplicate full identity raises `MalformedEnigmaError`** at index-build time. The corpus has 0 of 3.1M, so a duplicate means malformed input; do not silently keep one.
- The shipped `Pool.records` and `Pool.of_tag` must keep working unchanged; subclasses inherit them.
- `corpus/` is gitignored copyrighted material — no corpus bytes in fixtures; every test input constructed in-test; never print a corpus record value.
- Verify by mutation. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

## Note on the frozen-dataclass index pattern

`Pool` is a frozen dataclass. A keyed subclass declares its indexes as `field(init=False, ...)` and
populates them in `__post_init__` via `object.__setattr__` (frozen forbids normal assignment):

```python
@dataclass(frozen=True)
class OthersPool(Pool):
    _by_id: dict[tuple[str, ...], Record] = field(default_factory=dict, init=False, repr=False, compare=False)
    _by_cmper: dict[tuple[str, str], list[Record]] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_id: dict[tuple[str, ...], Record] = {}
        by_cmper: dict[tuple[str, str], list[Record]] = {}
        for r in self.records:
            ...  # build both, raising MalformedEnigmaError on a duplicate id
        object.__setattr__(self, "_by_id", by_id)
        object.__setattr__(self, "_by_cmper", by_cmper)
```

Verified: this passes `mypy --strict` and keeps `.records`/`.of_tag` intact.

---

### Task 1: Keyed pool subclasses

**Files:**
- Modify: `src/finale_file_parser/enigma/document.py`, `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/__init__.py`, `tests/test_public_api.py`
- Test: `tests/enigma/test_keyed_lookup.py`

**Interfaces:**
- Consumes: existing `Pool`, `Record`, `MalformedEnigmaError`, `parse_enigma`.
- Produces: `OptionsPool`, `OthersPool`, `DetailsPool`, `EntriesPool`, `TextsPool` (subclasses of `Pool`); a `.record` property on `Pool`; `EnigmaDocument.options/others/details/entries/texts` typed as the subclasses. All new pool types exported from `finale_file_parser.enigma` and the package root.

**The record's stored identity and a `get` call's identity MUST line up byte-for-byte, and there is one trap that silently breaks every lookup if you get it wrong.** It was caught while writing this plan and verified against all 401 corpus files:

- **`inci` has a default of `"0"`.** A record with no `inci` attribute is the same as `inci="0"` (Finale's default), and the two never coexist in the corpus (verified: 0 collisions when collapsed, across 3.1M records). So the record's stored identity uses `attrs.get("inci", "0")`, and `get`'s `inci: int | str = 0` default normalizes to `"0"`. **If instead the record used `attrs.get("inci")` (→ `None`) while `get` sent `"0"`, `get("measSpec", 1)` would return `None` for a record that exists** — a silent miss on every part-less lookup. Do not make that mistake.
- **`part` has NO default — absent means "the score record".** A record with no `part` attribute stores `None`; `get(..., part=None)` sends `None`. A record with `part="1"` is matched by `get(..., part=1)` → `"1"`. There is no `part="0"` in the corpus, so `None` for absent is unambiguous.
- **`cmper`, `cmper1`, `cmper2`, `entnum`, `number`, `type`:** absent → `None` on both sides (no default). In `details`, `get` fills `cmper1`/`cmper2` and leaves `entnum` `None`; `for_entry` fills `entnum` and leaves the pair `None`. Both are unique.

So the normalization is: `_key_part(value, default=None)` returns `default if value is None else str(value)`, called with `default="0"` for `inci` and `default=None` for everything else, on BOTH the record side (`attrs.get(attr)`) and the argument side. Verified: the corrected identity is unique across all 401 archives with zero collisions.

This is the measSpec case and the most important behaviour — the tests for `get("measSpec", 1)` hitting the score record and `get("measSpec", 1, part=1)` hitting the variant are the ones that would fail if the `inci`/`part` alignment is wrong.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/test_keyed_lookup.py`:

```python
import pytest

from finale_file_parser.enigma.document import (
    DetailsPool,
    EntriesPool,
    MalformedEnigmaError,
    OptionsPool,
    OthersPool,
    Pool,
    TextsPool,
    parse_enigma,
)

NS = "http://www.makemusic.com/2012/finale"


def _doc(body: str) -> bytes:
    return f'<finale version="18.0" xmlns="{NS}">{body}</finale>'.encode()


FULL = _doc(
    """
    <header><headerData><wordOrder>1</wordOrder></headerData></header>
    <mappings><mapGroup minInclusive="17.0"/></mappings>
    <options><beamOptions><maxSlope>10</maxSlope></beamOptions></options>
    <others>
      <articDef cmper="1"><charMain>46</charMain></articDef>
      <articDef cmper="2"><charMain>47</charMain></articDef>
      <textBlock cmper="5" inci="0"><t>a</t></textBlock>
      <textBlock cmper="5" inci="1"><t>b</t></textBlock>
      <measSpec cmper="1"><s>score</s></measSpec>
      <measSpec cmper="1" part="1" shared="true"><s>p1</s></measSpec>
      <measSpec cmper="1" part="2" shared="true"><s>p2</s></measSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="2"><v>x</v></gfhold>
      <perfData entnum="9" inci="0"><vel>64</vel></perfData>
    </details>
    <entries><entry entnum="1"><dura>1024</dura></entry></entries>
    <texts>
      <expression number="3"><t>cresc.</t></expression>
      <fileInfo type="title"><t>PLACEHOLDER</t></fileInfo>
    </texts>
    """
)


def test_pool_subtypes() -> None:
    doc = parse_enigma(FULL)
    assert isinstance(doc.options, OptionsPool)
    assert isinstance(doc.others, OthersPool)
    assert isinstance(doc.details, DetailsPool)
    assert isinstance(doc.entries, EntriesPool)
    assert isinstance(doc.texts, TextsPool)
    assert isinstance(doc.header, Pool)  # plain Pool singleton


def test_options_get_by_tag() -> None:
    doc = parse_enigma(FULL)
    assert doc.options.get("beamOptions").fields["maxSlope"] == "10"
    assert doc.options.get("missing") is None


def test_others_get_exact() -> None:
    doc = parse_enigma(FULL)
    assert doc.others.get("articDef", 1).fields["charMain"] == "46"
    assert doc.others.get("articDef", "2").fields["charMain"] == "47"  # str arg
    assert doc.others.get("textBlock", 5, inci=1).fields["t"] == "b"
    assert doc.others.get("articDef", 999) is None


def test_others_part_disambiguation() -> None:
    """The measSpec case: score record has no part; variants have part=1/2."""
    doc = parse_enigma(FULL)
    assert doc.others.get("measSpec", 1).fields["s"] == "score"          # part omitted -> score
    assert doc.others.get("measSpec", 1, part=1).fields["s"] == "p1"
    assert doc.others.get("measSpec", 1, part=2).fields["s"] == "p2"


def test_others_all_with_returns_score_plus_all_parts() -> None:
    doc = parse_enigma(FULL)
    variants = doc.others.all_with("measSpec", 1)
    assert [r.fields["s"] for r in variants] == ["score", "p1", "p2"]     # document order


def test_details_pair_and_entry_forms() -> None:
    doc = parse_enigma(FULL)
    assert doc.details.get("gfhold", 1, 2).fields["v"] == "x"
    assert doc.details.for_entry("perfData", 9, inci=0).fields["vel"] == "64"
    assert doc.details.get("gfhold", 9, 9) is None


def test_entries_get_by_entnum() -> None:
    doc = parse_enigma(FULL)
    assert doc.entries.get(1).fields["dura"] == "1024"
    assert doc.entries.get(999) is None


def test_texts_get_by_number_or_type() -> None:
    doc = parse_enigma(FULL)
    assert doc.texts.get("expression", number=3).fields["t"] == "cresc."
    assert doc.texts.get("fileInfo", type="title").fields["t"] == "PLACEHOLDER"


def test_singleton_record_convenience() -> None:
    doc = parse_enigma(FULL)
    assert doc.header.record.tag == "headerData"
    assert doc.mappings.record.tag == "mapGroup"
    assert parse_enigma(_doc("<others/>")).header.record is None


def test_of_tag_still_works() -> None:
    doc = parse_enigma(FULL)
    assert len(doc.others.of_tag("measSpec")) == 3
    assert len(doc.others.records) == 7


def test_duplicate_identity_raises() -> None:
    dup = _doc('<others><articDef cmper="1"><x>a</x></articDef>'
               '<articDef cmper="1"><x>b</x></articDef></others>')
    with pytest.raises(MalformedEnigmaError, match="duplicate"):
        parse_enigma(dup)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma/test_keyed_lookup.py -v`
Expected: FAIL — `ImportError: cannot import name 'OthersPool'`

- [ ] **Step 3: Implement the pool subclasses**

In `src/finale_file_parser/enigma/document.py`, add a `.record` property to `Pool` and the five subclasses. Use the frozen-dataclass index pattern from the plan header. Sketch:

```python
@dataclass(frozen=True)
class Pool:
    records: tuple[Record, ...]

    def of_tag(self, tag: str) -> tuple[Record, ...]:
        return tuple(r for r in self.records if r.tag == tag)

    @property
    def record(self) -> Record | None:
        """The single record of a singleton pool (header/mappings), or None."""
        return self.records[0] if self.records else None


def _key(value: int | str | None, default: str | None = None) -> str | None:
    # Normalize one identity component. `default` is "0" for inci (absent inci
    # means inci=0, verified across the corpus), and None for everything else
    # (absent means "not this key" / the score record for part).
    return default if value is None else str(value)


class _KeyedPool(Pool):
    """Shared index construction: an exact-identity dict raising on collision."""

    _ID_ATTRS: tuple[str, ...] = ()      # override per pool

    _by_id: dict[tuple[str | None, ...], Record] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        by_id: dict[tuple[str | None, ...], Record] = {}
        for r in self.records:
            key = (r.tag,) + tuple(
                _key(r.attrs.get(a), "0" if a == "inci" else None) for a in self._ID_ATTRS
            )
            if key in by_id:
                raise MalformedEnigmaError(f"duplicate record identity {key}")
            by_id[key] = r
        object.__setattr__(self, "_by_id", by_id)
```

Then each pool sets `_ID_ATTRS` and exposes typed `get`/`all_with`. `others` needs the `_by_cmper`
multimap too (for `all_with`); `details` has two `_ID_ATTRS` shapes (pair vs entnum) — model it as
one identity tuple `(tag, cmper1, cmper2, entnum, inci, part)` with `attrs.get` yielding `None` for
the absent ones, so `get` fills `cmper1/cmper2` and `for_entry` fills `entnum`, and both are unique.
`texts` identity is `(tag, number, type)`. `entries` identity is `(entnum,)` (single tag).

Make `@dataclass(frozen=True)` decorate each concrete subclass. Keep `MalformedEnigmaError` the
existing type from Task-of-the-prior-slice.

Update `parse_enigma` to construct the typed pool per name (a small dispatch dict `name -> PoolCls`),
and update `EnigmaDocument.__init__` to accept and expose the subclasses with their concrete types
(`options: OptionsPool`, etc.; `header`/`mappings` stay `Pool`).

Export `OptionsPool`, `OthersPool`, `DetailsPool`, `EntriesPool`, `TextsPool` from
`enigma/__init__.py` and the package root; add them to `EXPECTED_PUBLIC_NAMES` in
`tests/test_public_api.py`. The derived public-API test asserts subpackage `__all__` reachability —
satisfy it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: PASS — the new lookup tests plus everything else unchanged.

- [ ] **Step 5: Mutation-verify**

| Mutation | Test that must fail |
|---|---|
| Drop `part` from `others` `_ID_ATTRS` | `test_duplicate_identity_raises` (measSpec collapses) OR `test_others_part_disambiguation` |
| `get` ignores `inci` | `test_others_get_exact` |
| Remove the duplicate-identity check (last write wins) | `test_duplicate_identity_raises` |
| `all_with` returns only the exact match | `test_others_all_with_returns_score_plus_all_parts` |
| `_norm` does not `str()` the argument | `test_others_get_exact` (the `str` vs `int` arg case) |

The first is the important one: dropping `part` makes the three measSpec records collide on
`(measSpec, 1, inci, ...)`, so either the duplicate check fires (identity now non-unique) or the
part-disambiguation test fails. Record which; both prove `part` is load-bearing.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests
git commit -m "feat: add keyed lookup to the EnigmaXML document pools"
```

---

### Task 2: Corpus sweep — uniqueness and round-trip

**Files:** Create `tests/enigma/test_keyed_lookup_corpus_sweep.py`. Skips when `corpus/` is absent.

This is the guarantee `get` rests on. If any real file breaks full-identity uniqueness, this must fail rather than `get` silently returning one of several.

- [ ] **Step 1: Write the test**

Over all 401 `.musx` archives, compose `parse_enigma(score_xml(path))` and assert:

- **every archive parses without raising** — the index build itself is the uniqueness check, so a
  duplicate identity anywhere would already raise `MalformedEnigmaError`. Assert 401/401 succeed.
- a positive round-trip: for a sample of records drawn from the parsed document (not hardcoded
  values), `get` retrieves the same object — e.g. for every `entry`, `entries.get(entnum)` returns
  a record whose `entnum` matches; for a `measSpec` that has a `part`, `others.get("measSpec",
  cmper, part=part)` returns it and `all_with("measSpec", cmper)` contains it.
- across the sweep, at least one `measSpec` with a `part` is exercised through `get`+`all_with`
  (the linked-part case against real data).

Assert the file list is non-empty first. **If an observed value disagrees, report it rather than
adjusting the assertion.** Report counts only — never a corpus record value.

Note the existing document corpus sweep already decodes all 401 files (~80-120s); this adds a second
such sweep. Keep it focused so total local test time stays reasonable; if it is too slow, sample a
subset of files for the round-trip portion but still run the parse (uniqueness) check on all 401.

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/enigma/test_keyed_lookup_corpus_sweep.py -v` — expected pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/enigma -v; mv /tmp/corpus-parked corpus`

Expected: this sweep skipped, other enigma tests pass. **Confirm `corpus/` is restored and reports
639 files.**

- [ ] **Step 3: Commit**

```bash
git add tests/enigma/test_keyed_lookup_corpus_sweep.py
git commit -m "test: assert keyed-identity uniqueness across the corpus"
```

---

### Task 3: Documentation

**Files:** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Add the complete per-pool identity table (options: tag; others: tag+cmper+inci+part; details:
tag+cmper1+cmper2 or entnum, +inci+part; entries: entnum; texts: tag+number xor type) and that it is
unique across all 401 corpus archives (3.1M records, zero collisions). Note `part` is Finale's
linked-parts discriminant (score record + per-part variants sharing a cmper), that `get` returns the
exact record and `all_with` returns the whole linked set, and that a duplicate identity raises
`MalformedEnigmaError`. Link the design spec.

- [ ] **Step 2: `docs/ROADMAP.md`**

Mark keyed lookup done. Set the next item to **typed record models, starting with `entries`/`note`**
(pitches, durations) — the model now supports both walking (`of_tag`) and direct access (`get`).
Note cross-pool link resolution (what a cmper *references*) is a separate later slice.

- [ ] **Step 3: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record the per-pool identity keys and keyed lookup"
```

---

## Completion

After Task 3, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed; the per-pool identity keys and that they are unique across
3.1M corpus records; that `get` returns the exact record and `all_with` the linked-part set so
nothing is dropped; that a duplicate identity raises rather than silently keeping one; the mutation
results (especially the `part`-drop one); and that the corpus sweep asserts uniqueness across 401
files and skips in CI.
