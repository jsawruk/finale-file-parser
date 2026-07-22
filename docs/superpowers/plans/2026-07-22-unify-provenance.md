# Unified Provenance Stamps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Express `.mus` and `.musx` provenance with one shared `ProvenanceStamp` type instead of two incompatible ones.

**Architecture:** Rename `MusStamp` to `ProvenanceStamp` and extend it with the two fields only `.musx` has, keeping `.mus` behaviour identical. Then move `.musx` onto it — extracting the dates and `modifiedBy` it currently discards, dropping the collapsed `MusxDetail.platform` in favour of a platform on each stamp, and reaching `app_version` through the stamp when building the label.

**Tech Stack:** Python 3.12, stdlib only, pytest, ruff, mypy --strict.

**Design spec:** `docs/superpowers/specs/2026-07-22-unify-provenance-design.md`. Read it first.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`. Stdlib only.
- **This is an intentional breaking change, so the usual rule inverts.** Previous slices required existing tests to pass unmodified. Here `MusxDetail.created` changes type and `MusxDetail.platform` is removed, so tests asserting on those **must** be updated. That is correct, not a smell.
- **The replacement guard — this is what proves behaviour is preserved:**
  - `detect_version`'s `label` and `confidence` must not change for any input. **Every existing label assertion must pass untouched.** If a label test needs editing, behaviour changed — stop and report BLOCKED.
  - `modified` remains the layout authority for `.musx`; its existing test must keep passing untouched.
  - Corpus tallies unchanged: 401 `.musx` at schema 18.0; 238 `.mus` with 136 `MAC` / 102 `WIN`.
- Field defaults: `modified_by: str = ""` and `app_version: AppVersion | None = None`. `.mus` leaves both at defaults.
- `appRegion` is deliberately **not** modelled — one observed value (`US`) across 802 blocks carries no information yet.
- `corpus/` is gitignored copyrighted material. Never commit it; never quote a filename, title, or payload.
- Verify by mutation, per project practice: delete a rule, confirm its test fails, restore. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

---

### Task 1: Introduce `ProvenanceStamp`

**Files:**
- Modify: `src/finale_file_parser/version/models.py`
- Modify: `src/finale_file_parser/version/mus.py`, `src/finale_file_parser/__init__.py`
- Modify: `tests/version/test_mus_stamps.py`, `tests/test_public_api.py`
- Test: extend `tests/version/test_mus_stamps.py`

**Interfaces:**
- Produces: `ProvenanceStamp` (frozen dataclass: `year: int`, `month: int`, `day: int`, `application: str`, `platform: str`, `modified_by: str = ""`, `app_version: AppVersion | None = None`). `MusStamp` ceases to exist. Task 2 consumes this.

This task is a rename plus two new optional fields. `.mus` parsing behaviour is unchanged — it never populates `modified_by` or `app_version`.

- [ ] **Step 1: Rename and extend the type**

In `models.py`, rename `MusStamp` to `ProvenanceStamp` and add the two fields. Keep each field's own docstring.

```python
@dataclass(frozen=True)
class ProvenanceStamp:
    """When a file was written, by what application, on which platform.

    Both formats produce these. `.musx` additionally fills `app_version`, and
    may fill `modified_by`; `.mus` leaves both at their defaults.
    """

    year: int
    month: int
    day: int

    application: str
    """Observed: "FIN"."""

    platform: str
    """Observed: "MAC" or "WIN". Each stamp carries its own — do not assume
    both stamps in a file agree."""

    modified_by: str = ""
    """Who last wrote the file. `.musx` only; non-empty in 28 of 802 corpus
    blocks, where it holds a person's initials. Empty for `.mus`."""

    app_version: AppVersion | None = None
    """The writing application's version. `.musx` only — `.mus` records no
    version in its stamps, only the banner year."""
```

Update `MusDetail.created` / `.modified` annotations to `ProvenanceStamp | None`.

- [ ] **Step 2: Update the `.mus` parser and exports**

In `version/mus.py`, change the `MusStamp` import and construction to `ProvenanceStamp`. Nothing else changes — it does not set the new fields.

In `src/finale_file_parser/__init__.py`, replace `MusStamp` with `ProvenanceStamp` in the imports and `__all__`. Update `EXPECTED_PUBLIC_NAMES` in `tests/test_public_api.py`.

- [ ] **Step 3: Update the `.mus` stamp tests**

In `tests/version/test_mus_stamps.py`, update the import and any `MusStamp` reference. **Do not change any assertion** — the `.mus` values are unchanged by this task, so every existing assertion must still hold as written.

- [ ] **Step 4: Add tests for the new defaults**

Append:

```python
def test_mus_stamps_leave_the_musx_only_fields_at_defaults(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    """.mus records no version and no author in its stamps."""
    created = parse(mus_metadata_header()).created
    assert created is not None
    assert created.modified_by == ""
    assert created.app_version is None
```

- [ ] **Step 5: Run tests, gate, commit**

Run: `uv run pytest tests -v` — expected: all pass, count one higher than before.
Run: `make check` — clean.

Confirm no stale name remains: `grep -rn "MusStamp" src tests scripts docs` should return only historical references inside dated spec/plan files under `docs/superpowers/`, which are records and must not be rewritten.

```bash
git add src/finale_file_parser tests
git commit -m "refactor: rename MusStamp to ProvenanceStamp and add musx-only fields"
```

---

### Task 2: Move `.musx` onto `ProvenanceStamp`

**Files:**
- Modify: `src/finale_file_parser/version/models.py` (`MusxDetail`)
- Modify: `src/finale_file_parser/version/musx.py`, `src/finale_file_parser/version/detect.py`
- Modify: `tests/version/test_musx.py`, `tests/version/test_models.py`
- Test: extend `tests/version/test_musx.py`

**Interfaces:**
- Consumes: `ProvenanceStamp` from Task 1.
- Produces: `MusxDetail` with `created: ProvenanceStamp | None`, `modified: ProvenanceStamp | None`, `metadata_schema: str`. **`platform` is removed.**

This is the substantive task. `version/musx.py` currently reads only `platform` from each block, collapses the two with `or`, and discards the dates and `modifiedBy`.

- [ ] **Step 1: Reshape `MusxDetail`**

```python
@dataclass(frozen=True)
class MusxDetail:
    """Version evidence from a .musx NotationMetadata.xml."""

    created: ProvenanceStamp | None
    modified: ProvenanceStamp | None
    """The last writer. This is the layout authority — prefer it over `created`."""

    metadata_schema: str
```

Delete the `platform` field. Platform now lives on each stamp.

- [ ] **Step 2: Extract full stamps in `version/musx.py`**

Replace the `_app_version`-only extraction with one that builds a whole stamp from a block. Keep the existing namespace-tolerant `_find`, `_text`, `_int`, and `_app_version` helpers — `_app_version` becomes a component of the stamp rather than the whole result.

```python
def _stamp(block: Element | None) -> ProvenanceStamp | None:
    """Build a provenance stamp from a created/modified block.

    Returns None when the block is absent or carries no usable date. Unlike
    `.mus`, a `.musx` block may legitimately omit `maint`, so a missing
    optional field does not invalidate the stamp.
    """
    if block is None:
        return None
    year, month, day = _int(block, "year"), _int(block, "month"), _int(block, "day")
    if year is None or month is None or day is None:
        return None
    return ProvenanceStamp(
        year=year,
        month=month,
        day=day,
        application=_text(block, "application") or "",
        platform=_text(block, "platform") or "",
        modified_by=_text(block, "modifiedBy") or "",
        app_version=_app_version(block),
    )
```

And in `read`:

```python
    return MusxDetail(
        created=_stamp(created),
        modified=_stamp(modified),
        metadata_schema=root.get("version") or "",
    )
```

Update `_empty()` to drop the `platform` argument. Remove the now-unused `_platform` helper.

**Note the behaviour change this implies and keep it deliberate:** previously a block with an
`appVersion` but no date still produced a result; now a block without a usable date yields `None`.
Add a test pinning that, and make sure the "missing appVersion yields no version but still a stamp"
case is also covered — a block with dates but no `appVersion` must produce a stamp whose
`app_version` is `None`.

- [ ] **Step 3: Reach `app_version` through the stamp in `detect.py`**

```python
def _musx_label(detail: MusxDetail) -> str:
    stamp = detail.modified or detail.created
    app = stamp.app_version if stamp is not None else None
    if app is None:
        return UNKNOWN_LABEL
    number = f"{app.major}.{app.maint}" if app.maint is not None else str(app.major)
    parts = [number]
    if app.dev_status:
        parts.append(app.dev_status)
    if app.build is not None:
        parts.append(f"(build {app.build})")
    return " ".join(parts)
```

The `modified or created` precedence is unchanged and load-bearing: 264 of 401 corpus files were
created by major=16 and last modified by major=18.

**Confidence must be recomputed, or it silently changes meaning.** `detect.py` currently has:

```python
known = musx_detail.modified is not None or musx_detail.created is not None
```

Today those fields are `AppVersion`, so `known` means *"a version was parsed"*. After this task
they are stamps, so the same line would mean *"a date was parsed"* — and a `.musx` carrying dates
but no `appVersion` would flip from `UNKNOWN` to `EXACT` while still labelling `"unknown version"`.
That is exactly the behaviour change this branch's guard forbids. Replace it with an explicit
version check that preserves today's semantics:

```python
    stamp = musx_detail.modified or musx_detail.created
    known = stamp is not None and stamp.app_version is not None
```

Add a test pinning it: a `.musx` with dates but no `appVersion` must be `Confidence.UNKNOWN` with
label `"unknown version"`.

- [ ] **Step 4: Update the affected tests**

In `tests/version/test_musx.py`, update assertions that read `detail.created.major` and friends to
go through `detail.created.app_version`, and replace `detail.platform` with
`detail.modified.platform`. In `tests/version/test_models.py`, update the `MusxDetail(...)`
construction.

**Do not touch any label assertion in `tests/version/test_detect.py`** — those are the guard. If one
fails, behaviour changed; stop and report BLOCKED.

- [ ] **Step 5: Make `SAMPLE_METADATA` realistic first**

`tests/version/conftest.py`'s `SAMPLE_METADATA` currently carries `platform` and `appVersion` but
**no `year`/`month`/`day`** — which no real file does: all 802 corpus blocks have dates. With
`_stamp()` requiring a date, the default fixture would produce *no stamps* and several existing
tests would break for a reason that has nothing to do with the change.

Add dates to both blocks, keeping every existing element and value untouched so the assertions that
already read `platform` and `appVersion` still hold:

```python
    <created>
      <year>2010</year><month>9</month><day>14</day>
      <platform>MAC</platform>
      <appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>
    </created>
    <modified>
      <year>2015</year><month>11</month><day>23</day>
      <platform>WIN</platform>
      <appVersion><major>18</major><maint>5</maint><devStatus>dev</devStatus><build>7098</build></appVersion>
    </modified>
```

This is a fixture becoming *more* faithful to the format, not a test being weakened to fit the code.

- [ ] **Step 6: Add tests for the newly-extracted data**

Append to `tests/version/test_musx.py`:

```python
def test_extracts_dates_from_both_blocks(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx())
    assert detail.created is not None and detail.modified is not None
    assert (detail.created.year, detail.created.month, detail.created.day) == (2010, 9, 14)
    assert (detail.modified.year, detail.modified.month, detail.modified.day) == (2015, 11, 23)


def test_each_stamp_carries_its_own_platform(make_musx: Callable[..., Path]) -> None:
    detail = read(make_musx())
    assert detail.created is not None and detail.modified is not None
    assert detail.created.platform == "MAC"
    assert detail.modified.platform == "WIN"


def test_extracts_modified_by(make_musx: Callable[..., Path]) -> None:
    metadata = SAMPLE_METADATA.replace("<modifiedBy/>", "<modifiedBy>ABC</modifiedBy>")
    detail = read(make_musx(metadata=metadata))
    assert detail.modified is not None
    assert detail.modified.modified_by == "ABC"


def test_block_without_a_date_yields_no_stamp(make_musx: Callable[..., Path]) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><platform>MAC</platform>"
        "<appVersion><major>18</major></appVersion></modified></fileInfo></metadata>"
    )
    assert read(make_musx(metadata=metadata)).modified is None


def test_block_with_dates_but_no_app_version_still_yields_a_stamp(
    make_musx: Callable[..., Path],
) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><year>2015</year><month>1</month><day>2</day>"
        "<platform>MAC</platform></modified></fileInfo></metadata>"
    )
    stamp = read(make_musx(metadata=metadata)).modified
    assert stamp is not None
    assert stamp.app_version is None
    assert stamp.year == 2015
```

These match the dates added in the previous step. Read `SAMPLE_METADATA` rather than assuming.

- [ ] **Step 7: Verify the guard**

Run: `uv run pytest tests/version/test_detect.py -v`
Expected: PASS, **with no edits to that file**. Confirm with `git diff --stat tests/version/test_detect.py` — no output.

- [ ] **Step 8: Mutation-verify**

| Mutation | Test that must fail |
|---|---|
| `_musx_label` prefers `created` over `modified` | the existing `modified`-over-`created` priority test |
| `_stamp` returns a stamp when the date is missing | `test_block_without_a_date_yields_no_stamp` |
| `_stamp` reads `platform` from the other block | `test_each_stamp_carries_its_own_platform` |
| `_stamp` drops `modified_by` | `test_extracts_modified_by` |

- [ ] **Step 9: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests/version
git commit -m "feat: extract full provenance stamps from .musx metadata"
```

---

### Task 3: Fixtures and corpus sweep

**Files:**
- Modify: `scripts/build_version_fixtures.py`
- Modify: `tests/fixtures/version/MANIFEST.toml` (regenerated)
- Modify: `tests/version/test_fixtures.py`, `tests/version/test_corpus_sweep.py`

**Interfaces:** consumes `ProvenanceStamp`; produces no importable API.

- [ ] **Step 1: Update the generator**

`scripts/build_version_fixtures.py` selects `.musx` fixtures by `(major, platform)` and writes
manifest entries. Update both for the new shape: reach `major` through
`detail.modified.app_version`, and platform through `detail.modified.platform`.

Extend `.musx` manifest entries with their stamps, matching the `.mus` entries' existing shape.

**The content rule is unchanged and must hold:** `.musx` fixtures contain only `mimetype` and
`NotationMetadata.xml`, with the metadata scrubbed to the root `version` attribute and the
`created`/`modified` subtrees, attributes stripped, and **`modifiedBy` blanked**. Exposing
`modified_by` through the API does not change what may be committed — the corpus holds real
initials, and they must not enter the repo.

- [ ] **Step 2: Regenerate and verify**

Run: `uv run python scripts/build_version_fixtures.py`

Then confirm by direct inspection that no committed fixture carries a non-empty `modifiedBy`:

```bash
python3 -c "
import zipfile, pathlib, re
for p in sorted(pathlib.Path('tests/fixtures/version').glob('*.musx')):
    x = zipfile.ZipFile(p).read('NotationMetadata.xml').decode()
    for m in re.findall(r'<modifiedBy>(.*?)</modifiedBy>', x, re.S):
        assert not m.strip(), (p.name, m)
    print(p.name, 'modifiedBy clean')
"
```

If any is non-empty, stop and fix the generator.

- [ ] **Step 3: Update the fixture tests**

In `tests/version/test_fixtures.py`, update assertions reading `.platform` off the detail to read
it off a stamp, and extend the manifest comparison to cover the `.musx` stamps.

- [ ] **Step 4: Update the corpus sweep**

`tests/version/test_corpus_sweep.py` reads `detail.created.platform` for `.mus` (unchanged) and
asserts `.musx` schema. Add `.musx` assertions: every archive yields both stamps; every stamp's
`application` is non-empty; the `modified`-over-`created` divergence still holds for the 264 files
that differ.

**Tallies must be unchanged**: 401 `.musx` at schema 18.0, 238 `.mus` with 136 `MAC` / 102 `WIN`.
If an observed value disagrees, report it rather than adjusting the assertion.

- [ ] **Step 5: Run, gate, commit**

Run: `uv run pytest tests -v` then `make check` — both clean. Confirm `git status` shows nothing
under `corpus/` staged.

```bash
git add scripts tests
git commit -m "test: cover unified provenance in fixtures and the corpus sweep"
```

---

### Task 4: Documentation

**Files:** `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: Close the open question**

In `docs/DECISIONS.md`, remove the OPEN bullet on unifying `.musx` provenance and add:

```markdown
## 2026-07-22 — DECIDED: one provenance type for both formats

`ProvenanceStamp` (renamed from `MusStamp`) carries date, application, and platform for both `.mus`
and `.musx`, plus `modified_by` and `app_version` which only `.musx` fills. `MusxDetail.platform`
was removed — platform now lives on each stamp, matching `.mus`'s rule that both stamps must not be
assumed to agree.

Reason: the formats recorded the same facts and the code modelled them twice, one module apart —
`.musx` discarded its dates entirely and collapsed two platforms into one field. Breaking the
published type was cheap at 0.0.1 and would only get more expensive.

`appRegion` is deliberately not modelled: `US` in all 802 corpus blocks, so it carries no
information yet.
```

- [ ] **Step 2: Update ARCHITECTURE.md**

Record that both formats produce `ProvenanceStamp`; that `.musx` blocks are a superset (they add
`appVersion` and `modifiedBy`); and that `modifiedBy` is non-empty in 28 of 802 corpus blocks and
is blanked in committed fixtures.

- [ ] **Step 3: Make `score.dat` the next roadmap item**

In `docs/ROADMAP.md`, move `score.dat` decoding to the top of Later — or into its own next-up
section — and state plainly why: it is the wall between this project and actual notes, and pitches,
rhythms, staves, and MusicXML all sit behind it. Note that the community EnigmaXML documentation
may be read as reference, per the decision already recorded, with implementations written
independently.

- [ ] **Step 4: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record unified provenance and queue score.dat as next"
```

---

## Completion

After Task 4, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what unified; that this is an intentional breaking change and why the
usual "existing tests unmodified" guard was replaced by the label/confidence guard; that every
label assertion passed untouched; the mutation results; that corpus tallies are unchanged; and that
`modifiedBy` is exposed through the API but still blanked in committed fixtures.
