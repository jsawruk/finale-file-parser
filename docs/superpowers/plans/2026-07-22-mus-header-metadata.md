# `.mus` Header Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse the two provenance stamps in a `.mus` header into created/modified records carrying a date, application tag, and platform.

**Architecture:** A new `MusStamp` type and two optional fields on the existing `MusDetail`, populated by a pure function over a fixed header window in `version/mus.py`. `detect_version` reads a slightly larger header so the stamps are in range. No new modules, no new dependencies.

**Tech Stack:** Python 3.12, stdlib only, pytest, ruff, mypy --strict.

**Design spec:** `docs/superpowers/specs/2026-07-22-mus-header-metadata-design.md`. Read it first — it records the corpus survey this encodes, including a hypothesis that testing disproved.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`.
- ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`.
- **Exact offsets** (validated across all 238 corpus files): created stamp — date `0x66`, app tag `0x70`, platform tag `0x74`. Modified stamp — date `0x8C`, app tag `0x96`, platform tag `0x9A`. Date is 3 × `u8` as `[year - 1900, month, day]`.
- `MUS_METADATA_SIZE = 0xA0`.
- Plausibility rule: year 1980-2030, month 1-12, day 1-31.
- **`mus.parse` must never raise.** An unparseable stamp yields `None` for that stamp; banner and year are unaffected.
- **All-or-nothing stamps.** A stamp with an implausible date or an empty application tag is `None`, never partially filled — a caller cannot tell which half of a partial stamp to trust.
- **New `MusDetail` fields default to `None`**, so existing construction sites and tests keep working unmodified. Do not modify any existing test; append only. If an existing test fails, stop and report BLOCKED.
- `detect_version`'s `label` and `confidence` are unchanged — they derive from the banner year alone.
- `corpus/` is gitignored copyrighted material. Never commit it; never quote a filename, title, or payload.
- Every parsing rule verified by mutation: delete the rule, confirm its test fails, restore. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results in this repo.
- Conventional Commits. One commit per task.

---

### Task 1: Stamp parsing

**Files:**
- Modify: `src/finale_file_parser/version/models.py` (add `MusStamp`, extend `MusDetail`)
- Modify: `src/finale_file_parser/version/mus.py` (parse the stamps)
- Modify: `src/finale_file_parser/version/detect.py` (read a larger header)
- Modify: `src/finale_file_parser/__init__.py` (export `MusStamp`)
- Test: `tests/version/test_mus_stamps.py`

**Interfaces:**
- Consumes: `tests/version/conftest.py`, which already holds `mus_header` (a `0x60`-byte builder). That buffer is **too short to contain stamps**, so this task adds a sibling fixture there rather than duplicating the header layout in a test file — the same single-source rule the existing fixtures follow.
- Produces: `MusStamp` (frozen dataclass: `year: int`, `month: int`, `day: int`, `application: str`, `platform: str`), `MusDetail.created` / `MusDetail.modified` (both `MusStamp | None`, defaulting to `None`), `MUS_METADATA_SIZE = 0xA0` in `version/mus.py`, and the `mus_metadata_header` fixture. Tasks 2 and 3 consume these.

- [ ] **Step 1: Add the shared header builder**

Append to `tests/version/conftest.py`, keeping every existing fixture intact. Note it holds its own literal offsets on purpose, matching the existing `mus_header` rationale: the fixtures must not import production constants, so a wrong constant cannot make the tests agree with it.

```python
CREATED_DATE, CREATED_APP, CREATED_PLAT = 0x66, 0x70, 0x74
MODIFIED_DATE, MODIFIED_APP, MODIFIED_PLAT = 0x8C, 0x96, 0x9A
METADATA_BYTES = 0xA0


@pytest.fixture
def mus_metadata_header() -> Callable[..., bytes]:
    """Build a .mus header carrying banner plus both provenance stamps."""

    def build(
        banner: bytes = b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.",
        *,
        created: tuple[int, int, int] | None = (111, 10, 23),   # 2011-10-23
        modified: tuple[int, int, int] | None = (112, 4, 1),    # 2012-04-01
        app: bytes = b"FIN",
        platform: bytes = b"MAC",
        size: int = METADATA_BYTES,
    ) -> bytes:
        buf = bytearray(b"\x00" * size)
        buf[0 : len(MUS_MAGIC)] = MUS_MAGIC
        buf[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
        for date, date_off, app_off, plat_off in (
            (created, CREATED_DATE, CREATED_APP, CREATED_PLAT),
            (modified, MODIFIED_DATE, MODIFIED_APP, MODIFIED_PLAT),
        ):
            if date is None:
                continue
            buf[date_off : date_off + 3] = bytes(date)
            buf[app_off : app_off + len(app)] = app
            buf[plat_off : plat_off + len(platform)] = platform
        return bytes(buf)

    return build
```

- [ ] **Step 2: Write the failing tests**

Create `tests/version/test_mus_stamps.py`, using the fixture rather than a local builder:

```python
from collections.abc import Callable

from finale_file_parser.version.mus import parse


def test_parses_both_stamps(mus_metadata_header: Callable[..., bytes]) -> None:
    detail = parse(mus_metadata_header())
    assert detail.created is not None and detail.modified is not None
    assert (detail.created.year, detail.created.month, detail.created.day) == (2011, 10, 23)
    assert (detail.modified.year, detail.modified.month, detail.modified.day) == (2012, 4, 1)
    assert detail.created.application == "FIN"
    assert detail.created.platform == "MAC"


def test_banner_and_year_are_unaffected_by_stamps(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_metadata_header())
    assert detail.year == 2011
    assert detail.banner.startswith("Finale(R) 2011")


def test_windows_platform_tag(mus_metadata_header: Callable[..., bytes]) -> None:
    created = parse(mus_metadata_header(platform=b"WIN")).created
    assert created is not None
    assert created.platform == "WIN"


def test_implausible_month_yields_none_for_that_stamp_only(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_metadata_header(created=(111, 13, 1)))
    assert detail.created is None
    assert detail.modified is not None


def test_implausible_year_yields_none(mus_metadata_header: Callable[..., bytes]) -> None:
    assert parse(mus_metadata_header(created=(10, 6, 1))).created is None      # 1910
    assert parse(mus_metadata_header(created=(200, 6, 1))).created is None     # 2100


def test_implausible_day_yields_none(mus_metadata_header: Callable[..., bytes]) -> None:
    assert parse(mus_metadata_header(created=(111, 6, 0))).created is None
    assert parse(mus_metadata_header(created=(111, 6, 32))).created is None


def test_missing_application_tag_yields_none(mus_metadata_header: Callable[..., bytes]) -> None:
    assert parse(mus_metadata_header(app=b"")).created is None


def test_stamp_is_all_or_nothing_never_partial(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    # A bad date must not leave a stamp carrying only the tags.
    assert parse(mus_metadata_header(created=(0, 0, 0))).created is None


def test_truncated_header_yields_no_stamps_and_does_not_raise(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_metadata_header(size=0x60))
    assert detail.created is None
    assert detail.modified is None
    assert detail.year == 2011


def test_empty_header_does_not_raise() -> None:
    detail = parse(b"")
    assert detail.created is None and detail.modified is None and detail.year is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/version/test_mus_stamps.py -v`
Expected: FAIL — `ImportError: cannot import name 'MUS_METADATA_SIZE'`

- [ ] **Step 4: Add the types**

In `src/finale_file_parser/version/models.py`, add `MusStamp` and extend `MusDetail`. The new fields **must** have `None` defaults:

```python
@dataclass(frozen=True)
class MusStamp:
    """One provenance stamp from a .mus header: when, by what, on which platform."""

    year: int
    month: int
    day: int
    application: str
    """Observed: "FIN"."""

    platform: str
    """Observed: "MAC" or "WIN". Each stamp carries its own — do not assume both agree."""


@dataclass(frozen=True)
class MusDetail:
    """Version evidence from a legacy .mus header."""

    banner: str
    """The copyright banner, cut at the first NUL and decoded verbatim."""

    year: int | None
    """Marketing year parsed from the banner, or None if it did not match."""

    created: MusStamp | None = None
    modified: MusStamp | None = None
    """Mirrors MusxDetail's created/modified pair, so the same provenance
    question can be asked of either format."""
```

- [ ] **Step 5: Parse the stamps**

In `src/finale_file_parser/version/mus.py`, add the constants and parsing, and populate the new fields. Keep the existing banner logic exactly as it is.

```python
MUS_METADATA_SIZE = 0xA0
"""Bytes of header needed to reach both provenance stamps (they end at 0x9D)."""

_CREATED = (0x66, 0x70, 0x74)
_MODIFIED = (0x8C, 0x96, 0x9A)
"""(date, application tag, platform tag) offsets. Validated across all 238
corpus files; see the design spec."""

_MIN_YEAR, _MAX_YEAR = 1980, 2030


def parse(header: bytes) -> MusDetail:
    """... (keep the existing docstring, and add:)

    Provenance stamps are all-or-nothing: a stamp with an implausible date or
    an empty application tag is None rather than partially filled, because a
    caller cannot tell which half of a partial stamp to trust.
    """
    field = header[BANNER_OFFSET : BANNER_OFFSET + BANNER_FIELD_SIZE]
    banner = field.split(b"\x00", 1)[0].decode("latin-1")
    match = _BANNER_YEAR.match(banner)
    return MusDetail(
        banner=banner,
        year=int(match.group(1)) if match else None,
        created=_stamp(header, *_CREATED),
        modified=_stamp(header, *_MODIFIED),
    )


def _stamp(header: bytes, date_off: int, app_off: int, plat_off: int) -> MusStamp | None:
    """Return the stamp at these offsets, or None if it is absent or implausible."""
    date = header[date_off : date_off + 3]
    if len(date) < 3:
        return None
    year, month, day = 1900 + date[0], date[1], date[2]
    if not (_MIN_YEAR <= year <= _MAX_YEAR and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    application = _tag(header, app_off)
    if not application:
        return None
    return MusStamp(
        year=year,
        month=month,
        day=day,
        application=application,
        platform=_tag(header, plat_off),
    )


def _tag(header: bytes, offset: int, limit: int = 8) -> str:
    """Read a NUL-terminated ASCII tag, bounded by `limit` bytes."""
    return header[offset : offset + limit].split(b"\x00", 1)[0].decode("latin-1")
```

Add `MusStamp` to the imports from `models`.

- [ ] **Step 6: Widen the header read**

In `src/finale_file_parser/version/detect.py`, read enough bytes to reach the stamps. `classify` inspects only the leading magic, so a longer buffer is harmless.

```python
from finale_file_parser.version.mus import MUS_METADATA_SIZE

...
        header = handle.read(max(HEADER_SIZE, MUS_METADATA_SIZE))
```

Leave `HEADER_SIZE` and its invariant test alone — it still means "the banner geometry".

- [ ] **Step 7: Export `MusStamp`**

Add `MusStamp` to the imports and `__all__` in `src/finale_file_parser/__init__.py`, and to `EXPECTED_PUBLIC_NAMES` in `tests/test_public_api.py`.

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/version -v`
Expected: PASS — the 10 new tests plus every pre-existing version test, **unmodified**.

Confirm with `git diff --stat tests/` that no existing test file shows deletions.

- [ ] **Step 9: Mutation-verify the parsing rules**

For each rule, make the edit, run the named test, confirm it FAILS, then restore exactly.

| Mutation in `version/mus.py` | Test that must fail |
|---|---|
| Drop the year range check | `test_implausible_year_yields_none` |
| Drop the month range check | `test_implausible_month_yields_none_for_that_stamp_only` |
| Drop the day range check | `test_implausible_day_yields_none` |
| Drop the empty-application check | `test_missing_application_tag_yields_none` |
| Drop the `len(date) < 3` guard | `test_truncated_header_yields_no_stamps_and_does_not_raise` |
| Swap `_CREATED` and `_MODIFIED` | `test_parses_both_stamps` |

Record every result in your report. A mutation that does not cause a failure means the test is vacuous — fix the test before proceeding.

- [ ] **Step 10: Run the gate and commit**

Run: `make check` — expected clean.

```bash
git add src/finale_file_parser tests/version/test_mus_stamps.py tests/test_public_api.py
git commit -m "feat: parse created and modified provenance stamps from .mus headers"
```

---

### Task 2: Regenerate the `.mus` fixtures at the wider header

**Files:**
- Modify: `scripts/build_version_fixtures.py`
- Modify: `tests/fixtures/version/*.bin` and `MANIFEST.toml` (regenerated)
- Modify: `tests/version/test_fixtures.py`

**Interfaces:**
- Consumes: `MUS_METADATA_SIZE` from `version/mus.py`; `detect_version`.
- Produces: `.bin` fixtures of `MUS_METADATA_SIZE` bytes, with `MANIFEST.toml` gaining the expected stamp values per fixture.

The existing `.mus` fixtures are `0x60` bytes and stop short of the stamps, so they cannot exercise any of Task 1. Regenerate them at `MUS_METADATA_SIZE`.

**Content rule, unchanged:** these fixtures carry magic, banner, and provenance stamps only. That is format metadata, not musical content. `.musx` fixtures are untouched by this task.

- [ ] **Step 1: Widen the generator's `.mus` slice**

In `scripts/build_version_fixtures.py`, replace the `HEADER_SIZE`-byte read for `.mus` fixtures with `MUS_METADATA_SIZE`, and record the stamps in each manifest entry. Add to the `[[fixture]]` block, for fixtures that have them:

```toml
created = { year = 2011, month = 10, day = 23, application = "FIN", platform = "MAC" }
modified = { year = 2012, month = 4, day = 1, application = "FIN", platform = "MAC" }
```

Omit a key entirely when that stamp is `None`.

- [ ] **Step 2: Regenerate and inspect**

Run: `uv run python scripts/build_version_fixtures.py`

Then confirm by direct inspection that every `.bin` is now `MUS_METADATA_SIZE` bytes and contains no printable text beyond the banner and the `FIN`/platform tags:

```bash
ls -l tests/fixtures/version/*.bin
python3 -c "
import pathlib, re
for p in sorted(pathlib.Path('tests/fixtures/version').glob('*.bin')):
    b = p.read_bytes()
    runs = [s.decode('latin-1') for s in re.findall(rb'[ -~]{4,}', b)]
    print(f'{p.name} {len(b)} bytes: {runs}')
"
```

Expected: 160 bytes each; the only printable runs are the Finale banner and the `FIN`/`MAC`/`WIN` tags. If anything else appears, stop and report.

- [ ] **Step 3: Extend the fixture tests**

Append to `tests/version/test_fixtures.py` a parametrised test asserting that each manifest entry's declared `created`/`modified` match what `detect_version` returns for that fixture, and that a fixture declaring no stamp yields `None`.

Note the existing weakness this shares with the rest of that file: the manifest is generated by calling the code under test, so it pins consistency, not correctness. Add one independent pin — assert as a literal that the fixture derived from a Finale 2011 file reports `application == "FIN"` and a platform in `{"MAC", "WIN"}`, values taken from the corpus survey rather than from the generator.

- [ ] **Step 4: Run tests, gate, and commit**

Run: `uv run pytest tests/version -v` then `make check`. Both clean. Confirm `git status` shows nothing under `corpus/` staged.

```bash
git add scripts/build_version_fixtures.py tests/fixtures/version tests/version/test_fixtures.py
git commit -m "test: widen .mus fixtures to cover the provenance stamps"
```

---

### Task 3: Corpus sweep assertions

**Files:**
- Modify: `tests/version/test_corpus_sweep.py`

**Interfaces:**
- Consumes: `detect_version`, `MusDetail`.
- Produces: nothing importable.

Skips when `corpus/` is absent, like the existing sweeps.

- [ ] **Step 1: Append the assertions**

Add tests asserting, across all 238 `.mus` files:

- every file yields both a `created` and a `modified` stamp (238/238)
- `(created.year, created.month, created.day) <= (modified.year, modified.month, modified.day)` for every file
- every stamp's `application` is `"FIN"`
- platform tallies are exactly **136 `MAC`** and **102 `WIN`**, asserted as literals
- every stamp year falls in 1998-2012 inclusive

Assert the file list is non-empty first, so nothing can pass vacuously on an empty glob.

If observed values disagree with these, **report it rather than adjusting the assertions** — they are pinned so a corpus change forces a deliberate update to both the test and the spec.

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/version/test_corpus_sweep.py -v` — expected all pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/version/test_corpus_sweep.py -v; mv /tmp/corpus-parked corpus`

Expected: all skipped, then restored. **Confirm `corpus/` is back and reports 639 files** — it is the user's data and is not in git.

- [ ] **Step 3: Commit**

```bash
git add tests/version/test_corpus_sweep.py
git commit -m "test: sweep .mus provenance stamps across the corpus"
```

---

### Task 4: Update project documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`

**Interfaces:** none. Documentation only; change no code.

- [ ] **Step 1: Correct and extend ARCHITECTURE.md**

In the `.mus` format facts:

- **Correct the existing claim that platform is `.musx`-only.** It is recoverable from `.mus` too: `MAC` in 136 corpus files, `WIN` in 102.
- Add the stamp layout: created (date `0x66`, app `0x70`, platform `0x74`) and modified (date `0x8C`, app `0x96`, platform `0x9A`); date is `[year - 1900, month, day]`; present in 238/238 files with `created <= modified` in all of them.
- Record the **Mac-only plist trailer**: 89 of 136 `MAC` files, 0 of 102 `WIN`, in the last 1-3% of the file (938-1694 bytes), apparently appended OS metadata. Not parsed.
- Record the **disproved hypothesis**: `.mus` does *not* demonstrably share `.musx`'s record-type numbering. Scanning all 238 files for those ids as aligned LE `u16` gave occurrence rates close to the chance baseline. State it as a negative result so it is not re-derived.
- Record that **`.mus` has no member table** — there is no container abstraction, unlike `.musx`.

- [ ] **Step 2: Rescope the roadmap item**

In `docs/ROADMAP.md`, replace "Legacy `.mus` reader behind the same public API" with an accurate pair:

```markdown
- [x] `.mus` header provenance stamps (created/modified with date, application, platform).
- [ ] `.mus` internal record pools — open research. A `.mus` file has no member table, so there is
      no container abstraction to mirror from `.musx`; the pools must be located empirically.
```

- [ ] **Step 3: Close two decisions in DECISIONS.md**

```markdown
## 2026-07-22 — DECIDED: both `.mus` and `.musx` are in scope

Settled by what shipped: `detect_version` handles both, `.mus` banner parsing and provenance stamps
are done, and `.musx` has a full container reader. Reason: the corpus is 238 `.mus` and 401 `.musx`
— dropping either would abandon a third of real files.

## 2026-07-22 — DECIDED: use community reverse-engineering as reference, not as source

Published community documentation (e.g. the MIT-licensed EnigmaXML documentation) may be read as a
reference for what the format is; implementations are written independently rather than ported.
Reason: keeps provenance simple while not re-deriving what is already public. Licenses of known
sources are recorded in `docs/REFERENCES.md`.
```

Remove the corresponding OPEN bullets.

- [ ] **Step 4: Run the gate and commit**

Run: `make check` — expected clean (documentation only, but confirm).

```bash
git add docs
git commit -m "docs: record .mus provenance stamps and close two open decisions"
```

---

## Completion

After Task 4, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed; that `MusDetail`'s new fields default to `None` so existing
tests passed unmodified; the mutation results for all six parsing rules; that the corpus sweep ran
locally against 238 `.mus` files and skips in CI; that fixtures carry only magic, banner, and
provenance stamps; and that the roadmap item was rescoped because `.mus` has no container.
