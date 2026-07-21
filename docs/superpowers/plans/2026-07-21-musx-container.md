# `.musx` Container Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open a `.musx` archive, enumerate its members, and extract the score stream, without interpreting any of it.

**Architecture:** A new `container/` package owns all archive access and safety. `version/musx.py` is refactored to consume it instead of opening archives itself, so one module owns archive safety and the two cannot drift. Name validation is a pure function over strings; the reader is a context manager owning the zip handle.

**Tech Stack:** Python 3.12, stdlib `zipfile`, pytest, ruff, mypy --strict. No new dependencies.

**Design spec:** `docs/superpowers/specs/2026-07-21-musx-container-design.md`. Read it before starting — it records the corpus survey this implementation encodes.

## Global Constraints

- Python `>=3.12`; fully type-annotated; must pass `mypy --strict`.
- ruff line-length 100, lint rules `E, F, I, UP, B`. `make check` covers `src tests scripts`.
- Package root `src/finale_file_parser/`. Tests in `tests/`.
- **Nothing is ever extracted to disk.** The reader returns bytes; it does not write files.
- **No payload bytes from `corpus/` may be committed.** Fixtures carry structure only — member names, order, compression method, declared uncompressed lengths. `corpus/` is gitignored copyrighted material.
- Cap values, exact: `MAX_MEMBERS = 64`; `MAX_TOTAL_UNCOMPRESSED = 16 * 1024 * 1024`.
- Mimetype value, exact: `b"application/vnd.makemusic.notation"`.
- **Every safety check must be verified by mutation** — delete the check, confirm its test fails, restore. Nothing hostile occurs in the corpus, so these defences are testable only against synthetic input. This project has shipped tests that passed with the behaviour under test removed in five consecutive review rounds. Clear `__pycache__` and run with `PYTHONDONTWRITEBYTECODE=1` when mutation-testing; stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task unless a task says otherwise.

---

### Task 1: Member name validation and container types

**Files:**
- Create: `src/finale_file_parser/container/__init__.py`
- Create: `src/finale_file_parser/container/models.py`
- Create: `src/finale_file_parser/container/names.py`
- Test: `tests/container/__init__.py` (empty), `tests/container/test_names.py`, `tests/container/test_models.py`

**Interfaces:**
- Consumes: `FinaleFileError` from `finale_file_parser.version.models`.
- Produces: `ContainerEntry` (frozen dataclass: `name: str`, `size: int`, `compressed_size: int`, `compress_type: int`), `CorruptContainerError`, and `is_safe_name(name: str) -> bool`. Task 2 imports all of these.

**Policy this task encodes:** reject *unsafe* names, allow *unknown but safe* ones. A member a future Finale release adds must surface as data, not break reading. Unsafe means: empty, absolute (leading `/`), containing a `..` path segment, containing a backslash, containing control characters, or a drive-letter prefix (`C:`).

- [ ] **Step 1: Write the failing tests**

Create `tests/container/__init__.py` as an empty file. Create `tests/container/test_names.py`:

```python
import pytest

from finale_file_parser.container.names import is_safe_name

SAFE = [
    "mimetype",
    "META-INF/container.xml",
    "NotationMetadata.xml",
    "score.dat",
    "presets/10002.preset",
    "graphics/1.jpg",
    "some/future/member.bin",       # unknown but harmless — must be allowed
    "weird name with spaces.dat",
]

UNSAFE = [
    "",
    "/etc/passwd",
    "../escape.dat",
    "presets/../../escape.dat",
    "..",
    "dir\\file.dat",
    "C:/windows/system32",
    "bad\x00name",
    "bad\nname",
]


@pytest.mark.parametrize("name", SAFE)
def test_safe_names_are_allowed(name: str) -> None:
    assert is_safe_name(name) is True


@pytest.mark.parametrize("name", UNSAFE)
def test_unsafe_names_are_rejected(name: str) -> None:
    assert is_safe_name(name) is False


def test_a_dotdot_inside_a_filename_is_not_a_traversal() -> None:
    # "..." and "a..b" contain dots but no ".." *segment*.
    assert is_safe_name("presets/a..b.preset") is True
    assert is_safe_name("...dat") is True
```

Create `tests/container/test_models.py`:

```python
import pytest

from finale_file_parser.container.models import ContainerEntry, CorruptContainerError
from finale_file_parser.version.models import FinaleFileError


def test_entry_is_frozen() -> None:
    entry = ContainerEntry(name="score.dat", size=96427, compressed_size=96000, compress_type=8)
    with pytest.raises(AttributeError):
        entry.size = 1  # type: ignore[misc]


def test_corrupt_container_error_is_a_finale_file_error() -> None:
    assert issubclass(CorruptContainerError, FinaleFileError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/container -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.container'`

- [ ] **Step 3: Write minimal implementation**

Create `src/finale_file_parser/container/__init__.py` as an empty file.

Create `src/finale_file_parser/container/models.py`:

```python
"""Types for the .musx container reader."""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.version.models import FinaleFileError


class CorruptContainerError(FinaleFileError):
    """The archive is a Finale container but violates a structural safety rule.

    Distinct from NotFinaleFileError, which means "this is not a Finale file at
    all". This means "it is one, and it is malformed or hostile".
    """


@dataclass(frozen=True)
class ContainerEntry:
    """One member of a .musx archive, as declared by its central directory."""

    name: str
    size: int
    """Declared uncompressed size. Never trusted for allocation without a cap."""

    compressed_size: int
    compress_type: int
    """zipfile compression constant: 0 = STORED, 8 = DEFLATE."""
```

Create `src/finale_file_parser/container/names.py`:

```python
"""Member-name safety.

Reject names that are dangerous; allow names that are merely unfamiliar. A
future Finale release may add members we have never seen, and those must stay
inspectable rather than making the whole archive unreadable.
"""

from __future__ import annotations

_UNSAFE_CHARS = frozenset("\\")


def is_safe_name(name: str) -> bool:
    """Return True if `name` is safe to surface and to look up.

    Unsafe means: empty, absolute, containing a `..` path segment, containing a
    backslash, containing control characters, or carrying a drive-letter prefix.
    """
    if not name:
        return False
    if name.startswith("/"):
        return False
    if any(char in _UNSAFE_CHARS for char in name):
        return False
    if any(ord(char) < 0x20 for char in name):
        return False
    if len(name) > 1 and name[1] == ":":
        return False
    return ".." not in name.split("/")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/container -v`
Expected: PASS — 20 passed (17 parametrised name cases + 3 others)

- [ ] **Step 5: Commit**

```bash
git add src/finale_file_parser/container tests/container
git commit -m "feat: add container member-name validation and entry types"
```

---

### Task 2: The container reader

**Files:**
- Create: `src/finale_file_parser/container/musx.py`
- Test: `tests/container/conftest.py`, `tests/container/test_musx.py`

**Interfaces:**
- Consumes: `ContainerEntry`, `CorruptContainerError` from `container/models.py`; `is_safe_name` from `container/names.py`; `NotFinaleFileError` from `version/models.py`.
- Produces: `open_musx(path: str | os.PathLike[str]) -> MusxContainer`; `MusxContainer` with `.entries: tuple[ContainerEntry, ...]`, `.read(name: str, *, max_bytes: int) -> bytes`, `.score_stream() -> bytes`; constants `MIMETYPE_NAME`, `MIMETYPE_VALUE`, `SCORE_NAME`, `MAX_MEMBERS`, `MAX_TOTAL_UNCOMPRESSED`. Tasks 3, 4 and 5 all consume these.
- Produces (tests): the `make_archive` fixture in `tests/container/conftest.py`, reused by Task 3.

**Error contract, exactly:**
- `FileNotFoundError` — no such path.
- `NotFinaleFileError` — not a readable zip, or a zip without the Finale mimetype.
- `CorruptContainerError` — opens and is Finale, but: an unsafe member name, duplicate member names, more than `MAX_MEMBERS` members, total declared size over `MAX_TOTAL_UNCOMPRESSED`, a `read()` whose member declares more than `max_bytes`, or `score_stream()` when `score.dat` is absent.
- `KeyError` — `read()` for an absent member.

Validation happens once, at open time, over the central directory — before any member is read.

- [ ] **Step 1: Write the fixture**

Create `tests/container/conftest.py`:

```python
"""Shared fixtures for container tests.

Every archive here is constructed in-test. Nothing is derived from `corpus/`.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

MIMETYPE = b"application/vnd.makemusic.notation"

DEFAULT_MEMBERS: tuple[tuple[str, bytes], ...] = (
    ("mimetype", MIMETYPE),
    ("META-INF/container.xml", b"<container/>"),
    ("NotationMetadata.xml", b"<metadata/>"),
    ("presets/1.preset", b"preset-bytes"),
    ("score.dat", b"synthetic-score-payload"),
)


@pytest.fixture
def make_archive(tmp_path: Path) -> Callable[..., Path]:
    """Write a zip archive from (name, payload) pairs and return its path."""

    def build(
        members: Sequence[tuple[str, bytes]] = DEFAULT_MEMBERS,
        *,
        name: str = "sample.musx",
        allow_duplicates: bool = False,
    ) -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            for member_name, payload in members:
                # mimetype is stored uncompressed and first, matching all 401
                # corpus archives.
                method = zipfile.ZIP_STORED if member_name == "mimetype" else zipfile.ZIP_DEFLATED
                if allow_duplicates:
                    info = zipfile.ZipInfo(member_name)
                    info.compress_type = method
                    archive.writestr(info, payload)
                else:
                    archive.writestr(member_name, payload, compress_type=method)
        return path

    return build
```

- [ ] **Step 2: Write the failing tests**

Create `tests/container/test_musx.py`:

```python
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser.container.models import CorruptContainerError
from finale_file_parser.container.musx import (
    MAX_MEMBERS,
    MAX_TOTAL_UNCOMPRESSED,
    open_musx,
)
from finale_file_parser.version.models import NotFinaleFileError

from .conftest import MIMETYPE


def test_enumerates_members_in_archive_order(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        names = [entry.name for entry in container.entries]
    assert names[0] == "mimetype"
    assert names == [
        "mimetype",
        "META-INF/container.xml",
        "NotationMetadata.xml",
        "presets/1.preset",
        "score.dat",
    ]


def test_entry_reports_declared_sizes_and_method(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        by_name = {entry.name: entry for entry in container.entries}
    assert by_name["mimetype"].compress_type == zipfile.ZIP_STORED
    assert by_name["score.dat"].compress_type == zipfile.ZIP_DEFLATED
    assert by_name["score.dat"].size == len(b"synthetic-score-payload")


def test_reads_score_stream(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        assert container.score_stream() == b"synthetic-score-payload"


def test_read_returns_member_bytes(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        assert container.read("NotationMetadata.xml", max_bytes=1024) == b"<metadata/>"


def test_accepts_str_path(make_archive: Callable[..., Path]) -> None:
    with open_musx(str(make_archive())) as container:
        assert container.entries


def test_unknown_but_safe_member_name_is_allowed(make_archive: Callable[..., Path]) -> None:
    members = (
        ("mimetype", MIMETYPE),
        ("some/future/member.bin", b"who knows"),
        ("score.dat", b"payload"),
    )
    with open_musx(make_archive(members)) as container:
        assert "some/future/member.bin" in [entry.name for entry in container.entries]


def test_rejects_unsafe_member_name(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", MIMETYPE), ("../escape.dat", b"x"), ("score.dat", b"y"))
    with pytest.raises(CorruptContainerError, match="unsafe member name"):
        open_musx(make_archive(members))


def test_rejects_duplicate_member_names(make_archive: Callable[..., Path]) -> None:
    members = (
        ("mimetype", MIMETYPE),
        ("score.dat", b"first"),
        ("score.dat", b"second"),
    )
    with pytest.raises(CorruptContainerError, match="duplicate member name"):
        open_musx(make_archive(members, allow_duplicates=True))


def test_rejects_too_many_members(make_archive: Callable[..., Path]) -> None:
    members = [("mimetype", MIMETYPE)]
    members += [(f"presets/{i}.preset", b"x") for i in range(MAX_MEMBERS + 1)]
    with pytest.raises(CorruptContainerError, match="too many members"):
        open_musx(make_archive(tuple(members)))


def test_rejects_total_size_over_cap(tmp_path: Path) -> None:
    # Highly compressible payloads: small on disk, enormous declared size.
    path = tmp_path / "bomb.musx"
    chunk = b"\x00" * (4 * 1024 * 1024)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for i in range(8):  # 32 MiB declared, over the 16 MiB cap
            archive.writestr(f"presets/{i}.preset", chunk)
    assert 8 * len(chunk) > MAX_TOTAL_UNCOMPRESSED
    with pytest.raises(CorruptContainerError, match="total declared size"):
        open_musx(path)


def test_read_refuses_member_over_max_bytes(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(CorruptContainerError, match="exceeds max_bytes"):
            container.read("score.dat", max_bytes=4)


def test_read_of_absent_member_raises_key_error(make_archive: Callable[..., Path]) -> None:
    with open_musx(make_archive()) as container:
        with pytest.raises(KeyError):
            container.read("nope.dat", max_bytes=1024)


def test_score_stream_without_score_dat_raises(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", MIMETYPE), ("NotationMetadata.xml", b"<m/>"))
    with open_musx(make_archive(members)) as container:
        with pytest.raises(CorruptContainerError, match="no score.dat"):
            container.score_stream()


def test_rejects_zip_without_finale_mimetype(make_archive: Callable[..., Path]) -> None:
    members = (("mimetype", b"application/zip"), ("score.dat", b"x"))
    with pytest.raises(NotFinaleFileError):
        open_musx(make_archive(members))


def test_rejects_zip_with_no_mimetype_member(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "not a score")
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_rejects_non_zip(tmp_path: Path) -> None:
    path = tmp_path / "legacy.mus"
    path.write_bytes(b"ENIGMA BINARY FILE" + b"\x00" * 78)
    with pytest.raises(NotFinaleFileError):
        open_musx(path)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        open_musx(tmp_path / "nope.musx")


def test_closing_releases_the_handle(make_archive: Callable[..., Path]) -> None:
    container = open_musx(make_archive())
    container.close()
    with pytest.raises(ValueError):
        container.read("score.dat", max_bytes=1024)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/container/test_musx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.container.musx'`

- [ ] **Step 4: Write minimal implementation**

Create `src/finale_file_parser/container/musx.py`:

```python
"""Read the structure of a .musx archive.

A .musx is a zip container. This module opens one, validates its structure,
enumerates its members, and hands back member bytes. It does not interpret any
payload.

Every archive is treated as hostile: structural limits are checked once at open
time against the central directory, before any member is read, and nothing is
ever extracted to disk.
"""

from __future__ import annotations

import os
import zipfile
from types import TracebackType

from finale_file_parser.container.models import ContainerEntry, CorruptContainerError
from finale_file_parser.container.names import is_safe_name
from finale_file_parser.version.models import NotFinaleFileError

MIMETYPE_NAME = "mimetype"
MIMETYPE_VALUE = b"application/vnd.makemusic.notation"
SCORE_NAME = "score.dat"

MAX_MEMBERS = 64
"""Corpus maximum is 10 members."""

MAX_TOTAL_UNCOMPRESSED = 16 * 1024 * 1024
"""Corpus maximum is 419,972 bytes per archive. A per-member cap alone does not
stop an archive of many members each just under that cap."""


class MusxContainer:
    """An open .musx archive.

    Use as a context manager; it owns the underlying zip handle.
    """

    def __init__(self, archive: zipfile.ZipFile, entries: tuple[ContainerEntry, ...]) -> None:
        self._archive = archive
        self.entries = entries

    def __enter__(self) -> MusxContainer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._archive.close()

    def read(self, name: str, *, max_bytes: int) -> bytes:
        """Return the bytes of member `name`.

        `max_bytes` is required and has no default: every call site states its
        own bound, rather than inheriting one that silently stops fitting.

        Raises:
            KeyError: no such member.
            CorruptContainerError: the member declares more than `max_bytes`.
        """
        info = self._archive.getinfo(name)
        if info.file_size > max_bytes:
            raise CorruptContainerError(
                f"member {name!r} declares {info.file_size} bytes, which exceeds max_bytes"
                f" of {max_bytes}"
            )
        return self._archive.read(name)

    def score_stream(self) -> bytes:
        """Return the raw, still-obfuscated score payload.

        Raises:
            CorruptContainerError: the archive carries no score.dat. All 401
                corpus archives have one, so its absence is malformed input
                rather than a caller mistake.
        """
        try:
            info = self._archive.getinfo(SCORE_NAME)
        except KeyError as exc:
            raise CorruptContainerError("archive has no score.dat") from exc
        return self.read(SCORE_NAME, max_bytes=info.file_size)


def open_musx(path: str | os.PathLike[str]) -> MusxContainer:
    """Open a .musx archive and validate its structure.

    Raises:
        FileNotFoundError: no such path.
        NotFinaleFileError: not a readable zip, or a zip that does not carry the
            Finale notation mimetype.
        CorruptContainerError: a Finale archive violating a structural limit.
    """
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise NotFinaleFileError(f"{path} is not a readable archive") from exc

    try:
        _require_finale_mimetype(archive, path)
        entries = _validated_entries(archive)
    except Exception:
        archive.close()
        raise
    return MusxContainer(archive, entries)


def _require_finale_mimetype(archive: zipfile.ZipFile, path: object) -> None:
    try:
        info = archive.getinfo(MIMETYPE_NAME)
    except KeyError as exc:
        raise NotFinaleFileError(f"{path} is a zip archive with no mimetype member") from exc
    if info.file_size > len(MIMETYPE_VALUE) or archive.read(MIMETYPE_NAME) != MIMETYPE_VALUE:
        raise NotFinaleFileError(f"{path} is a zip archive but not a Finale .musx")


def _validated_entries(archive: zipfile.ZipFile) -> tuple[ContainerEntry, ...]:
    infos = archive.infolist()

    if len(infos) > MAX_MEMBERS:
        raise CorruptContainerError(f"archive has too many members: {len(infos)} > {MAX_MEMBERS}")

    seen: set[str] = set()
    total = 0
    entries: list[ContainerEntry] = []
    for info in infos:
        if not is_safe_name(info.filename):
            raise CorruptContainerError(f"unsafe member name: {info.filename!r}")
        if info.filename in seen:
            raise CorruptContainerError(f"duplicate member name: {info.filename!r}")
        seen.add(info.filename)

        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise CorruptContainerError(
                f"total declared size exceeds {MAX_TOTAL_UNCOMPRESSED} bytes"
            )

        entries.append(
            ContainerEntry(
                name=info.filename,
                size=info.file_size,
                compressed_size=info.compress_size,
                compress_type=info.compress_type,
            )
        )
    return tuple(entries)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/container/test_musx.py -v`
Expected: PASS — 18 passed

- [ ] **Step 6: Mutation-verify every safety check**

For each of the five checks below, make the edit, run the named test, confirm it FAILS, then restore the file exactly. Clear caches first: `find . -name __pycache__ -prune -exec rm -rf {} +` and run pytest with `PYTHONDONTWRITEBYTECODE=1`.

| Mutation in `container/musx.py` | Test that must fail |
|---|---|
| Delete the `is_safe_name` check | `test_rejects_unsafe_member_name` |
| Delete the duplicate-name check | `test_rejects_duplicate_member_names` |
| Delete the `MAX_MEMBERS` check | `test_rejects_too_many_members` |
| Delete the `MAX_TOTAL_UNCOMPRESSED` check | `test_rejects_total_size_over_cap` |
| Delete the `max_bytes` check in `read` | `test_read_refuses_member_over_max_bytes` |

Record each result in your report. If any mutation does NOT cause a failure, the test is vacuous — fix the test before proceeding.

- [ ] **Step 7: Run the full gate and commit**

Run: `make check`
Expected: clean.

```bash
git add src/finale_file_parser/container/musx.py tests/container/conftest.py \
        tests/container/test_musx.py
git commit -m "feat: add .musx container reader with structural safety limits"
```

---

### Task 3: Refactor version detection onto the container reader

**Files:**
- Modify: `src/finale_file_parser/version/musx.py`
- Test: `tests/version/test_musx.py` — **must pass untouched**

**Interfaces:**
- Consumes: `open_musx` from `container/musx.py`; `CorruptContainerError` from `container/models.py`.
- Produces: no interface change. `read(path) -> MusxDetail` keeps its exact signature and behaviour.

**The constraint that defines this task:** `tests/version/test_musx.py` and `tests/version/test_detect.py` must pass **without modification**. They are the proof that behaviour did not change. If a test needs editing to accommodate the refactor, that is evidence behaviour changed — stop and report rather than editing the test.

**The subtlety.** `version.musx.read` is deliberately lenient: unparseable *metadata* yields an empty `MusxDetail` rather than raising, so unrecognised variants stay inspectable. `open_musx` is deliberately strict: it raises `CorruptContainerError` on structural violations. Preserving the version module's leniency means catching `CorruptContainerError` at its boundary and degrading to an empty detail — a hostile archive makes version *unknown*, it does not make version detection fail. `NotFinaleFileError` still propagates, because "not a Finale file" is a different claim.

- [ ] **Step 1: Confirm the baseline**

Run: `uv run pytest tests/version -v`
Expected: PASS. Record the count — the same tests must pass at the end.

- [ ] **Step 2: Rewrite `read()` to consume the container**

In `src/finale_file_parser/version/musx.py`, replace the `read` function and delete the now-unused `_require_finale_mimetype` and `_read_capped` helpers, along with the `zipfile` and `NotFinaleFileError` imports if they become unused. Keep every XML helper (`_find`, `_find_block`, `_text`, `_int`, `_app_version`, `_platform`) and `MAX_METADATA_BYTES` exactly as they are.

```python
def read(path: Path) -> MusxDetail:
    """Return the version evidence carried by a .musx archive.

    Raises:
        NotFinaleFileError: `path` opens but is not a valid zip archive, or is
            a zip that does not carry the Finale notation mimetype. A path
            that does not exist raises `FileNotFoundError` instead, unchanged.

    Unparseable *metadata* is not an error: it yields a MusxDetail with empty
    fields, so an unrecognised variant remains inspectable. This covers a
    missing metadata member, one over `MAX_METADATA_BYTES`, one that fails to
    read (e.g. a CRC/decompression error), one that fails to parse as XML, and
    an archive whose structure violates a container safety limit.
    """
    try:
        with open_musx(path) as container:
            try:
                raw: bytes | None = container.read(
                    METADATA_NAME, max_bytes=MAX_METADATA_BYTES
                )
            except (KeyError, CorruptContainerError, zipfile.BadZipFile):
                # Missing, oversized, or unreadable metadata degrades to an
                # empty detail. Only "not a Finale file" raises.
                raw = None
    except CorruptContainerError:
        # A structurally hostile archive makes the version unknown; it does not
        # make version detection fail. Nothing oversized was read to get here.
        return _empty()

    if raw is None:
        return _empty()

    try:
        root = fromstring(raw)
    except (ParseError, DefusedXmlException):
        return _empty()

    modified = _find_block(root, "modified")
    created = _find_block(root, "created")
    return MusxDetail(
        created=_app_version(created),
        modified=_app_version(modified),
        metadata_schema=root.get("version") or "",
        platform=_platform(modified) or _platform(created),
    )


def _empty() -> MusxDetail:
    return MusxDetail(created=None, modified=None, metadata_schema="", platform=None)
```

Add the imports:

```python
from finale_file_parser.container.models import CorruptContainerError
from finale_file_parser.container.musx import open_musx
```

Keep `import zipfile` — it is still needed for the `BadZipFile` catch on a corrupt member.

- [ ] **Step 3: Run the version tests unmodified**

Run: `uv run pytest tests/version -v`
Expected: PASS, same count as Step 1, with **no edits to any test file**.

Confirm with: `git diff --stat tests/` — expected: no output. If any test file appears, stop and report; behaviour changed.

- [ ] **Step 4: Add one test for the new degradation path**

The one genuinely new behaviour is that a structurally hostile archive now yields an empty detail instead of whatever it did before. Append to `tests/version/test_musx.py`:

```python
def test_structurally_hostile_archive_yields_empty_detail(tmp_path: Path) -> None:
    # Duplicate member names trip a container safety limit. Version detection
    # degrades to "unknown" rather than raising — unknown variants stay
    # inspectable.
    path = tmp_path / "hostile.musx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/vnd.makemusic.notation")
        for _ in range(2):
            info = zipfile.ZipInfo("NotationMetadata.xml")
            archive.writestr(info, "<metadata/>")
    detail = read(path)
    assert detail.modified is None
    assert detail.metadata_schema == ""
```

- [ ] **Step 5: Run the full gate and commit**

Run: `make check`
Expected: clean.

```bash
git add src/finale_file_parser/version/musx.py tests/version/test_musx.py
git commit -m "refactor: read .musx version metadata through the container reader"
```

---

### Task 4: Synthetic container fixtures

**Files:**
- Create: `scripts/build_container_fixtures.py`
- Create: `tests/fixtures/container/*.musx` and `tests/fixtures/container/PROFILES.toml` (generated)
- Test: `tests/container/test_fixtures.py`

**Interfaces:**
- Consumes: `open_musx` from `container/musx.py`.
- Produces: 22 committed synthetic archives plus `PROFILES.toml`, whose `[[profile]]` entries carry `file`, `members` (ordered list of `{name, size, compress_type}`), and `source_count` (how many corpus archives shared this shape).

**The content rule for this task — read carefully.** `corpus/` holds copyrighted third-party works. **No payload bytes may be copied from it.** Only structure travels: member names, their order, compression method, and declared uncompressed lengths. Every payload is regenerated as a repeating pattern. This is stricter than the version fixtures, which kept real metadata XML — it has to be, because `score.dat` is the musical work and the corpus also embeds `graphics/*.jpg`, which may be licensed artwork.

The generator must additionally validate every harvested member name against a strict allowlist of known names — unlike the *reader*, which allows unknown-but-safe names. We control what gets committed, so the conservative rule is free here. If a corpus archive carries a name outside the allowlist, the generator must fail loudly rather than emit it: a member named after a piece must not ride along.

- [ ] **Step 1: Write the generator**

Create `scripts/build_container_fixtures.py`:

```python
"""Build synthetic .musx container fixtures from the local corpus.

Run manually when the corpus changes:
    uv run python scripts/build_container_fixtures.py

Only STRUCTURE is harvested — member names, their order, compression method,
and declared uncompressed lengths. Every payload is regenerated as a repeating
pattern, so declared sizes stay realistic while the committed archives stay
small. No payload byte from the corpus is ever written.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

CORPUS = Path("corpus")
OUT = Path("tests/fixtures/container")

ALLOWED_NAME = re.compile(
    r"^(mimetype"
    r"|META-INF/container\.xml"
    r"|NotationMetadata\.xml"
    r"|score\.dat"
    r"|presets/\d+\.preset"
    r"|graphics/\d+\.jpg)$"
)
"""Strict allowlist for HARVESTING. The reader is deliberately more permissive;
here we control what gets committed, so anything unrecognised is a hard stop."""

FILLER = b"FINALE-FIXTURE-SYNTHETIC-PAYLOAD-DO-NOT-INTERPRET-"


def _payload(size: int) -> bytes:
    """Deterministic, highly compressible filler of exactly `size` bytes."""
    if size == 0:
        return b""
    repeats = size // len(FILLER) + 1
    return (FILLER * repeats)[:size]


def _profiles() -> dict[tuple[tuple[str, int, int], ...], int]:
    """Map each distinct ORDERED member shape to how many archives share it."""
    shapes: dict[tuple[tuple[str, int, int], ...], int] = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".musx":
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
        except zipfile.BadZipFile:
            continue
        for info in infos:
            if not ALLOWED_NAME.match(info.filename):
                raise SystemExit(
                    f"refusing to harvest {path.name}: unrecognised member name "
                    f"{info.filename!r}. Widen ALLOWED_NAME only after confirming "
                    f"the name carries no title, composer, or personal data."
                )
        shape = tuple((i.filename, i.file_size, i.compress_type) for i in infos)
        shapes[shape] = shapes.get(shape, 0) + 1
    return shapes


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shapes = _profiles()
    entries: list[str] = []
    for index, (shape, count) in enumerate(sorted(shapes.items()), start=1):
        name = f"variant-{index:02d}.musx"
        target = OUT / name
        with zipfile.ZipFile(target, "w") as archive:
            for member, size, method in shape:
                info = zipfile.ZipInfo(member)
                info.compress_type = method
                archive.writestr(info, _payload(size))
        _assert_structure_matches(target, shape)
        members = "\n".join(
            f'  {{ name = "{m}", size = {s}, compress_type = {c} }},' for m, s, c in shape
        )
        entries.append(
            "[[profile]]\n"
            f'file = "{name}"\n'
            f"source_count = {count}\n"
            f"members = [\n{members}\n]\n"
        )

    (OUT / "PROFILES.toml").write_text(
        "# Generated by scripts/build_container_fixtures.py — do not edit by hand.\n"
        "# Structure harvested from the local corpus; ALL payloads are synthetic.\n\n"
        + "\n".join(entries)
    )
    print(f"wrote {len(entries)} container fixtures to {OUT}")


def _assert_structure_matches(path: Path, shape: tuple[tuple[str, int, int], ...]) -> None:
    with zipfile.ZipFile(path) as archive:
        actual = tuple((i.filename, i.file_size, i.compress_type) for i in archive.infolist())
    if actual != shape:
        raise SystemExit(f"generated {path} does not match its harvested shape")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the fixtures**

Run: `uv run python scripts/build_container_fixtures.py`
Expected: `wrote 22 container fixtures to tests/fixtures/container`

- [ ] **Step 3: Verify no corpus payload was committed**

Run:

```bash
ls -la tests/fixtures/container/ | head -30
du -sh tests/fixtures/container/
python3 -c "
import zipfile, pathlib
FILLER = b'FINALE-FIXTURE-SYNTHETIC-PAYLOAD-DO-NOT-INTERPRET-'
for p in sorted(pathlib.Path('tests/fixtures/container').glob('*.musx')):
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            data = z.read(name)
            assert not data or data == (FILLER * (len(data)//len(FILLER)+1))[:len(data)], (p, name)
print('every payload in every fixture is synthetic filler')
"
```

Expected: total size well under 1 MB, and the assertion prints its confirmation. If any payload is not filler, stop and fix the generator.

- [ ] **Step 4: Write the fixture tests**

Create `tests/container/test_fixtures.py`:

```python
import tomllib
import zipfile
from pathlib import Path

import pytest

from finale_file_parser.container.musx import open_musx

FIXTURES = Path(__file__).parent.parent / "fixtures" / "container"
PROFILES = FIXTURES / "PROFILES.toml"
FILLER = b"FINALE-FIXTURE-SYNTHETIC-PAYLOAD-DO-NOT-INTERPRET-"


def _profiles() -> list[dict[str, object]]:
    with PROFILES.open("rb") as handle:
        return tomllib.load(handle)["profile"]


def test_all_twenty_two_variants_are_present() -> None:
    assert len(_profiles()) == 22
    on_disk = {p.name for p in FIXTURES.glob("*.musx")}
    assert on_disk == {str(profile["file"]) for profile in _profiles()}


@pytest.mark.parametrize("profile", _profiles(), ids=lambda p: str(p["file"]))
def test_fixture_enumerates_exactly_its_declared_structure(profile: dict[str, object]) -> None:
    members = profile["members"]
    assert isinstance(members, list)
    with open_musx(FIXTURES / str(profile["file"])) as container:
        actual = [(e.name, e.size, e.compress_type) for e in container.entries]
    expected = [(m["name"], m["size"], m["compress_type"]) for m in members]
    assert actual == expected


@pytest.mark.parametrize("profile", _profiles(), ids=lambda p: str(p["file"]))
def test_fixture_yields_a_score_stream_of_declared_length(profile: dict[str, object]) -> None:
    members = profile["members"]
    assert isinstance(members, list)
    declared = next(m["size"] for m in members if m["name"] == "score.dat")
    with open_musx(FIXTURES / str(profile["file"])) as container:
        assert len(container.score_stream()) == declared


def test_mimetype_is_first_and_stored_in_every_fixture() -> None:
    fixtures = sorted(FIXTURES.glob("*.musx"))
    assert fixtures, "no fixtures found"
    for path in fixtures:
        with open_musx(path) as container:
            first = container.entries[0]
        assert first.name == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED


def test_no_fixture_contains_a_non_synthetic_payload() -> None:
    fixtures = sorted(FIXTURES.glob("*.musx"))
    assert fixtures, "no fixtures found"
    for path in fixtures:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                data = archive.read(name)
                if not data:
                    continue
                expected = (FILLER * (len(data) // len(FILLER) + 1))[: len(data)]
                assert data == expected, f"{path.name}:{name} is not synthetic filler"
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/container/test_fixtures.py -v`
Expected: PASS — 47 passed (22 + 22 parametrised, plus 3 structural).

- [ ] **Step 6: Run the full gate and commit**

Run: `make check` — expected clean. Run `git status` and confirm nothing under `corpus/` is staged.

```bash
git add scripts/build_container_fixtures.py tests/fixtures/container \
        tests/container/test_fixtures.py
git commit -m "test: add synthetic .musx container fixtures from corpus structure"
```

---

### Task 5: Extend the corpus sweep

**Files:**
- Create: `tests/container/test_corpus_sweep.py`

**Interfaces:**
- Consumes: `open_musx` from `container/musx.py`.
- Produces: nothing importable — a regression net only.

Skips entirely when `corpus/` is absent, so CI stays green without it. Expected values come from the design spec's findings table.

- [ ] **Step 1: Write the test**

Create `tests/container/test_corpus_sweep.py`:

```python
"""Sweep the full local corpus through the container reader.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted
third-party material and is gitignored; these assertions are the only check
against real archives. Expected values come from
docs/superpowers/specs/2026-07-21-musx-container-design.md.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from finale_file_parser.container.musx import SCORE_NAME, open_musx

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401
EXPECTED_VARIANTS = 22
MIN_MEMBERS, MAX_MEMBERS_OBSERVED = 5, 10


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_archive_opens_and_enumerates() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES
    for path in paths:
        with open_musx(path) as container:
            assert MIN_MEMBERS <= len(container.entries) <= MAX_MEMBERS_OBSERVED, path
            assert container.entries[0].name == "mimetype", path
            assert container.entries[0].compress_type == zipfile.ZIP_STORED, path


def test_every_archive_yields_a_score_stream_of_declared_length() -> None:
    paths = _archives()
    assert paths
    for path in paths:
        with zipfile.ZipFile(path) as raw:
            declared = raw.getinfo(SCORE_NAME).file_size
        with open_musx(path) as container:
            assert len(container.score_stream()) == declared, path


def test_corpus_still_has_the_expected_number_of_ordered_variants() -> None:
    shapes = set()
    for path in _archives():
        with zipfile.ZipFile(path) as raw:
            shapes.add(tuple(i.filename for i in raw.infolist()))
    assert len(shapes) == EXPECTED_VARIANTS


def test_no_corpus_archive_trips_a_safety_limit() -> None:
    # None of the defences fire on real files. If this ever fails, either the
    # corpus gained a hostile file or a cap is too tight — investigate before
    # loosening anything.
    paths = _archives()
    assert paths
    for path in paths:
        with open_musx(path):
            pass
```

- [ ] **Step 2: Run with the corpus present**

Run: `uv run pytest tests/container/test_corpus_sweep.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 3: Verify it skips without the corpus**

Run: `mv corpus /tmp/corpus-parked && uv run pytest tests/container/test_corpus_sweep.py -v; mv /tmp/corpus-parked corpus`
Expected: 4 skipped, then the corpus is restored. **Confirm `ls corpus` succeeds and reports 639 files afterwards** — it is the user's data and is not in git.

- [ ] **Step 4: Commit**

```bash
git add tests/container/test_corpus_sweep.py
git commit -m "test: sweep the local corpus through the container reader"
```

---

### Task 6: Update project documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/DECISIONS.md`

**Interfaces:** none. Documentation only. Do not change code.

- [ ] **Step 1: Record the container layout in ARCHITECTURE.md**

Add to the Modules section:

```markdown
- `src/finale_file_parser/container/` — owns all `.musx` archive access. `models.py`
  (`ContainerEntry`, `CorruptContainerError`), `names.py` (member-name safety), `musx.py`
  (`open_musx`, `MusxContainer`). `version/musx.py` is a client of this module; nothing else
  opens archives directly.
```

Add a subsection under the format facts:

```markdown
### Known format facts — the .musx container

Evidence: all 401 corpus archives, surveyed 2026-07-21. See
`docs/superpowers/specs/2026-07-21-musx-container-design.md`.

- A `.musx` is a zip. `mimetype` is always the **first** member and always **stored
  uncompressed** (401/401) — the ODF/EPUB convention. Member order is structural; do not
  assume alphabetical.
- Members observed: `mimetype`, `META-INF/container.xml`, `NotationMetadata.xml`, `score.dat`,
  `presets/<n>.preset`, `graphics/<n>.jpg`. Archives embed images, so container content is not
  limited to notation.
- Member count 5-10; per-archive uncompressed total 89 KB - 420 KB; `score.dat` 86 KB - 413 KB.
- 22 distinct **ordered** member shapes. (Comparing *sorted* sets gives 18 and discards ordering,
  which is meaningful here.)
- `score.dat` is high-entropy obfuscated data and barely compresses. It is extracted, never
  interpreted, at this layer.
- No corpus archive has duplicate or unsafe member names, so the reader's safety checks cannot be
  exercised by real files — they are covered by synthetic hostile input and verified by mutation.
```

- [ ] **Step 2: Correct the stale Phase 1 items in ROADMAP.md**

Replace the Phase 1 checklist with:

```markdown
- [x] Version detection for `.mus` and `.musx` (`detect_version`). Landed ahead of the container
      reader below.
- [x] `open_musx(path)` — open and structurally validate a `.musx` container. Raises
      `NotFinaleFileError` (not a Finale file) or `CorruptContainerError` (a Finale file violating
      a safety limit). The earlier `InvalidFinaleFile` name was dropped in favour of reusing the
      existing error type.
- [x] Enumerate the container's entries (name, declared size, compressed size, method) in archive
      order.
- [x] Extract the score stream as bytes, with size caps applied before reading.
- [x] Synthetic container fixtures harvested from corpus *structure* — this replaced "author a
      public-domain fixture", which needed a working Finale install. Structure-only harvesting is
      what makes CI coverage possible without committing a real score.
- [x] Document the container layout in `docs/ARCHITECTURE.md`, with evidence.
```

- [ ] **Step 3: Record the decisions in DECISIONS.md**

Add at the top of the entry list:

```markdown
## 2026-07-21 — DECIDED: one module owns archive access

`container/` owns opening, validating, and reading `.musx` archives. `version/musx.py` is a client.
Reason: the two had parallel implementations of the same zip-safety logic, which can drift; a
single owner means one place to harden.

## 2026-07-21 — DECIDED: reject unsafe member names, allow unknown ones

The container reader raises only on genuinely dangerous names (absolute, `..` segments,
backslashes, control characters). A merely *unfamiliar* name is surfaced as data. Reason: rejecting
unrecognised archives would contradict the principle that unknown variants stay inspectable, and
would make a new Finale member name break version detection outright. The fixture generator keeps a
strict allowlist, because we control what gets committed.

## 2026-07-21 — DECIDED: container fixtures carry structure only

Committed `.musx` fixtures harvest member names, order, compression method and declared lengths
from the corpus, and regenerate every payload. Reason: `score.dat` is the musical work and the
corpus also embeds `graphics/*.jpg` which may be licensed artwork. Payload bytes never leave the
gitignored corpus.
```

- [ ] **Step 4: Run the gate and commit**

Run: `make check` — expected clean (documentation-only, but confirm nothing broke).

```bash
git add docs
git commit -m "docs: record .musx container layout and decisions"
```

---

## Completion

After Task 6, open a pull request. This repo requires **all** changes to go through a PR and never
commits to `main` directly.

```bash
git push -u origin feat/musx-container
gh pr create --base main --title "feat: .musx container reader" --body "..."
```

The PR body should state: what landed; that `version/musx.py`'s existing tests passed untouched as
proof the refactor changed no behaviour; the mutation-verification results for all five safety
checks; that the corpus sweep ran locally against 401 archives and skips in CI; and that no corpus
payload bytes are committed.
