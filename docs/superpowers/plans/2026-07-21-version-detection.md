# Version Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify which Finale version wrote a `.mus` or `.musx` file, before any record parsing.

**Architecture:** A public `detect_version(path)` composes four small units — pure byte-level family
classification, a pure `.mus` banner parser, a `.musx` archive/metadata reader, and result
assembly. Only the entry point and the `.musx` reader perform I/O, which keeps the majority of the
logic testable from byte literals with no fixture files.

**Tech Stack:** Python 3.12, `defusedxml` (first runtime dependency), pytest, ruff, mypy --strict.

**Design spec:** `docs/superpowers/specs/2026-07-21-version-detection-design.md`. Read it before
starting — it records the corpus findings this implementation encodes.

## Global Constraints

- Python `>=3.12`; all code fully type-annotated and passing `mypy --strict`.
- Line length 100 (ruff), lint rules `E, F, I, UP, B`.
- Package root: `src/finale_file_parser/`. Tests: `tests/`.
- XML must be parsed with `defusedxml`, never stdlib `xml.etree.ElementTree`.
- Never read an unbounded amount from an archive member; cap before reading.
- `.mus` header reads are fixed at `0x60` bytes. No read length is ever derived from file content.
- The `.mus` banner field is **not** zero-filled on rewrite: always cut at the first NUL byte.
- Test fixtures may contain format metadata only — never musical content. No `score.dat`, ever.
- `corpus/` is gitignored and must never be committed or referenced by a CI-required test.
- Commit style: Conventional Commits. One task per commit.

---

### Task 1: Result types and exceptions

**Files:**
- Create: `src/finale_file_parser/version/__init__.py`
- Create: `src/finale_file_parser/version/models.py`
- Test: `tests/version/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Family`, `Confidence`, `AppVersion`, `MusDetail`, `MusxDetail`, `FileVersion`,
  `FinaleFileError`, `NotFinaleFileError`. Every later task imports from this module.

- [ ] **Step 1: Write the failing test**

Create `tests/version/__init__.py` as an empty file, then `tests/version/test_models.py`:

```python
import pytest

from finale_file_parser.version.models import (
    AppVersion,
    Confidence,
    Family,
    FileVersion,
    FinaleFileError,
    MusDetail,
    MusxDetail,
    NotFinaleFileError,
)


def test_families_are_distinct() -> None:
    assert Family.MUS is not Family.MUSX


def test_details_are_frozen() -> None:
    detail = MusDetail(banner="Finale(R) 2011", year=2011)
    with pytest.raises(AttributeError):
        detail.year = 2012  # type: ignore[misc]


def test_file_version_holds_family_specific_detail() -> None:
    musx = MusxDetail(
        created=None,
        modified=AppVersion(major=18, maint=5, dev_status="dev", build=7098),
        metadata_schema="18.0",
        platform="MAC",
    )
    version = FileVersion(
        family=Family.MUSX,
        label="18.5 dev (build 7098)",
        confidence=Confidence.EXACT,
        detail=musx,
    )
    assert version.detail is musx
    assert version.confidence is Confidence.EXACT


def test_not_finale_file_error_is_a_finale_file_error() -> None:
    assert issubclass(NotFinaleFileError, FinaleFileError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/version/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.version'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/version/__init__.py` as an empty file. Create
`src/finale_file_parser/version/models.py`:

```python
"""Result types for Finale file version detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FinaleFileError(Exception):
    """Base class for every error this package raises."""


class NotFinaleFileError(FinaleFileError):
    """The file is not a Finale file at all — no recognised container or magic."""


class Family(Enum):
    """Which on-disk container family a file belongs to."""

    MUS = "mus"
    MUSX = "musx"


class Confidence(Enum):
    """How certain the reported version is."""

    EXACT = "exact"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AppVersion:
    """A Finale application version, as reported by .musx metadata."""

    major: int
    maint: int | None
    dev_status: str
    build: int | None


@dataclass(frozen=True)
class MusDetail:
    """Version evidence from a legacy .mus header."""

    banner: str
    """The copyright banner, cut at the first NUL and decoded verbatim."""

    year: int | None
    """Marketing year parsed from the banner, or None if it did not match."""


@dataclass(frozen=True)
class MusxDetail:
    """Version evidence from a .musx NotationMetadata.xml."""

    created: AppVersion | None
    modified: AppVersion | None
    """The last writer. This is the layout authority — prefer it over `created`."""

    metadata_schema: str
    platform: str | None


@dataclass(frozen=True)
class FileVersion:
    """The result of detecting a file's writing version."""

    family: Family
    label: str
    """Human-readable version, e.g. "Finale 2011" or "18.5 dev (build 7098)"."""

    confidence: Confidence
    detail: MusDetail | MusxDetail
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/version/test_models.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/version tests/version
git commit -m "feat: add version detection result types"
```

---

### Task 2: Family classification from header bytes

**Files:**
- Create: `src/finale_file_parser/version/family.py`
- Test: `tests/version/test_family.py`

**Interfaces:**
- Consumes: `Family`, `NotFinaleFileError` from `models.py`.
- Produces: `classify(header: bytes) -> Family`, and the constants `MUS_MAGIC: bytes`,
  `ZIP_MAGIC: bytes`, `HEADER_SIZE: int` (value `0x60`). Task 3 and Task 5 use `HEADER_SIZE`.

**Note on scope:** `classify` returns `Family.MUSX` for *any* zip archive. Distinguishing a real
`.musx` from an unrelated zip requires reading the `mimetype` member, which is Task 4's job. This
split is deliberate — classification stays pure and byte-only.

- [ ] **Step 1: Write the failing test**

Create `tests/version/test_family.py`:

```python
import pytest

from finale_file_parser.version.family import HEADER_SIZE, classify
from finale_file_parser.version.models import Family, NotFinaleFileError


def _mus_header(banner: bytes = b"Finale(R) 2011") -> bytes:
    header = bytearray(b"\x00" * HEADER_SIZE)
    header[0:18] = b"ENIGMA BINARY FILE"
    header[0x20 : 0x20 + len(banner)] = banner
    return bytes(header)


def test_classifies_mus_by_magic() -> None:
    assert classify(_mus_header()) is Family.MUS


def test_classifies_any_zip_as_musx() -> None:
    assert classify(b"PK\x03\x04" + b"\x00" * 60) is Family.MUSX


def test_rejects_unrelated_bytes() -> None:
    with pytest.raises(NotFinaleFileError):
        classify(b"%PDF-1.4" + b"\x00" * 60)


def test_rejects_empty_input() -> None:
    with pytest.raises(NotFinaleFileError):
        classify(b"")


def test_rejects_truncated_magic() -> None:
    with pytest.raises(NotFinaleFileError):
        classify(b"ENIGMA BIN")


def test_header_size_is_96_bytes() -> None:
    assert HEADER_SIZE == 0x60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/version/test_family.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.version.family'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/version/family.py`:

```python
"""Classify a file into a Finale container family from its leading bytes."""

from __future__ import annotations

from finale_file_parser.version.models import Family, NotFinaleFileError

MUS_MAGIC = b"ENIGMA BINARY FILE"
"""Present at offset 0 in every .mus file observed, across Finale 2001-2012."""

ZIP_MAGIC = b"PK\x03\x04"

HEADER_SIZE = 0x60
"""Bytes read for classification and .mus banner parsing. Fixed; never content-derived."""


def classify(header: bytes) -> Family:
    """Return the container family for `header`.

    Any zip archive classifies as MUSX; confirming it is genuinely a Finale
    archive requires reading its `mimetype` member, which `musx.read` does.

    Raises:
        NotFinaleFileError: the bytes match no known Finale container.
    """
    if header.startswith(MUS_MAGIC):
        return Family.MUS
    if header.startswith(ZIP_MAGIC):
        return Family.MUSX
    raise NotFinaleFileError(f"unrecognised file header: {header[:16]!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/version/test_family.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/version/family.py tests/version/test_family.py
git commit -m "feat: classify Finale container family from header bytes"
```

---

### Task 3: Parse the .mus banner

**Files:**
- Create: `src/finale_file_parser/version/mus.py`
- Test: `tests/version/test_mus.py`

**Interfaces:**
- Consumes: `MusDetail` from `models.py`; `HEADER_SIZE` from `family.py`.
- Produces: `parse(header: bytes) -> MusDetail`, and constants `BANNER_OFFSET: int` (`0x20`),
  `BANNER_FIELD_SIZE: int` (`0x40`).

**The trailing-garbage case matters.** A real Finale 2005 file in the corpus contains
`b"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc.\x00\x00\x00logy"` — `logy` survives from
the longer Finale 2004 banner (`...Coda Music Technology`) that a previous save left behind.
Decoding the whole field would append that garbage. Cut at the first NUL.

- [ ] **Step 1: Write the failing test**

Create `tests/version/test_mus.py`:

```python
from finale_file_parser.version.family import HEADER_SIZE
from finale_file_parser.version.mus import BANNER_OFFSET, parse


def _header_with(field: bytes) -> bytes:
    header = bytearray(b"\x00" * HEADER_SIZE)
    header[0:18] = b"ENIGMA BINARY FILE"
    header[BANNER_OFFSET : BANNER_OFFSET + len(field)] = field
    return bytes(header)


def test_parses_year_from_banner() -> None:
    detail = parse(_header_with(b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc."))
    assert detail.year == 2011
    assert detail.banner == "Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc."


def test_parses_coda_era_banner() -> None:
    detail = parse(_header_with(b"Finale(R) 2001 Copyright (c) 1987-2000 Coda Music Technology"))
    assert detail.year == 2001


def test_parses_makemusic_bang_banner() -> None:
    # Finale 2005 spells the vendor "MakeMusic!" — do not pattern-match vendor names.
    detail = parse(_header_with(b"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc."))
    assert detail.year == 2005


def test_stops_at_first_nul_ignoring_previous_writer_residue() -> None:
    # Real corpus case: shorter 2005 banner overwrote the longer 2004 Coda banner.
    field = b"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc.\x00\x00\x00logy"
    detail = parse(_header_with(field))
    assert detail.banner.endswith("MakeMusic! Inc.")
    assert "logy" not in detail.banner


def test_unparseable_banner_yields_none_year_but_keeps_text() -> None:
    detail = parse(_header_with(b"Some Future Banner Format"))
    assert detail.year is None
    assert detail.banner == "Some Future Banner Format"


def test_empty_banner_field_yields_empty_string_and_none_year() -> None:
    detail = parse(_header_with(b""))
    assert detail.banner == ""
    assert detail.year is None


def test_short_header_does_not_raise() -> None:
    detail = parse(b"ENIGMA BINARY FILE")
    assert detail.year is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/version/test_mus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.version.mus'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/version/mus.py`:

```python
"""Extract version evidence from a legacy .mus header."""

from __future__ import annotations

import re

from finale_file_parser.version.models import MusDetail

BANNER_OFFSET = 0x20
BANNER_FIELD_SIZE = 0x40

_BANNER_YEAR = re.compile(r"Finale\(R\)\s+(\d{4})\b")


def parse(header: bytes) -> MusDetail:
    """Return the version evidence carried by a .mus header.

    The banner field is fixed-size and is *not* zero-filled when Finale
    rewrites it, so a shorter banner can leave a tail of the previous, longer
    one behind. Everything from the first NUL onward is therefore discarded.

    Never raises: an unrecognised banner yields `year=None` with the raw text
    preserved, so an unknown variant stays inspectable.
    """
    field = header[BANNER_OFFSET : BANNER_OFFSET + BANNER_FIELD_SIZE]
    banner = field.split(b"\x00", 1)[0].decode("latin-1")
    match = _BANNER_YEAR.match(banner)
    return MusDetail(banner=banner, year=int(match.group(1)) if match else None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/version/test_mus.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/version/mus.py tests/version/test_mus.py
git commit -m "feat: parse Finale version banner from .mus header"
```

---

### Task 4: Read .musx metadata safely

**Files:**
- Modify: `pyproject.toml:11` (add `defusedxml` runtime dependency) and `pyproject.toml:15`
  (add `types-defusedxml` to the dev group)
- Create: `src/finale_file_parser/version/musx.py`
- Test: `tests/version/test_musx.py`

**Interfaces:**
- Consumes: `AppVersion`, `MusxDetail`, `NotFinaleFileError` from `models.py`.
- Produces: `read(path: Path) -> MusxDetail`, and constants `MIMETYPE_VALUE: bytes`,
  `MAX_METADATA_BYTES: int`.

This is the only task handling attacker-controlled structured data. Three defences are required and
each has a test: mimetype validation, an uncompressed-size cap before reading, and `defusedxml`.

- [ ] **Step 1: Add the dependency**

Edit `pyproject.toml` line 11:

```toml
dependencies = ["defusedxml>=0.7.1"]
```

Edit `pyproject.toml` line 15:

```toml
dev = ["pytest>=7.4", "ruff>=0.4", "mypy>=1.8", "types-defusedxml>=0.7"]
```

Run: `uv sync`
Expected: `defusedxml` and `types-defusedxml` installed.

- [ ] **Step 2: Write the failing test**

Create `tests/version/test_musx.py`:

```python
import zipfile
from pathlib import Path

import pytest

from finale_file_parser.version.models import NotFinaleFileError
from finale_file_parser.version.musx import MAX_METADATA_BYTES, read

MIMETYPE = b"application/vnd.makemusic.notation"

METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">
  <fileInfo>
    <created>
      <platform>MAC</platform>
      <appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>
    </created>
    <modified>
      <platform>WIN</platform>
      <appVersion><major>18</major><maint>5</maint><devStatus>dev</devStatus><build>7098</build></appVersion>
    </modified>
  </fileInfo>
</metadata>
"""


def _make_musx(
    tmp_path: Path,
    *,
    mimetype: bytes = MIMETYPE,
    metadata: str | None = METADATA,
    name: str = "sample.musx",
) -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", mimetype)
        if metadata is not None:
            archive.writestr("NotationMetadata.xml", metadata)
    return path


def test_reads_created_and_modified(tmp_path: Path) -> None:
    detail = read(_make_musx(tmp_path))
    assert detail.metadata_schema == "18.0"
    assert detail.created is not None
    assert detail.created.major == 16
    assert detail.created.maint is None
    assert detail.created.dev_status == "release"
    assert detail.modified is not None
    assert detail.modified.major == 18
    assert detail.modified.maint == 5
    assert detail.modified.build == 7098


def test_platform_comes_from_the_modifying_write(tmp_path: Path) -> None:
    assert read(_make_musx(tmp_path)).platform == "WIN"


def test_rejects_zip_that_is_not_a_musx(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "not a score")
    with pytest.raises(NotFinaleFileError):
        read(path)


def test_rejects_wrong_mimetype(tmp_path: Path) -> None:
    with pytest.raises(NotFinaleFileError):
        read(_make_musx(tmp_path, mimetype=b"application/zip"))


def test_missing_metadata_yields_empty_detail(tmp_path: Path) -> None:
    detail = read(_make_musx(tmp_path, metadata=None))
    assert detail.created is None
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_malformed_xml_yields_empty_detail(tmp_path: Path) -> None:
    detail = read(_make_musx(tmp_path, metadata="<metadata><unclosed>"))
    assert detail.modified is None


def test_missing_app_version_yields_none(tmp_path: Path) -> None:
    metadata = (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        "<fileInfo><modified><platform>MAC</platform></modified></fileInfo></metadata>"
    )
    detail = read(_make_musx(tmp_path, metadata=metadata))
    assert detail.modified is None
    assert detail.platform == "MAC"


def test_refuses_oversized_metadata_member(tmp_path: Path) -> None:
    # A zip bomb: small compressed, enormous uncompressed.
    detail = read(_make_musx(tmp_path, metadata="<a/>" + " " * (MAX_METADATA_BYTES + 1)))
    assert detail.modified is None
    assert detail.metadata_schema == ""


def test_resists_entity_expansion(tmp_path: Path) -> None:
    # "Billion laughs". defusedxml must refuse it rather than expanding.
    bomb = """<?xml version="1.0"?>
<!DOCTYPE metadata [
  <!ENTITY a "AAAAAAAAAA">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<metadata version="18.0">&c;</metadata>
"""
    detail = read(_make_musx(tmp_path, metadata=bomb))
    assert detail.modified is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/version/test_musx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.version.musx'`

- [ ] **Step 4: Write minimal implementation**

Create `src/finale_file_parser/version/musx.py`:

```python
"""Read version evidence from a .musx archive's metadata.

Every input is treated as hostile: the archive is validated by mimetype, the
metadata member's declared size is capped before it is read, and the XML is
parsed with defusedxml so entity-expansion payloads are refused.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

from finale_file_parser.version.models import AppVersion, MusxDetail, NotFinaleFileError

MIMETYPE_NAME = "mimetype"
MIMETYPE_VALUE = b"application/vnd.makemusic.notation"
METADATA_NAME = "NotationMetadata.xml"

MAX_METADATA_BYTES = 1 << 20
"""Refuse to read a metadata member larger than 1 MiB uncompressed. Observed
files are ~1 KB; anything vastly larger is a zip bomb, not a score."""

NAMESPACE = {"m": "http://www.makemusic.com/2012/NotationMetadata"}


def read(path: Path) -> MusxDetail:
    """Return the version evidence carried by a .musx archive.

    Raises:
        NotFinaleFileError: the archive is unreadable, or is a zip that is not
            a Finale notation container.

    Unparseable *metadata* is not an error: it yields a MusxDetail with empty
    fields, so an unrecognised variant remains inspectable.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            _require_finale_mimetype(archive, path)
            raw = _read_capped(archive, METADATA_NAME, MAX_METADATA_BYTES)
    except zipfile.BadZipFile as exc:
        raise NotFinaleFileError(f"{path} is not a readable archive") from exc

    if raw is None:
        return MusxDetail(created=None, modified=None, metadata_schema="", platform=None)

    try:
        root = fromstring(raw)
    except Exception:
        # defusedxml raises its own DefusedXmlException subclasses for attack
        # payloads and ParseError for malformed input. Both mean "no usable
        # metadata", which is a result, not a failure.
        return MusxDetail(created=None, modified=None, metadata_schema="", platform=None)

    modified = _find_block(root, "modified")
    created = _find_block(root, "created")
    return MusxDetail(
        created=_app_version(created),
        modified=_app_version(modified),
        metadata_schema=root.get("version") or "",
        platform=_platform(modified) or _platform(created),
    )


def _require_finale_mimetype(archive: zipfile.ZipFile, path: Path) -> None:
    raw = _read_capped(archive, MIMETYPE_NAME, len(MIMETYPE_VALUE))
    if raw != MIMETYPE_VALUE:
        raise NotFinaleFileError(f"{path} is a zip archive but not a Finale .musx")


def _read_capped(archive: zipfile.ZipFile, name: str, cap: int) -> bytes | None:
    """Read `name` only if it declares no more than `cap` uncompressed bytes."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > cap:
        return None
    return archive.read(name)


def _find_block(root: Element, tag: str) -> Element | None:
    block = root.find(f".//m:{tag}", NAMESPACE)
    return block if block is not None else root.find(f".//{tag}")


def _text(parent: Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    found = parent.find(f"m:{tag}", NAMESPACE)
    if found is None:
        found = parent.find(tag)
    return found.text if found is not None and found.text else None


def _int(parent: Element | None, tag: str) -> int | None:
    raw = _text(parent, tag)
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _app_version(block: Element | None) -> AppVersion | None:
    if block is None:
        return None
    found: Any = block.find("m:appVersion", NAMESPACE)
    if found is None:
        found = block.find("appVersion")
    if found is None:
        return None
    major = _int(found, "major")
    if major is None:
        return None
    return AppVersion(
        major=major,
        maint=_int(found, "maint"),
        dev_status=_text(found, "devStatus") or "",
        build=_int(found, "build"),
    )


def _platform(block: Element | None) -> str | None:
    return _text(block, "platform")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/version/test_musx.py -v`
Expected: PASS — 9 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/finale_file_parser/version/musx.py tests/version/test_musx.py
git commit -m "feat: read .musx version metadata with hardened XML and zip handling"
```

---

### Task 5: Public detect_version entry point

**Files:**
- Create: `src/finale_file_parser/version/detect.py`
- Modify: `src/finale_file_parser/__init__.py` (export the public surface)
- Test: `tests/version/test_detect.py`

**Interfaces:**
- Consumes: `classify`, `HEADER_SIZE` from `family.py`; `parse` from `mus.py`; `read` from
  `musx.py`; all types from `models.py`.
- Produces: `detect_version(path: Path) -> FileVersion`, re-exported from the package root as
  `finale_file_parser.detect_version`.

Label formats, fixed here so later tasks can assert on them:
- `.mus` with a year → `"Finale 2011"`; without → `"unknown version"`.
- `.musx` → `"18.5 dev (build 7098)"`; `maint` omitted when absent (`"16 release (build 2)"`);
  `build` clause omitted when absent; no `appVersion` at all → `"unknown version"`.

- [ ] **Step 1: Write the failing test**

Create `tests/version/test_detect.py`:

```python
import zipfile
from pathlib import Path

import pytest

from finale_file_parser import detect_version
from finale_file_parser.version.family import HEADER_SIZE
from finale_file_parser.version.models import (
    Confidence,
    Family,
    MusDetail,
    MusxDetail,
    NotFinaleFileError,
)

MIMETYPE = b"application/vnd.makemusic.notation"


def _write_mus(tmp_path: Path, banner: bytes) -> Path:
    header = bytearray(b"\x00" * HEADER_SIZE)
    header[0:18] = b"ENIGMA BINARY FILE"
    header[0x20 : 0x20 + len(banner)] = banner
    path = tmp_path / "sample.mus"
    path.write_bytes(bytes(header) + b"\xde\xad\xbe\xef" * 64)
    return path


def _write_musx(tmp_path: Path, metadata: str) -> Path:
    path = tmp_path / "sample.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE)
        archive.writestr("NotationMetadata.xml", metadata)
    return path


def _metadata(app_version: str) -> str:
    return (
        '<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">'
        f"<fileInfo><modified><platform>MAC</platform>{app_version}</modified></fileInfo>"
        "</metadata>"
    )


def test_detects_mus(tmp_path: Path) -> None:
    path = _write_mus(tmp_path, b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.")
    result = detect_version(path)
    assert result.family is Family.MUS
    assert result.label == "Finale 2011"
    assert result.confidence is Confidence.EXACT
    assert isinstance(result.detail, MusDetail)


def test_unrecognised_mus_banner_is_unknown_not_an_error(tmp_path: Path) -> None:
    path = _write_mus(tmp_path, b"Finale(R) Future Edition")
    result = detect_version(path)
    assert result.confidence is Confidence.UNKNOWN
    assert result.label == "unknown version"
    assert isinstance(result.detail, MusDetail)
    assert result.detail.banner == "Finale(R) Future Edition"


def test_detects_musx(tmp_path: Path) -> None:
    path = _write_musx(
        tmp_path,
        _metadata(
            "<appVersion><major>18</major><maint>5</maint>"
            "<devStatus>dev</devStatus><build>7098</build></appVersion>"
        ),
    )
    result = detect_version(path)
    assert result.family is Family.MUSX
    assert result.label == "18.5 dev (build 7098)"
    assert result.confidence is Confidence.EXACT
    assert isinstance(result.detail, MusxDetail)


def test_musx_label_omits_absent_maint(tmp_path: Path) -> None:
    path = _write_musx(
        tmp_path,
        _metadata(
            "<appVersion><major>16</major><devStatus>release</devStatus>"
            "<build>2</build></appVersion>"
        ),
    )
    assert detect_version(path).label == "16 release (build 2)"


def test_musx_without_app_version_is_unknown(tmp_path: Path) -> None:
    path = _write_musx(tmp_path, _metadata(""))
    result = detect_version(path)
    assert result.confidence is Confidence.UNKNOWN
    assert result.label == "unknown version"


def test_rejects_non_finale_file(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_bytes(b"just some text, definitely not a score")
    with pytest.raises(NotFinaleFileError):
        detect_version(path)


def test_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.mus"
    path.write_bytes(b"")
    with pytest.raises(NotFinaleFileError):
        detect_version(path)


def test_rejects_file_truncated_inside_the_magic(tmp_path: Path) -> None:
    path = tmp_path / "truncated.mus"
    path.write_bytes(b"ENIGMA BIN")
    with pytest.raises(NotFinaleFileError):
        detect_version(path)


def test_accepts_mus_truncated_after_the_magic(tmp_path: Path) -> None:
    # Short but validly-magicked: report UNKNOWN rather than raising.
    path = tmp_path / "short.mus"
    path.write_bytes(b"ENIGMA BINARY FILE")
    result = detect_version(path)
    assert result.family is Family.MUS
    assert result.confidence is Confidence.UNKNOWN


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_version(tmp_path / "nope.mus")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/version/test_detect.py -v`
Expected: FAIL — `ImportError: cannot import name 'detect_version' from 'finale_file_parser'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/version/detect.py`:

```python
"""Public entry point for Finale file version detection."""

from __future__ import annotations

from pathlib import Path

from finale_file_parser.version import mus, musx
from finale_file_parser.version.family import HEADER_SIZE, classify
from finale_file_parser.version.models import (
    Confidence,
    Family,
    FileVersion,
    MusDetail,
    MusxDetail,
)

UNKNOWN_LABEL = "unknown version"


def detect_version(path: Path) -> FileVersion:
    """Identify which Finale version wrote the file at `path`.

    Reads only the header (and, for .musx, the archive metadata) — never the
    score body.

    Raises:
        FileNotFoundError: no such file.
        NotFinaleFileError: the file is not a Finale file.
    """
    with open(path, "rb") as handle:
        header = handle.read(HEADER_SIZE)

    family = classify(header)
    if family is Family.MUS:
        detail = mus.parse(header)
        return _assemble(Family.MUS, _mus_label(detail), detail.year is not None, detail)

    musx_detail = musx.read(Path(path))
    known = musx_detail.modified is not None or musx_detail.created is not None
    return _assemble(Family.MUSX, _musx_label(musx_detail), known, musx_detail)


def _assemble(
    family: Family, label: str, known: bool, detail: MusDetail | MusxDetail
) -> FileVersion:
    return FileVersion(
        family=family,
        label=label,
        confidence=Confidence.EXACT if known else Confidence.UNKNOWN,
        detail=detail,
    )


def _mus_label(detail: MusDetail) -> str:
    return f"Finale {detail.year}" if detail.year is not None else UNKNOWN_LABEL


def _musx_label(detail: MusxDetail) -> str:
    app = detail.modified or detail.created
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

Replace the contents of `src/finale_file_parser/__init__.py`:

```python
"""A parser for Finale music notation files (.mus/.musx)."""

from finale_file_parser.version.detect import detect_version
from finale_file_parser.version.models import (
    AppVersion,
    Confidence,
    Family,
    FileVersion,
    FinaleFileError,
    MusDetail,
    MusxDetail,
    NotFinaleFileError,
)

__all__ = [
    "AppVersion",
    "Confidence",
    "Family",
    "FileVersion",
    "FinaleFileError",
    "MusDetail",
    "MusxDetail",
    "NotFinaleFileError",
    "detect_version",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/version/test_detect.py -v`
Expected: PASS — 10 passed

- [ ] **Step 5: Run the full gate**

Run: `make check`
Expected: ruff clean, ruff format clean, mypy `Success`, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/finale_file_parser tests/version/test_detect.py
git commit -m "feat: add detect_version public entry point"
```

---

### Task 6: Real-file fixtures and their manifest

**Files:**
- Create: `scripts/build_version_fixtures.py`
- Create: `tests/fixtures/version/*.bin` and `tests/fixtures/version/*.musx` (generated)
- Create: `tests/fixtures/version/MANIFEST.toml` (generated)
- Test: `tests/version/test_fixtures.py`

**Interfaces:**
- Consumes: `detect_version` from the package root.
- Produces: committed fixtures plus `MANIFEST.toml`, whose `[[fixture]]` entries carry
  `file`, `source`, `bytes`, `expected_family`, `expected_label`, `expected_confidence`.

**Content rule:** `.mus` fixtures are the first `0x60` bytes only — magic and banner, no musical
content. `.musx` fixtures are rebuilt archives containing only `mimetype` and
`NotationMetadata.xml`; `score.dat` and `presets/` are excluded, so no musical content is committed.
The generator must enforce this, not merely intend it.

- [ ] **Step 1: Write the generator**

Create `scripts/build_version_fixtures.py`:

```python
"""Build committed test fixtures from the local corpus.

Run manually when the corpus changes:  uv run python scripts/build_version_fixtures.py

Only format metadata is emitted. .mus fixtures are header prefixes; .musx
fixtures are rebuilt archives without score.dat or presets. No musical content
is ever written.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from finale_file_parser import detect_version
from finale_file_parser.version.family import HEADER_SIZE

CORPUS = Path("corpus")
OUT = Path("tests/fixtures/version")
ALLOWED_MUSX_MEMBERS = {"mimetype", "NotationMetadata.xml"}


def _mus_fixtures() -> dict[str, Path]:
    """One .mus file per distinct banner year, plus the trailing-garbage case."""
    chosen: dict[str, Path] = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".mus":
            continue
        head = path.open("rb").read(HEADER_SIZE)
        if not head.startswith(b"ENIGMA BINARY FILE"):
            continue
        field = head[0x20:HEADER_SIZE]
        banner = field.split(b"\x00", 1)[0].decode("latin-1")
        year = banner.split()[1] if len(banner.split()) > 1 else "unknown"
        residue = field[len(banner) :].strip(b"\x00")
        key = f"mus-{year}-residue" if residue else f"mus-{year}"
        chosen.setdefault(key, path)
    return chosen


def _musx_fixtures() -> dict[str, Path]:
    """One .musx per distinct (modified major, platform) pair."""
    chosen: dict[str, Path] = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".musx":
            continue
        try:
            detail = detect_version(path).detail
        except Exception:
            continue
        app = getattr(detail, "modified", None)
        platform = getattr(detail, "platform", None)
        key = f"musx-{app.major if app else 'none'}-{platform or 'none'}"
        chosen.setdefault(key, path)
    return chosen


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    entries: list[str] = []

    for name, src in sorted(_mus_fixtures().items()):
        target = OUT / f"{name}.bin"
        target.write_bytes(src.open("rb").read(HEADER_SIZE))
        entries.append(_entry(target, src, f"first {HEADER_SIZE} bytes"))

    for name, src in sorted(_musx_fixtures().items()):
        target = OUT / f"{name}.musx"
        with zipfile.ZipFile(src) as source, zipfile.ZipFile(target, "w") as out:
            for member in source.namelist():
                if member in ALLOWED_MUSX_MEMBERS:
                    out.writestr(member, source.read(member))
        _assert_metadata_only(target)
        entries.append(_entry(target, src, "mimetype + NotationMetadata.xml only"))

    (OUT / "MANIFEST.toml").write_text(
        "# Generated by scripts/build_version_fixtures.py — do not edit by hand.\n"
        "# Sources are local corpus files, which are NOT committed.\n\n" + "\n".join(entries)
    )
    print(f"wrote {len(entries)} fixtures to {OUT}")


def _assert_metadata_only(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        extra = set(archive.namelist()) - ALLOWED_MUSX_MEMBERS
    if extra:
        raise SystemExit(f"refusing to emit {archive_path}: unexpected members {sorted(extra)}")


def _entry(target: Path, source: Path, taken: str) -> str:
    result = detect_version(target)
    return (
        "[[fixture]]\n"
        f'file = "{target.name}"\n'
        f'source = "{source.relative_to(CORPUS)}"\n'
        f'bytes = "{taken}"\n'
        f'expected_family = "{result.family.value}"\n'
        f'expected_label = "{result.label}"\n'
        f'expected_confidence = "{result.confidence.value}"\n'
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the fixtures**

Run: `uv run python scripts/build_version_fixtures.py`
Expected: `wrote N fixtures to tests/fixtures/version` with N ≥ 7 (5 `.mus` years, at least one
residue case, and one `.musx` per major/platform pair).

- [ ] **Step 3: Verify no musical content was committed**

Run:

```bash
python3 -c "
import zipfile, pathlib
for p in pathlib.Path('tests/fixtures/version').glob('*.musx'):
    names = zipfile.ZipFile(p).namelist()
    assert set(names) <= {'mimetype','NotationMetadata.xml'}, (p, names)
    print(p.name, names)
"
ls -la tests/fixtures/version/
```

Expected: every `.musx` lists exactly `mimetype` and `NotationMetadata.xml`; every `.bin` is 96
bytes. If any archive contains `score.dat`, stop and fix the generator.

- [ ] **Step 4: Write the test that reads the manifest**

Create `tests/version/test_fixtures.py`:

```python
import tomllib
from pathlib import Path

import pytest

from finale_file_parser import detect_version

FIXTURES = Path(__file__).parent.parent / "fixtures" / "version"
MANIFEST = FIXTURES / "MANIFEST.toml"


def _entries() -> list[dict[str, str]]:
    with MANIFEST.open("rb") as handle:
        return tomllib.load(handle)["fixture"]


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["file"])
def test_fixture_detects_as_manifest_declares(entry: dict[str, str]) -> None:
    result = detect_version(FIXTURES / entry["file"])
    assert result.family.value == entry["expected_family"]
    assert result.label == entry["expected_label"]
    assert result.confidence.value == entry["expected_confidence"]


def test_every_fixture_file_has_a_manifest_entry() -> None:
    declared = {e["file"] for e in _entries()}
    on_disk = {p.name for p in FIXTURES.iterdir() if p.name != "MANIFEST.toml"}
    assert declared == on_disk


def test_no_fixture_contains_musical_content() -> None:
    import zipfile

    for path in FIXTURES.glob("*.musx"):
        assert set(zipfile.ZipFile(path).namelist()) <= {"mimetype", "NotationMetadata.xml"}


def test_all_five_mus_versions_are_represented() -> None:
    labels = {e["expected_label"] for e in _entries()}
    for year in (2001, 2004, 2005, 2011, 2012):
        assert f"Finale {year}" in labels
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/version/test_fixtures.py -v`
Expected: PASS — one parametrised case per fixture plus 3 structural tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_version_fixtures.py tests/fixtures/version tests/version/test_fixtures.py
git commit -m "test: add real-file version fixtures and provenance manifest"
```

---

### Task 7: Corpus sweep (local only)

**Files:**
- Create: `tests/version/test_corpus_sweep.py`

**Interfaces:**
- Consumes: `detect_version`, `Family`, `Confidence` from the package root.
- Produces: nothing importable — this is a regression net only.

Skips entirely when `corpus/` is absent, so CI stays green without it. Expected tallies come from
the design spec's findings section.

- [ ] **Step 1: Write the test**

Create `tests/version/test_corpus_sweep.py`:

```python
"""Sweep the full local corpus. Skipped wherever corpus/ is absent (e.g. CI).

The corpus is copyrighted third-party material and is gitignored; these
assertions are the regression net against 639 real files without committing any
of them. Expected tallies come from
docs/superpowers/specs/2026-07-21-version-detection-design.md.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from finale_file_parser import Confidence, Family, detect_version

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_MUS = {
    "Finale 2001": 102,
    "Finale 2004": 1,
    "Finale 2005": 36,
    "Finale 2011": 89,
    "Finale 2012": 10,
}
EXPECTED_MUSX_COUNT = 401


def _files(suffix: str) -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == suffix]


def test_every_mus_file_detects_exactly() -> None:
    tally: collections.Counter[str] = collections.Counter()
    for path in _files(".mus"):
        result = detect_version(path)
        assert result.family is Family.MUS, path
        assert result.confidence is Confidence.EXACT, path
        tally[result.label] += 1
    assert dict(tally) == EXPECTED_MUS


def test_every_musx_file_detects_exactly() -> None:
    paths = _files(".musx")
    assert len(paths) == EXPECTED_MUSX_COUNT
    for path in paths:
        result = detect_version(path)
        assert result.family is Family.MUSX, path
        assert result.confidence is Confidence.EXACT, path


def test_every_musx_reports_schema_18() -> None:
    for path in _files(".musx"):
        detail = detect_version(path).detail
        assert getattr(detail, "metadata_schema", None) == "18.0", path


def test_directory_names_are_not_trusted_as_version_labels() -> None:
    # holiday_tunes_2013/ holds Finale 2012 files — the banner is the truth.
    mislabelled = [p for p in _files(".mus") if "holiday_tunes_2013" in str(p)]
    if mislabelled:
        assert all(detect_version(p).label == "Finale 2012" for p in mislabelled)
```

- [ ] **Step 2: Run with the corpus present**

Run: `uv run pytest tests/version/test_corpus_sweep.py -v`
Expected: PASS — 4 passed. If a tally assertion fails, the corpus changed; re-verify with the
survey in the spec and update both documents rather than loosening the test.

- [ ] **Step 3: Verify it skips without the corpus**

Run: `mv corpus /tmp/corpus-parked && uv run pytest tests/version/test_corpus_sweep.py -v; mv /tmp/corpus-parked corpus`
Expected: 4 skipped, then the corpus is restored. Confirm `ls corpus` succeeds afterwards.

- [ ] **Step 4: Commit**

```bash
git add tests/version/test_corpus_sweep.py
git commit -m "test: add local corpus sweep for version detection"
```

---

### Task 8: Update project documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md` (Modules section)
- Modify: `docs/DECISIONS.md` (close one open question, add the dependency decision)
- Modify: `docs/ROADMAP.md` (mark version detection done)
- Modify: `CLAUDE.md:16` (key libraries line)

**Interfaces:**
- Consumes: nothing. Documentation only.
- Produces: nothing importable.

- [ ] **Step 1: Record the format knowledge in ARCHITECTURE.md**

Add to the Modules section:

```markdown
- `src/finale_file_parser/version/` — identifies which Finale version wrote a file, before any
  record parsing. `models.py` (types), `family.py` (magic → family), `mus.py` (banner parsing),
  `musx.py` (archive metadata), `detect.py` (public entry).

### Known format facts — version

- `.mus` begins with `ENIGMA BINARY FILE` at offset 0, identical across Finale 2001–2012. The
  writing version is an ASCII banner at offset `0x20`, e.g.
  `Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.`
  Evidence: 238 corpus files; see `docs/superpowers/specs/2026-07-21-version-detection-design.md`.
- That banner field is fixed-size and is **not** zero-filled on rewrite, so a shorter banner can
  leave a tail of the previous, longer one behind (observed: `logy` from the Finale 2004 Coda
  banner surviving into a 2005 file). Always cut at the first NUL.
- `.musx` is a zip with `mimetype` = `application/vnd.makemusic.notation`. Version data lives in
  `NotationMetadata.xml` as plaintext, with separate `created` and `modified` blocks. **`modified`
  is the layout authority** — 264 of 401 corpus files were created by major=16 but last written by
  major=18.
- `score.dat` is obfuscated high-entropy data. Version detection never reads it.
```

- [ ] **Step 2: Update DECISIONS.md**

Add a DECIDED entry at the top of the entry list:

```markdown
## 2026-07-21 — DECIDED: defusedxml for all XML parsing

`.musx` metadata is attacker-controlled XML, and stdlib `ElementTree` is vulnerable to
entity-expansion and external-entity attacks. All XML parsing uses **`defusedxml`** — the project's
first runtime dependency. Reason: hand-hardening the stdlib parser is easy to get subtly wrong and
easy to regress.
```

Then remove the `format versioning` bullet from Open questions and add:

```markdown
## 2026-07-21 — DECIDED: version detection precedes record parsing

Version is detected from headers/metadata before any record parsing, and both formats are covered.
Whether each version needs *distinct record-parsing logic* remains unknown — that question opens
once record parsing begins.
```

- [ ] **Step 3: Update ROADMAP.md**

Change the Phase 1 list to mark version detection complete and note it landed ahead of the
container reader:

```markdown
- [x] Version detection for `.mus` and `.musx` (`detect_version`).
```

- [ ] **Step 4: Update CLAUDE.md key libraries**

Replace line 16:

```markdown
- **Key libraries:** `defusedxml` — all XML parsing, because `.musx` metadata is untrusted input.
```

- [ ] **Step 5: Run the full gate**

Run: `make check`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs: record version detection design facts and decisions"
```

---

## Completion

After Task 8, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

```bash
git push -u origin <branch>
gh pr create --base main --title "feat: Finale version detection for .mus and .musx" --body "..."
```

The PR body should state: what landed, that `make check` passes, that the corpus sweep ran locally
against 639 files (and skips in CI), and that no musical content is committed.
