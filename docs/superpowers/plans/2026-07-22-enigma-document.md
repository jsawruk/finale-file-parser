# EnigmaXML Document Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `parse_enigma(xml: bytes) -> EnigmaDocument` — a navigable model of a decoded EnigmaXML document that preserves every record.

**Architecture:** A pure `enigma/document.py` operating on `bytes`. A recursive `Record` (tag, attrs, fields) models any of the format's ~191 record types uniformly; one uniform `Pool` type holds each pool's records in document order, addressable by tag. Parsed with `defusedxml`. **No keyed lookup in this slice** — the survey showed no fixed key set is unique (see the spec's "Keying deferred").

**Design spec:** `docs/superpowers/specs/2026-07-22-enigma-document-design.md`. Read it first — note it was revised after the corpus survey to defer keyed lookup.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`.
- **XML parsed with `defusedxml`**, never stdlib `xml.etree.ElementTree`. Already the project's one runtime dependency; no new dependency.
- `parse_enigma` operates on `bytes` and is **pure** — must not import or call `score_xml`, `open_musx`, or anything in `container/`. Callers compose `parse_enigma(score_xml(path))`.
- **No corpus bytes in any committed fixture.** The decoded `texts` pool carries title/composer/copyright; every fixture is hand-written synthetic EnigmaXML.
- **`Record.attrs` holds ALL attributes verbatim** — this slice does not designate keys. **Nothing is dropped**: a `measSpec` with a score record and per-`part` variants sharing a cmper must all survive in the pool.
- **Field value rule.** Group a record's child elements by tag name:
  - no child elements, once → `str` (verbatim, possibly empty)
  - no child elements, N>1 → `tuple[str, ...]`
  - has child elements, once → `Record`
  - has child elements, N>1 → `tuple[Record, ...]`
  Verified across the corpus: no tag is scalar in one record and nested in another.
- Root must be `<finale>`, matched by *local* name (namespace `http://www.makemusic.com/2012/finale`), so a namespace change stays inspectable.
- Verify by mutation. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

---

### Task 1: `Record`, `Pool`, `parse_enigma`

**Files:**
- Create: `src/finale_file_parser/enigma/document.py`
- Modify: `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/__init__.py`, `tests/test_public_api.py`
- Test: `tests/enigma/test_document.py`

**Interfaces:**
- Consumes: `FinaleFileError` from `finale_file_parser.errors`.
- Produces: `Record` (frozen: `tag: str`, `attrs: Mapping[str, str]`, `fields: Mapping[str, str | tuple[str, ...] | Record | tuple[Record, ...]]`); `Pool` (frozen: `records: tuple[Record, ...]`, method `of_tag(tag) -> tuple[Record, ...]`); `EnigmaDocument` (`version: str` plus seven `Pool` attributes: `header`, `mappings`, `options`, `others`, `details`, `entries`, `texts`); `parse_enigma(xml: bytes) -> EnigmaDocument`; `MalformedEnigmaError`. All exported from `finale_file_parser.enigma` and the package root.

The whole slice is one module and one behaviour, so it is one task. `header`/`mappings` are ordinary `Pool`s that happen to hold a single record — no special-casing.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/test_document.py`:

```python
import pytest

from finale_file_parser.enigma.document import (
    EnigmaDocument,
    MalformedEnigmaError,
    Pool,
    Record,
    parse_enigma,
)
from finale_file_parser.errors import FinaleFileError

NS = "http://www.makemusic.com/2012/finale"


def _doc(body: str, *, version: str = "18.0", root: str = "finale") -> bytes:
    return f'<{root} version="{version}" xmlns="{NS}">{body}</{root}>'.encode()


FULL = _doc(
    """
    <header><headerData><wordOrder>1</wordOrder></headerData></header>
    <mappings><mapGroup minInclusive="17.0"/></mappings>
    <options><beamOptions><maxSlope>10</maxSlope></beamOptions></options>
    <others>
      <articDef cmper="1"><charMain>46</charMain></articDef>
      <measSpec cmper="1"/>
      <measSpec cmper="1" part="1" shared="true"/>
      <measSpec cmper="1" part="2" shared="true"/>
      <shapeData cmper="9"><data>1</data><data>2</data><data>3</data></shapeData>
    </others>
    <details><gfhold cmper1="1" cmper2="2"><val>x</val></gfhold></details>
    <entries>
      <entry entnum="1"><dura>1024</dura><note id="1"/><note id="2"/></entry>
    </entries>
    <texts><expression number="3"><text>PLACEHOLDER</text></expression></texts>
    """
)


def test_version() -> None:
    assert parse_enigma(FULL).version == "18.0"


def test_all_seven_pools_present() -> None:
    doc = parse_enigma(FULL)
    for pool in (doc.header, doc.mappings, doc.options, doc.others,
                 doc.details, doc.entries, doc.texts):
        assert isinstance(pool, Pool)
    assert doc.header.records[0].tag == "headerData"
    assert doc.mappings.records[0].tag == "mapGroup"


def test_records_preserved_in_document_order() -> None:
    tags = [r.tag for r in parse_enigma(FULL).others.records]
    assert tags == ["articDef", "measSpec", "measSpec", "measSpec", "shapeData"]


def test_of_tag_returns_all_matching_records_in_order() -> None:
    measspecs = parse_enigma(FULL).others.of_tag("measSpec")
    assert len(measspecs) == 3
    # the collision the survey found: score record + two per-part variants, all kept
    assert measspecs[0].attrs == {"cmper": "1"}
    assert measspecs[1].attrs == {"cmper": "1", "part": "1", "shared": "true"}
    assert measspecs[2].attrs == {"cmper": "1", "part": "2", "shared": "true"}


def test_of_tag_missing_returns_empty() -> None:
    assert parse_enigma(FULL).others.of_tag("nonesuch") == ()


def test_attrs_hold_all_attributes_verbatim() -> None:
    artic = parse_enigma(FULL).others.of_tag("articDef")[0]
    assert artic.attrs == {"cmper": "1"}
    assert artic.fields == {"charMain": "46"}


def test_scalar_field() -> None:
    entry = parse_enigma(FULL).entries.of_tag("entry")[0]
    assert entry.fields["dura"] == "1024"


def test_repeated_scalar_field_is_a_tuple() -> None:
    sd = parse_enigma(FULL).others.of_tag("shapeData")[0]
    assert sd.fields["data"] == ("1", "2", "3")


def test_repeated_nested_field_is_a_tuple_of_records() -> None:
    entry = parse_enigma(FULL).entries.of_tag("entry")[0]
    notes = entry.fields["note"]
    assert isinstance(notes, tuple) and len(notes) == 2
    assert all(isinstance(n, Record) for n in notes)


def test_single_nested_field_is_a_record() -> None:
    doc = parse_enigma(_doc("<others><fb cmper='1'><cell><fret>0</fret></cell></fb></others>"))
    cell = doc.others.of_tag("fb")[0].fields["cell"]
    assert isinstance(cell, Record)
    assert cell.fields == {"fret": "0"}


def test_nesting_four_deep() -> None:
    doc = parse_enigma(_doc("<others><a cmper='1'><b><c><d>leaf</d></c></b></a></others>"))
    a = doc.others.of_tag("a")[0]
    assert a.fields["b"].fields["c"].fields["d"] == "leaf"


def test_empty_field_is_empty_string() -> None:
    doc = parse_enigma(_doc("<others><x cmper='1'><flag></flag></x></others>"))
    assert doc.others.of_tag("x")[0].fields["flag"] == ""


def test_absent_pool_is_an_empty_pool() -> None:
    doc = parse_enigma(_doc("<entries><entry entnum='1'/></entries>"))
    assert doc.texts.records == ()
    assert doc.header.records == ()


def test_record_is_frozen() -> None:
    rec = parse_enigma(FULL).others.records[0]
    with pytest.raises((AttributeError, TypeError)):
        rec.tag = "y"  # type: ignore[misc]


def test_rejects_non_xml() -> None:
    with pytest.raises(MalformedEnigmaError):
        parse_enigma(b"this is not xml")


def test_rejects_wrong_root() -> None:
    with pytest.raises(MalformedEnigmaError, match="finale"):
        parse_enigma(_doc("", root="notfinale"))


def test_rejects_entity_expansion() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE finale ['
        '<!ENTITY a "AAAAAAAAAA"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
        f'<finale version="18.0" xmlns="{NS}">&b;</finale>'
    ).encode()
    with pytest.raises(MalformedEnigmaError):
        parse_enigma(bomb)


def test_malformed_error_is_a_finale_file_error() -> None:
    assert issubclass(MalformedEnigmaError, FinaleFileError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma/test_document.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_enigma'`

- [ ] **Step 3: Write the implementation**

Create `src/finale_file_parser/enigma/document.py`:

```python
"""Parse decoded EnigmaXML into a navigable document model.

Models the format's uniform structure — seven pools of records, each record
recursive (tag, attributes, fields) — not any of its ~191 individual record
types, and not keyed lookup (no fixed key set uniquely identifies a record; see
the design spec). Every record is preserved in document order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException

from finale_file_parser.errors import FinaleFileError

_FINALE_ROOT = "finale"
_POOLS = ("header", "mappings", "options", "others", "details", "entries", "texts")

FieldValue = "str | tuple[str, ...] | Record | tuple[Record, ...]"


class MalformedEnigmaError(FinaleFileError):
    """The bytes are not parseable EnigmaXML, or the root is not <finale>."""


@dataclass(frozen=True)
class Record:
    """One record: its tag, all its attributes verbatim, and its fields.

    `fields` maps a child element's local name to its value — a str (scalar
    text) or a Record (nested), and a tuple of either when the tag repeats.
    Nothing is coerced; `attrs` designates no keys.
    """

    tag: str
    attrs: Mapping[str, str]
    fields: Mapping[str, str | tuple[str, ...] | "Record" | tuple["Record", ...]]


@dataclass(frozen=True)
class Pool:
    """Every record of one top-level pool, in document order."""

    records: tuple[Record, ...]

    def of_tag(self, tag: str) -> tuple[Record, ...]:
        """All records with this tag, in document order (possibly none)."""
        return tuple(r for r in self.records if r.tag == tag)


class EnigmaDocument:
    """A parsed EnigmaXML document: its schema version and seven pools."""

    def __init__(self, version: str, pools: Mapping[str, Pool]) -> None:
        self.version = version
        self.header = pools["header"]
        self.mappings = pools["mappings"]
        self.options = pools["options"]
        self.others = pools["others"]
        self.details = pools["details"]
        self.entries = pools["entries"]
        self.texts = pools["texts"]


def _local(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _record_from_element(element: Element) -> Record:
    grouped: dict[str, list[str | Record]] = {}
    for child in element:
        value: str | Record = (
            _record_from_element(child) if len(child) else (child.text or "")
        )
        grouped.setdefault(_local(child), []).append(value)
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        name: (values[0] if len(values) == 1 else tuple(values))  # type: ignore[misc]
        for name, values in grouped.items()
    }
    return Record(tag=_local(element), attrs=dict(element.attrib), fields=fields)


def parse_enigma(xml: bytes) -> EnigmaDocument:
    """Parse decoded EnigmaXML into an EnigmaDocument.

    Raises:
        MalformedEnigmaError: the bytes are not parseable XML, or the root is
            not <finale>.
    """
    try:
        root = fromstring(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise MalformedEnigmaError(f"not parseable EnigmaXML: {exc}") from exc
    if _local(root) != _FINALE_ROOT:
        raise MalformedEnigmaError(f"root is <{_local(root)}>, expected <finale>")

    found: dict[str, list[Record]] = {name: [] for name in _POOLS}
    for pool_element in root:
        name = _local(pool_element)
        if name in found:
            found[name].extend(_record_from_element(r) for r in pool_element)
    pools = {name: Pool(tuple(records)) for name, records in found.items()}
    return EnigmaDocument(version=root.get("version", ""), pools=pools)
```

Note `element.attrib` is a plain `dict[str, str]` with namespaces already stripped for unprefixed
attributes (the corpus uses none), so `dict(element.attrib)` captures all attributes verbatim.

Export `parse_enigma`, `EnigmaDocument`, `Pool`, `Record`, and `MalformedEnigmaError` from
`src/finale_file_parser/enigma/__init__.py` and the package root; add them to `EXPECTED_PUBLIC_NAMES`
in `tests/test_public_api.py`. The derived public-API test asserts every subpackage `__all__` is
reachable from the root — satisfy it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: PASS — the new document tests plus everything else.

- [ ] **Step 5: Mutation-verify**

| Mutation | Test that must fail |
|---|---|
| Drop the root-element check | `test_rejects_wrong_root` |
| `of_tag` returns only the first match | `test_of_tag_returns_all_matching_records_in_order` |
| `attrs` filtered to a fixed key subset (drop `part`) | `test_of_tag_returns_all_matching_records_in_order` |
| Repeated fields keep only the first value | `test_repeated_scalar_field_is_a_tuple` |
| Swap `fromstring` for stdlib `xml.etree.ElementTree.fromstring` | `test_rejects_entity_expansion` |

The `part`-drop mutation is the important one: it is the exact data-loss the deferred-keying decision
exists to prevent. If dropping `part` from `attrs` does not fail a test, the `measSpec` collision is
not actually covered.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests
git commit -m "feat: parse EnigmaXML into a record/pool document model"
```

---

### Task 2: Synthetic fixtures and the content-safety guard

**Files:** Create `tests/fixtures/enigma/*.xml` (hand-written) and `tests/enigma/test_fixtures.py`.

**Interfaces:** consumes `parse_enigma`; produces no importable API.

**The content rule.** Hand-written synthetic EnigmaXML with invented records — no corpus content. Decoded EnigmaXML's `texts` pool carries copyright/title/composer in real files, so a test asserts no committed fixture contains a `fileInfo` element at all.

- [ ] **Step 1: Write two synthetic fixtures**

`tests/fixtures/enigma/minimal.xml` — a small valid document touching every pool, with **invented**
values (obviously-fake placeholders, e.g. `<text>PLACEHOLDER</text>`; no real titles/composers).
`tests/fixtures/enigma/nested.xml` — exercises 4-deep nesting and a repeated nested field (an entry
with several notes). Neither may contain a `<fileInfo>` element.

- [ ] **Step 2: Write the tests**

Create `tests/enigma/test_fixtures.py`:

```python
from pathlib import Path

import pytest
from defusedxml.ElementTree import fromstring

from finale_file_parser.enigma.document import parse_enigma

FIXTURES = Path(__file__).parent.parent / "fixtures" / "enigma"


def _fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*.xml"))


def test_there_are_fixtures() -> None:
    assert _fixtures(), "no EnigmaXML fixtures found"


@pytest.mark.parametrize("path", _fixtures(), ids=lambda p: p.name)
def test_fixture_parses(path: Path) -> None:
    assert parse_enigma(path.read_bytes()).version


def test_no_fixture_carries_bibliographic_text() -> None:
    """Decoded EnigmaXML's texts pool holds title/composer/copyright in real
    files; committed fixtures are synthetic and carry none of it."""
    for path in _fixtures():
        locals_ = [e.tag.rsplit("}", 1)[-1] for e in fromstring(path.read_bytes()).iter()]
        assert "fileInfo" not in locals_, f"{path.name} contains a fileInfo record"


def test_nested_fixture_reaches_four_deep() -> None:
    doc = parse_enigma((FIXTURES / "nested.xml").read_bytes())
    ...  # implementer: assert the specific 4-deep leaf your nested.xml defines
```

- [ ] **Step 3: Run, gate, commit**

Run: `uv run pytest tests/enigma/test_fixtures.py -v` then `make check` — both clean.

```bash
git add tests/fixtures/enigma tests/enigma/test_fixtures.py
git commit -m "test: add synthetic EnigmaXML fixtures with a content-safety guard"
```

---

### Task 3: Corpus sweep

**Files:** Create `tests/enigma/test_document_corpus_sweep.py`. Skips when `corpus/` is absent.

- [ ] **Step 1: Write the test**

Compose `parse_enigma(score_xml(path))` over all 401 `.musx` archives and assert:

- every archive parses without raising — **401 of 401**
- `version == "18.0"` for every one
- across the sweep, all seven pools are non-empty on at least one file
- across the sweep, an `entry` with a nested `note` field is reached (the recursive model reaches
  the musical core)
- across the sweep, a `measSpec` in `others` has a `part` attribute (the collision case survives)

Assert the file list is non-empty first. **If an observed value disagrees, report it rather than
adjusting the assertion.** Report counts only — never a corpus title, composer, or record *value*
(this sweep decodes real files that contain them).

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/enigma/test_document_corpus_sweep.py -v` — expected pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/enigma -v; mv /tmp/corpus-parked corpus`

Expected: sweep skipped, other enigma tests pass. **Confirm `corpus/` is restored and reports 639
files** — the user's data, not in git.

- [ ] **Step 3: Commit**

```bash
git add tests/enigma/test_document_corpus_sweep.py
git commit -m "test: sweep the corpus through the EnigmaXML document parser"
```

---

### Task 4: Documentation

**Files:** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Add `enigma/document.py` to Modules. Add a "Known format facts — EnigmaXML structure" subsection:
the seven pools; that records are recursive and a chord's notes are nested `note` fields inside an
entry; that fields nest up to 4 deep; that `version` is the schema version not the app version;
that the `texts` pool carries copyright/title/composer (hence no decoded XML is committed); and —
importantly — that **no fixed key set uniquely identifies a record** (`cmper=1` spans 54 tags;
`measSpec` adds per-`part` variants sharing a cmper), which is why this slice preserves all records
and defers keyed lookup. Link the design spec.

- [ ] **Step 2: `docs/ROADMAP.md`**

Mark the generic-structure step done. Set the next items to: **keyed lookup** (once the full
key-attribute set is mapped — the survey found `cmper` insufficient and `part` among the missing
keys), then **typed record models** starting with `entries`/`note`.

- [ ] **Step 3: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record the EnigmaXML document model and defer keyed lookup"
```

---

## Completion

After Task 4, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed; that records are preserved in document order with all
attributes verbatim (no keyed lookup this slice, and why — no fixed key set is unique); the mutation
results, especially the `part`-drop one; that the corpus sweep parses 401/401 locally and skips in
CI; and — prominently — that decoded EnigmaXML carries copyright/title/composer text, so every
committed fixture is hand-written synthetic XML with a test enforcing it.
