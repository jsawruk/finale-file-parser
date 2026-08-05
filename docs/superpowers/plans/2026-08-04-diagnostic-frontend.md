# Diagnostic Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-contained HTML report showing what the parser saw in one `.mus`/`.musx` document, including how far it got when it failed.

**Architecture:** A renderer-agnostic `Inspection` dataclass built by running the existing public readers through a guarded "stage ladder", then rendered to one HTML file with embedded JSON. The model calls existing readers only — it never parses anything itself.

**Tech Stack:** Python 3.12+, stdlib only (`dataclasses`, `base64`, `json`, `hashlib`, `html`). No new runtime dependencies. Inline vanilla JS/CSS in the generated report.

## Global Constraints

- **No new runtime dependencies.** The project depends on `defusedxml` and nothing else. Do not add a web framework, template engine, or JS toolchain.
- Python `>=3.12`. Toolchain is `uv` · `ruff` · `mypy --strict` · `pytest`, run via `make`. Never ad-hoc.
- Ruff line length is **100**.
- **The model reimplements nothing.** `model.py` may only call public readers and record what they returned or raised.
- **Report generation never fails.** A section that cannot be built records its error; the file still writes.
- Embedded JSON budget: **16 MB**. Truncation order when exceeded: `raw` first, then `records`. Score and document summaries are never truncated.
- Record-field walking nests at most **8 levels**.
- Bytes are embedded **base64**, never hex. The renderer converts on demand.
- Generated HTML has **no external assets** — no CDN, no framework, no build step.
- Corpus tests **report counts only** — never a corpus filename, title, or record value. (Existing project guardrail; see any `*_corpus_sweep.py`.)
- Error text stored in the report must not contain absolute paths. Reader messages embed the path; strip to the file name.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/finale_file_parser/inspect/__init__.py` | Public surface: `inspect_document`, `render_html`, `Inspection`, `Stage` |
| `src/finale_file_parser/inspect/ladder.py` | `Stage`, statuses, and the guarded `Ladder` runner. No knowledge of Finale. |
| `src/finale_file_parser/inspect/model.py` | `Inspection`, `inspect_document(path)`. Builds both family ladders and the depth data. |
| `src/finale_file_parser/inspect/summary.py` | Pure summarisers: `Score` → score depth, `EnigmaDocument` → document depth. |
| `src/finale_file_parser/inspect/html.py` | `render_html(Inspection) -> str`. Embedding, escaping, panes. |
| `src/finale_file_parser/cli.py` | Add `--report PATH` to the existing `inspect` command. |
| `tests/inspect/test_ladder.py` | Ladder primitives |
| `tests/inspect/test_model.py` | Ladder shape per family, bounds, path stripping |
| `tests/inspect/test_summary.py` | Summarisers |
| `tests/inspect/test_html.py` | Escaping, well-formedness, embedded JSON |
| `tests/inspect/test_inspect_corpus_sweep.py` | Every corpus document inspects; agreement with existing sweeps |

---

### Task 1: Stage ladder primitives

The runner that turns an exception into data, and distinguishes a reader that *refused* a file from one that *crashed* on it.

**Files:**
- Create: `src/finale_file_parser/inspect/__init__.py`
- Create: `src/finale_file_parser/inspect/ladder.py`
- Test: `tests/inspect/test_ladder.py`

**Interfaces:**
- Consumes: `finale_file_parser.errors.FinaleFileError`
- Produces:
  - `OK = "ok"`, `REFUSED = "refused"`, `CRASHED = "crashed"`, `SKIPPED = "skipped"`
  - `Stage(name: str, status: str, detail: dict[str, str], error: str | None)`
  - `Ladder()` with `.stages: list[Stage]` and
    `run(name: str, call: Callable[[], T], detail: Callable[[T], dict[str, str]] | None = None) -> T | None`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the stage ladder."""

from __future__ import annotations

import pytest

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.inspect.ladder import CRASHED, OK, REFUSED, SKIPPED, Ladder


def test_a_stage_that_succeeds_records_its_detail() -> None:
    ladder = Ladder()
    value = ladder.run("read", lambda: 7, lambda v: {"count": str(v)})
    assert value == 7
    assert [(s.name, s.status) for s in ladder.stages] == [("read", OK)]
    assert ladder.stages[0].detail == {"count": "7"}


def test_a_reader_that_refuses_is_recorded_as_refused() -> None:
    """A FinaleFileError means the reader deliberately declined the file."""
    ladder = Ladder()

    def refuse() -> int:
        raise FinaleFileError("no frame holds; the document carries no music")

    assert ladder.run("read", refuse) is None
    assert ladder.stages[0].status == REFUSED
    assert "no frame holds" in (ladder.stages[0].error or "")


def test_any_other_exception_is_recorded_as_a_crash() -> None:
    """Not a bad file -- a reader bug, and the report must say which."""
    ladder = Ladder()

    def crash() -> int:
        raise IndexError("index out of range")

    assert ladder.run("read", crash) is None
    assert ladder.stages[0].status == CRASHED
    assert "IndexError" in (ladder.stages[0].error or "")


def test_stages_after_a_failure_are_skipped_not_attempted() -> None:
    """The ladder stops. A later stage must not run against a value that was
    never produced, and must not look like it passed."""
    ladder = Ladder()
    ladder.run("first", lambda: (_ for _ in ()).throw(FinaleFileError("nope")))
    ran = []
    ladder.run("second", lambda: ran.append(1))
    assert ran == []
    assert [s.status for s in ladder.stages] == [REFUSED, SKIPPED]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inspect/test_ladder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.inspect'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/inspect/__init__.py`:

```python
"""Inspecting one document: what the parser saw, and how far it got."""

from __future__ import annotations

from finale_file_parser.inspect.ladder import Stage

__all__ = ["Stage"]
```

Create `src/finale_file_parser/inspect/ladder.py`:

```python
"""Running a pipeline stage so that failure becomes data rather than an exception.

The tool exists for documents that do not work, so a stage that fails is the
normal path. Two failures are distinguished, because the difference is the most
useful thing a report can say:

**Refused** -- a `FinaleFileError`. The reader deliberately declined, and its
message already explains why.

**Crashed** -- anything else. That is a reader *bug* rather than a bad file, and
naming it as such is what makes this a bug-finder as well as a viewer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from finale_file_parser.errors import FinaleFileError

__all__ = ["CRASHED", "OK", "REFUSED", "SKIPPED", "Ladder", "Stage"]

OK = "ok"
REFUSED = "refused"
CRASHED = "crashed"
SKIPPED = "skipped"
"""Not attempted, because an earlier stage stopped the ladder."""

T = TypeVar("T")


@dataclass(frozen=True)
class Stage:
    """One rung: what was tried, how it went, and what it produced."""

    name: str
    status: str
    detail: dict[str, str] = field(default_factory=dict)
    error: str | None = None


class Ladder:
    """Runs stages in order and stops at the first failure.

    Stopping matters: a later stage given a value an earlier one never produced
    would either crash for the wrong reason or, worse, look like it passed.
    """

    def __init__(self) -> None:
        self.stages: list[Stage] = []
        self._stopped = False

    def run(
        self,
        name: str,
        call: Callable[[], T],
        detail: Callable[[T], dict[str, str]] | None = None,
    ) -> T | None:
        if self._stopped:
            self.stages.append(Stage(name, SKIPPED))
            return None
        try:
            value = call()
        except FinaleFileError as error:
            self._stopped = True
            self.stages.append(Stage(name, REFUSED, error=str(error)))
            return None
        except Exception as error:  # noqa: BLE001 - a reader bug is a finding, not a crash
            self._stopped = True
            self.stages.append(
                Stage(name, CRASHED, error=f"{type(error).__name__}: {error}")
            )
            return None
        self.stages.append(Stage(name, OK, detail(value) if detail else {}))
        return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/inspect/test_ladder.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/inspect/ tests/inspect/test_ladder.py
git commit -m "feat: add the stage ladder that turns a reader failure into data"
```

---

### Task 2: Summarisers for the score and document depths

Pure functions over already-built objects. Separated from `model.py` so they can be tested without touching a file.

**Files:**
- Create: `src/finale_file_parser/inspect/summary.py`
- Test: `tests/inspect/test_summary.py`

**Interfaces:**
- Consumes: `finale_file_parser.ir.Score`, `finale_file_parser.enigma.document.EnigmaDocument`
- Produces:
  - `summarise_score(score: Score) -> dict[str, object]`
  - `summarise_document(document: EnigmaDocument) -> dict[str, object]`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the score and document summarisers."""

from __future__ import annotations

from fractions import Fraction

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
from finale_file_parser.inspect.summary import summarise_document, summarise_score
from finale_file_parser.ir import Event, Measure, Part, Pitch, Score, TimeSignature, Voice


def _score() -> Score:
    event = Event(
        duration=Fraction(1, 4),
        written_duration=Fraction(1, 4),
        pitches=(Pitch("C", 4, 0),),
    )
    measure = Measure(
        number=1,
        voices=(Voice(number=1, events=(event,)),),
        time=TimeSignature(beats=4, beat_type=4),
        clef_sign="G",
    )
    return Score(parts=(Part(id="P1", name="Flute", measures=(measure,)),))


def test_score_summary_carries_per_measure_shape() -> None:
    """Per measure, not just totals: a measure that came out empty is the thing
    a reader is looking for, and a total hides it."""
    summary = summarise_score(_score())
    assert summary["parts"] == [
        {
            "id": "P1",
            "name": "Flute",
            "measures": [
                {
                    "number": 1,
                    "time": "4/4",
                    "clef": "G",
                    "key": None,
                    "events": 1,
                    "pitches": 1,
                }
            ],
        }
    ]


def test_score_summary_totals_agree_with_the_parts() -> None:
    summary = summarise_score(_score())
    assert summary["totals"] == {"parts": 1, "measures": 1, "events": 1, "pitches": 1}


def _document(*records: Record) -> EnigmaDocument:
    empty: tuple[Record, ...] = ()
    return EnigmaDocument(
        version="test",
        header=Pool(records=empty),
        mappings=Pool(records=empty),
        options=OptionsPool(records=empty),
        others=OthersPool(records=records),
        details=DetailsPool(records=empty),
        entries=EntriesPool(records=empty),
        texts=TextsPool(records=empty),
    )


def test_document_summary_counts_records_by_pool_and_tag() -> None:
    document = _document(
        Record(tag="measSpec", attrs={"cmper": "1"}, text="", fields={}),
        Record(tag="measSpec", attrs={"cmper": "2"}, text="", fields={}),
        Record(tag="frameSpec", attrs={"cmper": "1"}, text="", fields={}),
    )
    summary = summarise_document(document)
    assert summary["pools"]["others"] == {"measSpec": 2, "frameSpec": 1}


def test_document_summary_names_the_untranslated_gaps() -> None:
    """A .mus is read by reverse engineering, so what is *not* carried is part of
    the answer."""
    summary = summarise_document(_document())
    assert isinstance(summary["untranslated"], list)
    assert summary["untranslated"], "UNTRANSLATED must be surfaced"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inspect/test_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.inspect.summary'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/inspect/summary.py`:

```python
"""Turning built objects into the report's two upper depths.

Pure functions over a `Score` and an `EnigmaDocument`, so they can be tested
without opening a file, and so a later renderer (a server, a terminal UI) gets
them unchanged.
"""

from __future__ import annotations

import collections

from finale_file_parser.enigma.document import EnigmaDocument
from finale_file_parser.enigma.mus_document import UNTRANSLATED
from finale_file_parser.ir import Measure, Score

__all__ = ["summarise_document", "summarise_score"]


def _measure(measure: Measure) -> dict[str, object]:
    events = [event for voice in measure.voices for event in voice.events]
    time = f"{measure.time.beats}/{measure.time.beat_type}" if measure.time else None
    return {
        "number": measure.number,
        "time": time,
        "clef": measure.clef_sign,
        "key": measure.key_fifths,
        "events": len(events),
        "pitches": sum(len(event.pitches) for event in events),
    }


def summarise_score(score: Score) -> dict[str, object]:
    """Per part, per measure -- not only totals.

    A measure that came out empty is exactly what someone diagnosing a bad
    conversion is looking for, and a total hides it.
    """
    parts = [
        {
            "id": part.id,
            "name": part.name,
            "measures": [_measure(measure) for measure in part.measures],
        }
        for part in score.parts
    ]
    measures = [m for part in parts for m in part["measures"]]  # type: ignore[index]
    return {
        "parts": parts,
        "totals": {
            "parts": len(parts),
            "measures": len(measures),
            "events": sum(int(m["events"]) for m in measures),
            "pitches": sum(int(m["pitches"]) for m in measures),
        },
    }


_POOLS = ("header", "mappings", "options", "others", "details", "entries", "texts")


def summarise_document(document: EnigmaDocument) -> dict[str, object]:
    """Record counts by pool and tag, plus what this reader does not carry."""
    pools: dict[str, dict[str, int]] = {}
    for name in _POOLS:
        counts: collections.Counter[str] = collections.Counter()
        for record in getattr(document, name).records:
            counts[record.tag] += 1
        pools[name] = dict(counts)
    return {
        "version": document.version,
        "pools": pools,
        "untranslated": list(UNTRANSLATED),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/inspect/test_summary.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/inspect/summary.py tests/inspect/test_summary.py
git commit -m "feat: summarise a score and document for the report's upper depths"
```

---

### Task 3: The `.mus` ladder and `Inspection`

**Files:**
- Create: `src/finale_file_parser/inspect/model.py`
- Modify: `src/finale_file_parser/inspect/__init__.py`
- Test: `tests/inspect/test_model.py`

**Interfaces:**
- Consumes: `Ladder`, `Stage`, `summarise_score`, `summarise_document`
- Produces:
  - `Inspection(file: dict[str, str], stages: list[Stage], score: dict | None, document: dict | None, records: dict, raw: dict, notes: list[str])`
  - `inspect_document(path: str | os.PathLike[str]) -> Inspection`
  - `MAX_JSON_BYTES = 16 * 1024 * 1024`, `MAX_FIELD_DEPTH = 8`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the inspection model.

The readers are stubbed, so these cover the ladder's shape rather than the
parser's behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.errors import FinaleFileError
from finale_file_parser.inspect import model
from finale_file_parser.inspect.ladder import OK, REFUSED, SKIPPED


def _file(tmp_path: Path) -> Path:
    path = tmp_path / "score.mus"
    path.write_bytes(b"not really a mus file")
    return path


def test_the_ladder_stops_where_the_reader_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: the report says how far it got."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())

    def refuse(p: object) -> object:
        raise FinaleFileError(f"{p} has no frame holds")

    monkeypatch.setattr(model, "read_mus_pools", refuse)
    inspection = model.inspect_document(path)
    names = [(s.name, s.status) for s in inspection.stages]
    assert names[0] == ("detect version", OK)
    assert names[1][1] == REFUSED
    assert {status for _, status in names[2:]} == {SKIPPED}


def test_the_error_does_not_carry_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A report is meant to be sendable. Reader messages embed the path."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())

    def refuse(p: object) -> object:
        raise FinaleFileError(f"{p} has no frame holds")

    monkeypatch.setattr(model, "read_mus_pools", refuse)
    inspection = model.inspect_document(path)
    error = next(s.error for s in inspection.stages if s.error)
    assert str(tmp_path) not in error
    assert "score.mus" in error


def test_file_identity_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """So two people can confirm they are looking at the same file."""
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())
    monkeypatch.setattr(
        model, "read_mus_pools", lambda p: (_ for _ in ()).throw(FinaleFileError("x"))
    )
    inspection = model.inspect_document(path)
    assert inspection.file["name"] == "score.mus"
    assert inspection.file["size"] == str(len(b"not really a mus file"))
    assert len(inspection.file["sha256"]) == 64


def test_a_reader_bug_is_reported_as_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _file(tmp_path)
    monkeypatch.setattr(model, "detect_version", lambda p: _FakeVersion())

    def crash(p: object) -> object:
        raise IndexError("index out of range")

    monkeypatch.setattr(model, "read_mus_pools", crash)
    inspection = model.inspect_document(path)
    stage = next(s for s in inspection.stages if s.error)
    assert stage.status == "crashed"
    assert "IndexError" in (stage.error or "")


def test_inspecting_a_file_that_is_not_finale_at_all_still_returns(
    tmp_path: Path,
) -> None:
    """Report generation never fails."""
    path = tmp_path / "notes.mus"
    path.write_bytes(b"\x00\x01\x02")
    inspection = model.inspect_document(path)
    assert inspection.stages
    assert inspection.score is None


class _FakeVersion:
    class _Family:
        value = "mus"

    family = _Family()
    label = "Finale 2005"
    confidence = None
    detail = None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inspect/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.inspect.model'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/inspect/model.py`:

```python
"""Building an `Inspection`: what the parser saw, and how far it got.

**This module reimplements nothing.** It calls the public readers and records
what each returned or raised. Parsing logic of its own would be a second
implementation that could disagree with the real one, and a diagnostic tool that
lies about the parser is worse than no tool.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_payload import read_mus_pools
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.inspect.ladder import Ladder, Stage
from finale_file_parser.inspect.summary import summarise_document, summarise_score
from finale_file_parser.version.detect import detect_version

__all__ = ["MAX_FIELD_DEPTH", "MAX_JSON_BYTES", "Inspection", "inspect_document"]

MAX_JSON_BYTES = 16 * 1024 * 1024
"""Budget for the embedded JSON. The largest corpus payload is ~500 KB, so no
real document approaches this; it exists to stop a pathological file."""

MAX_FIELD_DEPTH = 8
"""A record's fields may contain records. Bound the walk."""


@dataclass
class Inspection:
    """Everything the report shows about one document."""

    file: dict[str, str]
    stages: list[Stage] = field(default_factory=list)
    score: dict[str, object] | None = None
    document: dict[str, object] | None = None
    records: dict[str, object] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    """Anything the report had to leave out, and why."""


def _identity(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    return {
        "name": path.name,
        "size": str(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _no_paths(text: str, path: Path) -> str:
    """Reader messages embed the path. A report is meant to be sendable."""
    return text.replace(str(path), path.name).replace(str(path.parent) + os.sep, "")


def inspect_document(path: str | os.PathLike[str]) -> Inspection:
    """Run the pipeline for `path`, recording how far it got."""
    target = Path(path)
    inspection = Inspection(file=_identity(target))
    ladder = Ladder()

    version = ladder.run(
        "detect version",
        lambda: detect_version(target),
        lambda v: {"family": str(v.family.value), "label": v.label},
    )
    family = str(version.family.value) if version is not None else ""

    if family == "musx":
        _musx_stages(ladder, target, inspection)
    else:
        _mus_stages(ladder, target, inspection)

    inspection.stages = [
        Stage(s.name, s.status, s.detail, _no_paths(s.error, target) if s.error else None)
        for s in ladder.stages
    ]
    return inspection


def _mus_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    ladder.run(
        "decode payload",
        lambda: read_mus_pools(target),
        lambda pools: {"pools": str(len(pools)), "byte order": pools[0].byte_order},
    )
    document = ladder.run("build document", lambda: read_mus_document(target))
    _finish(ladder, document, inspection)


def _musx_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    xml = ladder.run(
        "extract score.dat", lambda: score_xml(target), lambda b: {"bytes": str(len(b))}
    )
    document = ladder.run("parse EnigmaXML", lambda: parse_enigma(xml or b""))
    _finish(ladder, document, inspection)


def _finish(ladder: Ladder, document: object, inspection: Inspection) -> None:
    if document is not None:
        inspection.document = summarise_document(document)  # type: ignore[arg-type]
    score = ladder.run("build score", lambda: build_score(document))  # type: ignore[arg-type]
    if score is not None:
        inspection.score = summarise_score(score)
    ladder.run(
        "export MusicXML",
        lambda: to_musicxml(score),  # type: ignore[arg-type]
        lambda data: {"bytes": str(len(data))},
    )
```

Modify `src/finale_file_parser/inspect/__init__.py`:

```python
"""Inspecting one document: what the parser saw, and how far it got."""

from __future__ import annotations

from finale_file_parser.inspect.ladder import Stage
from finale_file_parser.inspect.model import Inspection, inspect_document

__all__ = ["Inspection", "Stage", "inspect_document"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/inspect/test_model.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/inspect/ tests/inspect/test_model.py
git commit -m "feat: build an Inspection by running the pipeline as a stage ladder"
```

---

### Task 4: Record and raw-byte depths, with the budget enforced

**Files:**
- Modify: `src/finale_file_parser/inspect/model.py`
- Test: `tests/inspect/test_model.py` (append)

**Interfaces:**
- Consumes: `Inspection`, `MAX_JSON_BYTES`, `MAX_FIELD_DEPTH`
- Produces: `Inspection.records` shaped `{pool: {tag: [record, ...]}}` where a record is
  `{"key": str, "fields": dict[str, object], "offset": int | None, "length": int | None}`;
  `Inspection.raw` shaped `{pool_name: base64_str}`; `Inspection.notes` naming anything dropped.

- [ ] **Step 1: Write the failing test**

```python
def test_record_fields_stop_nesting_at_the_cap() -> None:
    """A record's fields may contain records. Hostile input must not recurse
    without end."""
    from finale_file_parser.enigma.document import Record
    from finale_file_parser.inspect.model import MAX_FIELD_DEPTH, walk_fields

    deepest = Record(tag="leaf", attrs={}, text="", fields={})
    node = deepest
    for _ in range(MAX_FIELD_DEPTH + 5):
        node = Record(tag="branch", attrs={}, text="", fields={"child": node})

    walked = walk_fields(node.fields, depth=0)
    depth = 0
    cursor: object = walked
    while isinstance(cursor, dict) and "child" in cursor:
        cursor = cursor["child"]
        depth += 1
    assert depth <= MAX_FIELD_DEPTH


def test_raw_bytes_are_base64_not_hex() -> None:
    """Base64 is 4/3 of the payload where hex is 2x."""
    import base64

    from finale_file_parser.inspect.model import encode_raw

    assert base64.b64decode(encode_raw(b"\x00\xff\x10")) == b"\x00\xff\x10"


def test_the_budget_drops_raw_before_records() -> None:
    """Score and document summaries are never truncated; raw goes first."""
    from finale_file_parser.inspect.model import Inspection, apply_budget

    inspection = Inspection(file={"name": "x", "size": "0", "sha256": ""})
    inspection.score = {"totals": {"parts": 1}}
    inspection.raw = {"others": "A" * 2000}
    inspection.records = {"others": {"measSpec": [{"key": "1"}]}}

    apply_budget(inspection, limit=500)
    assert inspection.raw == {}
    assert inspection.score is not None
    assert any("raw" in note for note in inspection.notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inspect/test_model.py -v -k "nesting or base64 or budget"`
Expected: FAIL — `ImportError: cannot import name 'walk_fields'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/finale_file_parser/inspect/model.py`:

```python
import base64
import json

from finale_file_parser.enigma.document import Record


def encode_raw(data: bytes) -> str:
    """Base64, not hex: 4/3 of the payload rather than 2x, and the renderer
    converts to hex on demand for whichever region is in view."""
    return base64.b64encode(data).decode("ascii")


def walk_fields(fields: object, depth: int) -> object:
    """A record's fields, flattened for JSON, bounded at `MAX_FIELD_DEPTH`."""
    if depth >= MAX_FIELD_DEPTH:
        return "<nesting cap reached>"
    if isinstance(fields, Record):
        return walk_fields(fields.fields, depth + 1)
    if isinstance(fields, dict):
        return {str(k): walk_fields(v, depth + 1) for k, v in fields.items()}
    if isinstance(fields, tuple):
        return [walk_fields(item, depth + 1) for item in fields]
    return str(fields)


def _weight(inspection: Inspection) -> int:
    return len(
        json.dumps(
            {
                "score": inspection.score,
                "document": inspection.document,
                "records": inspection.records,
                "raw": inspection.raw,
            }
        )
    )


def apply_budget(inspection: Inspection, limit: int = MAX_JSON_BYTES) -> None:
    """Drop `raw` first, then `records`, naming what went in `notes`.

    Score and document summaries are never dropped: they are small, and they are
    the part a reader needs most.
    """
    if _weight(inspection) <= limit:
        return
    if inspection.raw:
        inspection.raw = {}
        inspection.notes.append(
            f"raw bytes omitted: the report exceeded its {limit} byte budget"
        )
    if _weight(inspection) <= limit:
        return
    if inspection.records:
        inspection.records = {}
        inspection.notes.append(
            f"records omitted: the report exceeded its {limit} byte budget"
        )
```

Then call `apply_budget(inspection)` as the last line of `inspect_document` before `return inspection`, and populate `records`/`raw` inside `_mus_stages` from the pools the ladder already read.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/inspect/test_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/inspect/model.py tests/inspect/test_model.py
git commit -m "feat: add record and raw-byte depths with a bounded budget"
```

---

### Task 5: The HTML renderer

**Files:**
- Create: `src/finale_file_parser/inspect/html.py`
- Modify: `src/finale_file_parser/inspect/__init__.py`
- Test: `tests/inspect/test_html.py`

**Interfaces:**
- Consumes: `Inspection`
- Produces: `render_html(inspection: Inspection) -> str`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the HTML report renderer."""

from __future__ import annotations

import json
import re

from defusedxml import ElementTree as DET

from finale_file_parser.inspect.html import render_html
from finale_file_parser.inspect.ladder import OK, Stage
from finale_file_parser.inspect.model import Inspection


def _inspection(**kwargs: object) -> Inspection:
    base = Inspection(file={"name": "score.mus", "size": "10", "sha256": "ab"})
    base.stages = [Stage("detect version", OK, {"family": "mus"})]
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_a_title_containing_a_script_tag_cannot_break_out() -> None:
    """Document text goes into the page and the input is untrusted by
    definition. `</script>` inside the embedded JSON would end the block."""
    hostile = '</script><script>alert("x")</script>'
    html = render_html(_inspection(score={"parts": [{"id": "P1", "name": hostile}]}))
    assert "</script><script>alert" not in html
    assert "\\u003c/script" in html


def test_the_report_embeds_its_data_as_json() -> None:
    html = render_html(_inspection(score={"totals": {"parts": 3}}))
    match = re.search(r'<script id="inspection" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    assert payload["score"]["totals"]["parts"] == 3


def test_the_report_is_well_formed_markup() -> None:
    """Not a strict HTML requirement, but it catches unbalanced tags cheaply.

    The doctype is stripped first: defusedxml refuses a DTD by design, which is
    the whole reason to use it here."""
    html = render_html(_inspection())
    DET.fromstring(html[html.index("<html") :])


def test_the_report_names_the_stage_that_failed() -> None:
    inspection = _inspection()
    inspection.stages = [
        Stage("detect version", OK, {"family": "mus"}),
        Stage("build score", "refused", error="entry 39 placed by more than one frame"),
    ]
    html = render_html(inspection)
    assert "entry 39 placed by more than one frame" in html
    assert "build score" in html


def test_the_report_has_no_external_assets() -> None:
    """No CDN, no framework, no build step."""
    html = render_html(_inspection())
    assert "http://" not in html and "https://" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inspect/test_html.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.inspect.html'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/inspect/html.py`. Key points the implementer must honour:

- Serialise with `json.dumps(...)` then replace `</` with `<\\/` before embedding, so no document string can end the `<script>` block. The test above pins this.
- Escape every value interpolated into markup with `html.escape`.
- Emit `<!doctype html>` plus a single `<html>` tree that parses as XML (self-close void elements, quote all attributes).
- Inline `<style>` and `<script>`; no URLs anywhere.
- Four panes — score, document, records, bytes — driven from the embedded JSON, with the stage ladder always visible at the top and panes for stages that never ran shown as unavailable with the reason.

```python
"""Rendering an `Inspection` as one self-contained HTML file.

No server, no external assets, no build step: the report is a file, which is what
makes it archivable beside the converted output and sendable by someone whose
score cannot leave their machine.
"""

from __future__ import annotations

import html as html_escape
import json

from finale_file_parser.inspect.model import Inspection

__all__ = ["render_html"]


_STYLE = """
body { font: 14px/1.5 ui-monospace, monospace; margin: 2rem; max-width: 70rem; }
h1 { font-size: 1.2rem; margin-bottom: 0; }
.meta { color: #666; margin-top: 0.2rem; }
ol.ladder { list-style: none; padding: 0; }
ol.ladder li { padding: 0.3rem 0.6rem; border-left: 4px solid #ccc; margin: 0.2rem 0; }
li.ok { border-color: #2a7; }
li.refused { border-color: #c81; }
li.crashed { border-color: #c33; font-weight: bold; }
li.skipped { border-color: #ddd; color: #999; }
nav button { font: inherit; margin-right: 0.4rem; }
section { display: none; }
section.shown { display: block; }
table { border-collapse: collapse; }
td, th { border: 1px solid #ddd; padding: 0.15rem 0.5rem; text-align: left; }
.empty { color: #c33; }
"""

_SCRIPT = """
const data = JSON.parse(document.getElementById('inspection').textContent);
function show(name) {
  for (const s of document.querySelectorAll('section')) {
    s.className = (s.id === name) ? 'shown' : '';
  }
}
for (const b of document.querySelectorAll('nav button')) {
  b.addEventListener('click', () => show(b.dataset.pane));
}
function esc(t) { return String(t).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function renderScore() {
  const el = document.getElementById('score');
  if (!data.score) { el.innerHTML = '<p>No score was built.</p>'; return; }
  let out = '';
  for (const part of data.score.parts) {
    out += '<h2>' + esc(part.id) + ' &mdash; ' + esc(part.name) + '</h2><table>' +
           '<tr><th>measure</th><th>time</th><th>clef</th><th>key</th>' +
           '<th>events</th><th>pitches</th></tr>';
    for (const m of part.measures) {
      const cls = m.events === 0 ? ' class="empty"' : '';
      out += '<tr' + cls + '><td>' + m.number + '</td><td>' + esc(m.time ?? '') +
             '</td><td>' + esc(m.clef ?? '') + '</td><td>' + esc(m.key ?? '') +
             '</td><td>' + m.events + '</td><td>' + m.pitches + '</td></tr>';
    }
    out += '</table>';
  }
  el.innerHTML = out;
}
function renderJson(id, value) {
  document.getElementById(id).innerHTML =
    value ? '<pre>' + esc(JSON.stringify(value, null, 2)) + '</pre>'
          : '<p>Not available &mdash; the pipeline stopped before this stage.</p>';
}
function renderBytes() {
  const el = document.getElementById('bytes');
  const pools = Object.entries(data.raw || {});
  if (!pools.length) { el.innerHTML = '<p>No raw bytes were embedded.</p>'; return; }
  let out = '';
  for (const [name, b64] of pools) {
    const bin = atob(b64);
    let hex = '';
    for (let i = 0; i < Math.min(bin.length, 4096); i++) {
      hex += bin.charCodeAt(i).toString(16).padStart(2, '0') + (i % 16 === 15 ? '\n' : ' ');
    }
    out += '<h2>' + esc(name) + ' (' + bin.length + ' bytes)</h2><pre>' + esc(hex) + '</pre>';
  }
  el.innerHTML = out;
}
renderScore();
renderJson('document', data.document);
renderJson('records', data.records);
renderBytes();
show('score');
"""


def _embed(data: object) -> str:
    """JSON safe to place inside a <script> block in an XML-well-formed page.

    Document text reaches this -- titles, part names, lyrics -- and the input is
    untrusted. A `</script>` in a lyric would end the block and turn the rest of
    the document into markup; a bare `<` or `&` would break well-formedness.
    Escaping both as JSON unicode escapes fixes both at once and still parses as
    JSON on the other side.
    """
    return (
        json.dumps(data, default=str)
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )


def _ladder(inspection: Inspection) -> str:
    rows = []
    for stage in inspection.stages:
        detail = " ".join(f"{k}={v}" for k, v in stage.detail.items())
        text = html_escape.escape(stage.name)
        if detail:
            text += " <span>" + html_escape.escape(detail) + "</span>"
        if stage.error:
            text += " &mdash; " + html_escape.escape(stage.error)
        rows.append(f'<li class="{html_escape.escape(stage.status)}">{text}</li>')
    return "<ol class=\"ladder\">" + "".join(rows) + "</ol>"


def render_html(inspection: Inspection) -> str:
    """One self-contained page. No network, no build step, no external assets."""
    name = html_escape.escape(inspection.file.get("name", "document"))
    meta = html_escape.escape(
        f"{inspection.file.get('size', '?')} bytes · sha256 {inspection.file.get('sha256', '')}"
    )
    notes = "".join(f"<p>{html_escape.escape(n)}</p>" for n in inspection.notes)
    payload = _embed(
        {
            "file": inspection.file,
            "stages": [vars(s) for s in inspection.stages],
            "score": inspection.score,
            "document": inspection.document,
            "records": inspection.records,
            "raw": inspection.raw,
            "notes": inspection.notes,
        }
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8"/>'
        f"<title>{name} &mdash; inspection</title>"
        f"<style>{_STYLE}</style></head><body>"
        f"<h1>{name}</h1><p class=\"meta\">{meta}</p>"
        f"{_ladder(inspection)}{notes}"
        '<nav><button data-pane="score">score</button>'
        '<button data-pane="document">document</button>'
        '<button data-pane="records">records</button>'
        '<button data-pane="bytes">bytes</button></nav>'
        '<section id="score"></section><section id="document"></section>'
        '<section id="records"></section><section id="bytes"></section>'
        f'<script id="inspection" type="application/json">{payload}</script>'
        f"<script>{_SCRIPT}</script>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/inspect/test_html.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/inspect/html.py src/finale_file_parser/inspect/__init__.py tests/inspect/test_html.py
git commit -m "feat: render an Inspection as a self-contained HTML report"
```

---

### Task 6: Wire `--report` into the CLI

**Files:**
- Modify: `src/finale_file_parser/cli.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `inspect_document`, `render_html`
- Produces: `finale-parser inspect INPUT --report OUT.html`

- [ ] **Step 1: Write the failing test**

```python
def test_inspect_writes_a_report(tmp_path: Path, stub: None) -> None:
    """The report is the whole point of the flag; the terminal output stays."""
    source = touch(tmp_path / "a.mus")
    report = tmp_path / "out.html"
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_OK
    assert report.read_text().startswith("<!doctype html>")


def test_a_report_is_refused_rather_than_clobbered(tmp_path: Path, stub: None) -> None:
    """Same rule as convert: nothing is overwritten without being asked."""
    source = touch(tmp_path / "a.mus")
    report = tmp_path / "out.html"
    report.write_text("MINE")
    assert cli.main(["inspect", str(source), "--report", str(report)]) == cli.EXIT_USAGE
    assert report.read_text() == "MINE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v -k report`
Expected: FAIL — `unrecognized arguments: --report`

- [ ] **Step 3: Write minimal implementation**

In `_parser()`, add to the `inspect` subparser:

```python
    inspect.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write a self-contained HTML report instead of terminal output",
    )
    inspect.add_argument(
        "--force", action="store_true", help="overwrite an existing report"
    )
```

In `_inspect()`, before the existing loop:

```python
    if args.report is not None:
        if len(sources) != 1:
            print(f"{PROGRAM}: --report takes one file, not a directory", file=sys.stderr)
            return EXIT_USAGE
        if args.report.exists() and not args.force:
            print(
                f"{PROGRAM}: {args.report.name} exists; pass --force to overwrite",
                file=sys.stderr,
            )
            return EXIT_USAGE
        from finale_file_parser.inspect import inspect_document
        from finale_file_parser.inspect.html import render_html

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_html(inspect_document(sources[0])), encoding="utf-8")
        print(f"{sources[0]} -> {args.report}", file=out)  # type: ignore[call-overload]
        return EXIT_OK
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/cli.py tests/test_cli.py
git commit -m "feat: add finale-parser inspect --report"
```

---

### Task 7: Corpus sweep and agreement with the existing sweeps

The cross-check that keeps the report honest.

**Files:**
- Create: `tests/inspect/test_inspect_corpus_sweep.py`

**Interfaces:**
- Consumes: `inspect_document`, `render_html`, `corpus_files.corpus_paths`

- [ ] **Step 1: Write the failing test**

```python
"""Inspecting every corpus document, and agreeing with the sweeps that already
pin what builds.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.inspect import inspect_document
from finale_file_parser.inspect.html import render_html
from finale_file_parser.inspect.ladder import OK

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

DOCUMENTS_THAT_BUILD = 631
"""What the report thinks builds.

Deliberately the same number the `.mus` and `.musx` sweeps pin between them. This
asserts the two **agree**: the report must not develop its own opinion of what
builds, because two independent counts of one thing drift.
"""


def test_every_corpus_document_inspects_without_raising() -> None:
    """Report generation never fails -- including on the documents that do not
    build, which are the ones it exists for."""
    for path in corpus_paths(".mus") + corpus_paths(".musx"):
        inspection = inspect_document(path)
        assert inspection.stages, "a document produced no ladder at all"


def test_the_report_agrees_with_the_sweeps_about_what_builds() -> None:
    built = 0
    for path in corpus_paths(".mus") + corpus_paths(".musx"):
        stages = {stage.name: stage.status for stage in inspect_document(path).stages}
        built += stages.get("build score") == OK
    assert built == DOCUMENTS_THAT_BUILD


def test_no_corpus_document_crashes_a_reader() -> None:
    """A crash is a reader bug rather than a bad file. Zero today; pinned so the
    next one is a regression."""
    crashed = 0
    for path in corpus_paths(".mus") + corpus_paths(".musx"):
        crashed += any(s.status == "crashed" for s in inspect_document(path).stages)
    assert crashed == 0


def test_a_report_renders_for_a_document_that_does_not_build() -> None:
    """The tool is most informative when the file is most broken."""
    for path in corpus_paths(".mus"):
        inspection = inspect_document(path)
        if any(stage.status in {"refused", "crashed"} for stage in inspection.stages):
            assert render_html(inspection).startswith("<!doctype html>")
            return
    pytest.fail("no failing corpus document found to render")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/inspect/test_inspect_corpus_sweep.py -v`
Expected: FAIL on `DOCUMENTS_THAT_BUILD` if the ladder and the sweeps disagree — investigate rather than adjusting the number, since disagreement means one of them is wrong.

- [ ] **Step 3: Reconcile**

If the count differs, find which documents the report and the sweeps disagree about and fix the model. Only change `DOCUMENTS_THAT_BUILD` if the *sweeps'* pinned totals have themselves changed.

- [ ] **Step 4: Run the whole gate**

Run: `make check`
Expected: ruff clean, `mypy --strict` clean, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/inspect/test_inspect_corpus_sweep.py
git commit -m "test: pin that the report agrees with the sweeps about what builds"
```

---

### Task 8: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Add usage to the README**

Under the existing `inspect` example:

````markdown
```bash
finale-parser inspect score.mus --report score-report.html
```

Writes one self-contained HTML file showing what the parser saw: how far the
pipeline got, the score it built, the records it read, and the raw bytes. It is
most informative when the document does *not* convert — the report names the
stage that stopped and why, which is what to send when reporting a file that
will not parse.
````

- [ ] **Step 2: Update the roadmap**

Replace the "desktop frontend: hex viewer with decoded structure values" entry with a `[x]` noting it shipped as an HTML report, and leave "notation rendering" unchecked.

- [ ] **Step 3: Run the gate**

Run: `make check`

- [ ] **Step 4: Commit**

```bash
git add README.md docs/ROADMAP.md
git commit -m "docs: document the inspection report"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
| --- | --- |
| Stage ladder, failure as data | 1 |
| Refused vs crashed | 1, 7 |
| Score + document depths | 2 |
| `.mus` and `.musx` ladders | 3 |
| File identity, path stripping | 3 |
| Records + raw depths | 4 |
| 16 MB budget, truncation order | 4 |
| 8-level nesting cap | 4 |
| base64 not hex | 4 |
| Self-contained HTML, no external assets | 5 |
| `</script>` escaping | 5 |
| CLI `--report` | 6 |
| Corpus sweep, agreement with sweeps | 7 |
| Report generation never fails | 3, 7 |
| Documentation | 8 |

**Placeholders:** none. Task 5's `render_html` was initially described rather than written; it is now written out in full, since a step that says what to do without showing how is a plan failure. Its well-formedness test was also corrected — `defusedxml` refuses a DTD by design, so the doctype must be stripped before parsing, and the test as first drafted could not have passed.

**Type consistency:** `Inspection`, `Stage`, `Ladder.run`, `summarise_score`, `summarise_document`, `walk_fields`, `encode_raw`, `apply_budget`, `render_html`, `inspect_document` are named identically wherever they appear.
