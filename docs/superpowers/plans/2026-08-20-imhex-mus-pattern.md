# ImHex `.mus` Pattern Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `finale-parser extract` writes one framed `.pools.bin` per score, and a generated ImHex
pattern walks it end to end — every pool, every record, at the catalog's offsets.

**Architecture:** A new `enigma/pool_file.py` writes and reads the framed file: an 8-byte header
(magic, version, byte order, era, pool count) followed by the DCL container's own
kind/length/checksum chain with each payload decompressed in place. `cli.py` gains an `extract`
verb over it. `scripts/hexpat/` renders `docs/formats/finale-mus.hexpat` from
`formats/layouts.py` — the same catalog the parser, the report and the PDF spec read — and a test
pins the committed pattern byte for byte.

**Tech Stack:** Python 3.12, dataclasses, pytest, mypy --strict, ruff. No new dependencies. The
output is ImHex Pattern Language, which nothing in CI can execute.

**Spec:** `docs/superpowers/specs/2026-08-20-imhex-mus-pattern-design.md`

## Global Constraints

- Toolchain is `make` only: `UV_OFFLINE=1 make check` between edits, `UV_OFFLINE=1 make check-full`
  before pushing. Never invoke pytest/ruff/mypy ad hoc as the gate.
- `mypy --strict` must pass. Every new function is fully annotated. Line length 100.
- Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- **Every input file is hostile.** Bounds-check every offset and length read from a file, and cap
  allocations driven by file-supplied sizes. Malformed input raises a clear error, never crashes or
  hangs. `read_pool_file` reads a file this project wrote, and is still not permitted to trust it.
- **No fabricated facts.** A pool kind that cannot be identified is refused, never guessed. A record
  type with no layout is shown as raw bytes, never given an invented structure.
- **`Layout.computed` layouts must not be laid over real bytes.** `FrameSpec` and `GfHold` carry it;
  `report/model.py:686` already honours it and the generator must too.
- Never `git add -A` — a `corpus` symlink is present and untracked. Add explicit paths.
- `corpus/` is gitignored and absent in CI. Corpus tests carry the existing skip marker; unit tests
  must not need a corpus.
- Report counts only in test output — never a corpus filename, title, or record value.

## Existing interfaces this plan consumes

Verbatim from the source, so no task has to guess:

```python
# enigma/mus_payload.py
POOL_OTHERS, POOL_DETAILS, POOL_ENTRIES, POOL_TEXT = 15, 16, 17, 18
MAX_MUS_PAYLOAD = 64 * 1024 * 1024
ByteOrder = Literal["little", "big"]

@dataclass(frozen=True)
class MusPool:
    data: bytes
    byte_order: ByteOrder = "little"
    kind: int | None = None          # None where the container does not label its pools

read_mus_pools(path) -> tuple[MusPool, ...]      # raises CorruptScoreError

# enigma/mus_others.py
_walk(stream: bytes) -> tuple[MusOther, ...] | None    # None when not an others pool
_MIN_RECORDS = 50

# enigma/mus_details.py
_walk(stream: bytes) -> tuple[MusDetailRecord, ...] | None
_MIN_RECORDS = 50

# enigma/mus_entries.py
_looks_like_entry_pool(stream: bytes, order: ByteOrder = "little") -> bool

# enigma/models.py
class CorruptScoreError(FinaleFileError)

# formats/layouts.py
LAYOUTS: tuple[Layout, ...]          # all 12
Layout(name, record, tag: int, dcl: str, pool: str, fields: tuple[Field, ...],
       stride: int = 0, computed: bool = False)
Field(offset: int, size: int, name: str, type_: str, note: str = "")
Field.is_tail -> bool                # size == 0

# cli.py
PROGRAM, EXIT_OK, EXIT_FAILURES, EXIT_USAGE
source_paths(root: Path) -> list[Path]
output_path(source: Path, root: Path, destination: Path | None, suffix: str = _OUTPUT_SUFFIX) -> Path
_clobber_reason(target: Path, force: bool) -> str | None
_reason(error: Exception) -> str
```

---

### Task 1: The framed pool file — write and read

**Files:**
- Create: `src/finale_file_parser/enigma/pool_file.py`
- Test: `tests/enigma/test_pool_file.py`

**Interfaces:**
- Consumes: `MusPool`, `ByteOrder`, `CorruptScoreError` from `enigma`.
- Produces:
  ```python
  MAGIC: bytes          # b"FMUS"
  VERSION: int          # 1
  HEADER_SIZE: int      # 8
  ENTRY_HEADER_SIZE: int  # 10
  EMPTY_ENTRY_LENGTH: int # 6
  ERA_ZLIB: int         # 0
  ERA_DCL: int          # 1

  @dataclass(frozen=True)
  class PoolFile:
      version: int
      byte_order: ByteOrder
      era: int
      pools: tuple[MusPool, ...]

  write_pool_file(pools: tuple[MusPool, ...], *, era: int) -> bytes
  read_pool_file(data: bytes) -> PoolFile      # raises CorruptScoreError
  ```

- [ ] **Step 1: Write the failing round-trip test**

Create `tests/enigma/test_pool_file.py`:

```python
"""The framed file `finale-parser extract` writes.

The chain is the DCL container's own -- kind, length, checksum, laid end to
end, with `length` counting its own header -- so a reader of this file walks it
exactly as a reader of a `.mus` walks the real thing. What differs is that the
payloads are decompressed and a magic header says so.

The round-trip test is the one that matters. A framing bug that shifted a
payload by one byte would pass every other assertion here and produce a hex
dump that is wrong in a way a reader would trust.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    MusPool,
)
from finale_file_parser.enigma.pool_file import (
    EMPTY_ENTRY_LENGTH,
    ERA_DCL,
    ERA_ZLIB,
    HEADER_SIZE,
    MAGIC,
    VERSION,
    read_pool_file,
    write_pool_file,
)


def _pools(order: str = "little") -> tuple[MusPool, ...]:
    return (
        MusPool(data=b"\x01\x02\x03\x04", byte_order=order, kind=POOL_OTHERS),
        MusPool(data=b"\xaa" * 40, byte_order=order, kind=POOL_DETAILS),
        MusPool(data=b"", byte_order=order, kind=POOL_ENTRIES),
        MusPool(data=b"text", byte_order=order, kind=POOL_TEXT),
    )


def test_pools_survive_a_round_trip() -> None:
    written = write_pool_file(_pools(), era=ERA_DCL)
    back = read_pool_file(written)
    assert back.era == ERA_DCL
    assert back.byte_order == "little"
    assert back.version == VERSION
    assert [(p.kind, p.data) for p in back.pools] == [(p.kind, p.data) for p in _pools()]


def test_a_big_endian_document_round_trips_too() -> None:
    """37 of the 139 DCL-era corpus documents are big-endian, so this is not a
    rare branch. Reading it the wrong way round yields plausible nonsense."""
    written = write_pool_file(_pools("big"), era=ERA_DCL)
    back = read_pool_file(written)
    assert back.byte_order == "big"
    assert [p.data for p in back.pools] == [p.data for p in _pools("big")]


def test_the_header_announces_the_file() -> None:
    written = write_pool_file(_pools(), era=ERA_ZLIB)
    assert written[:4] == MAGIC, "the file must not impersonate a .mus"
    assert written[4] == VERSION
    assert written[5] == 0, "0 is little-endian"
    assert written[6] == ERA_ZLIB
    assert written[7] == 4


def test_an_empty_pool_keeps_its_shape() -> None:
    """`length == 6` is how the container itself says a pool exists and holds
    nothing -- three corpus documents carry an empty entry pool that way. A
    missing pool and an empty one mean different things."""
    written = write_pool_file(_pools(), era=ERA_DCL)
    back = read_pool_file(written)
    empty = [p for p in back.pools if p.kind == POOL_ENTRIES][0]
    assert empty.data == b""

    # and the entry on the wire is the short form
    offset = HEADER_SIZE
    for pool in _pools()[:2]:
        offset += 10 + len(pool.data)
    length = int.from_bytes(written[offset + 2 : offset + 6], "little")
    assert length == EMPTY_ENTRY_LENGTH


def test_an_unlabelled_pool_is_refused() -> None:
    """A pool whose kind was never identified must not be written with a guess."""
    with pytest.raises(ValueError):
        write_pool_file((MusPool(data=b"x", kind=None),), era=ERA_ZLIB)


@pytest.mark.parametrize(
    "mangle",
    [
        pytest.param(lambda b: b[:3], id="truncated-magic"),
        pytest.param(lambda b: b"XXXX" + b[4:], id="wrong-magic"),
        pytest.param(lambda b: b[:4] + bytes([VERSION + 9]) + b[5:], id="future-version"),
        pytest.param(lambda b: b[: HEADER_SIZE + 4], id="truncated-chain"),
        pytest.param(lambda b: b[:6] + b"\x09" + b[7:], id="unknown-era"),
    ],
)
def test_a_malformed_file_raises_rather_than_guessing(
    mangle: Callable[[bytes], bytes],
) -> None:
    """This file is one we wrote, and it is still untrusted input."""
    with pytest.raises(CorruptScoreError):
        read_pool_file(mangle(write_pool_file(_pools(), era=ERA_DCL)))


def test_a_declared_length_beyond_the_data_is_refused() -> None:
    """The length field is the one number a hostile file controls. Believing it
    is how a reader is made to allocate or read past its buffer."""
    written = bytearray(write_pool_file(_pools(), era=ERA_DCL))
    written[HEADER_SIZE + 2 : HEADER_SIZE + 6] = (1 << 30).to_bytes(4, "little")
    with pytest.raises(CorruptScoreError):
        read_pool_file(bytes(written))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/enigma/test_pool_file.py -q`
Expected: collection error, `ModuleNotFoundError: finale_file_parser.enigma.pool_file`.

- [ ] **Step 3: Write the module**

Create `src/finale_file_parser/enigma/pool_file.py`:

```python
"""The framed file `finale-parser extract` writes, and reads back.

A `.mus` keeps its payload as four compressed pools, and a hex editor sees only
the compressed bytes. This file is those pools decompressed, in one piece, laid
out so a reader can walk them without decompressing anything.

**The chain is the container's own.** A 2001-2005 `.mus` already stores its
payload as a run of records -- kind, length, checksum -- laid end to end from
`0x200` with no gaps, where `length` counts its own ten-byte header. This file
keeps exactly that shape, so what a reader learns from walking it is true of
the format rather than true of us. Two things differ, and only two: each
payload is decompressed, so `length` is the decompressed size; and an 8-byte
header is prepended so the file announces what it is instead of impersonating a
score.

**The checksum is always zero.** The container's checksum covers the
*compressed* stream, which this file does not contain, so carrying it across
would invite a reader to verify it against bytes it never described. The field
is kept because the chain's shape is the point; its value is not.

A 2011-era `.mus` has no pool chain at all -- its pools are bare zlib streams --
so for those documents the framing is borrowed rather than preserved. The
header's `era` byte says which case a reader is looking at.
"""

from __future__ import annotations

from dataclasses import dataclass

from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_payload import MAX_MUS_PAYLOAD, ByteOrder, MusPool

__all__ = [
    "EMPTY_ENTRY_LENGTH",
    "ENTRY_HEADER_SIZE",
    "ERA_DCL",
    "ERA_ZLIB",
    "HEADER_SIZE",
    "MAGIC",
    "VERSION",
    "PoolFile",
    "era_of",
    "read_pool_file",
    "write_pool_file",
]

MAGIC = b"FMUS"
"""Four bytes that say this is not a `.mus`.

A derived file that looked like the real thing would eventually be opened as
one, and every offset in it would be wrong by eight bytes and a decompression.
"""

VERSION = 1
HEADER_SIZE = 8
"""magic (4) + version (1) + order (1) + era (1) + pool count (1).

Every field is a single byte, so the header itself has no byte order to get
wrong -- which matters, because the byte order of everything after it is what
byte 5 announces.
"""

ENTRY_HEADER_SIZE = 10
"""kind (2) + length (4) + checksum (4), as the container writes it."""

EMPTY_ENTRY_LENGTH = 6
"""A `length` of exactly 6 means kind and length and nothing else -- no
checksum, no payload. The container's own way of saying a pool exists and is
empty, which three corpus documents use for their entry pool."""

ERA_ZLIB = 0
ERA_DCL = 1

_MAX_POOLS = 64
"""Refuse a file claiming more pools than any real document has.

Every corpus document has exactly four. The cap is defence in depth: the count
is a file-supplied number that sizes a loop.
"""


@dataclass(frozen=True)
class PoolFile:
    """A framed file, read back."""

    version: int
    byte_order: ByteOrder
    era: int
    pools: tuple[MusPool, ...]


def era_of(pools: tuple[MusPool, ...]) -> int:
    """Which container these pools came out of.

    A DCL container labels its pools and a zlib-era one does not, so a labelled
    first pool is the era, stated by the container rather than guessed.
    """
    return ERA_DCL if pools and pools[0].kind is not None else ERA_ZLIB


def _int(value: int, size: int, order: ByteOrder) -> bytes:
    return value.to_bytes(size, order)


def write_pool_file(pools: tuple[MusPool, ...], *, era: int) -> bytes:
    """Frame `pools` as one file.

    Raises:
        ValueError: a pool has no `kind`, or there are too many pools. An
            unidentified pool is refused rather than written with a guessed
            label -- a wrong kind in this header sends a reader to the wrong
            record shape and everything after it is confident nonsense.
    """
    if not pools:
        raise ValueError("no pools to write")
    if len(pools) > _MAX_POOLS:
        raise ValueError(f"{len(pools)} pools exceeds the {_MAX_POOLS} this format allows")
    if era not in (ERA_ZLIB, ERA_DCL):
        raise ValueError(f"unknown era {era!r}")

    order: ByteOrder = pools[0].byte_order
    out = bytearray(MAGIC)
    out.append(VERSION)
    out.append(1 if order == "big" else 0)
    out.append(era)
    out.append(len(pools))

    for pool in pools:
        if pool.kind is None:
            raise ValueError("a pool with no identified kind cannot be written")
        out += _int(pool.kind, 2, order)
        if not pool.data:
            out += _int(EMPTY_ENTRY_LENGTH, 4, order)
            continue
        out += _int(ENTRY_HEADER_SIZE + len(pool.data), 4, order)
        out += _int(0, 4, order)
        out += pool.data
    return bytes(out)


def read_pool_file(data: bytes) -> PoolFile:
    """Walk a framed file back into pools.

    This reads a file this project wrote, and still does not trust it: every
    length is bounds-checked before it is used, because the alternative is a
    reader that can be made to walk past its own buffer by a number in a file.

    Raises:
        CorruptScoreError: the header is wrong, the version is not one this
            reader knows, or the chain does not tile the data exactly.
    """
    if len(data) < HEADER_SIZE:
        raise CorruptScoreError("not a pool file: shorter than its header")
    if data[:4] != MAGIC:
        raise CorruptScoreError("not a pool file: wrong magic")
    version = data[4]
    if version != VERSION:
        raise CorruptScoreError(f"pool file version {version} is not version {VERSION}")
    order: ByteOrder = "big" if data[5] else "little"
    era = data[6]
    if era not in (ERA_ZLIB, ERA_DCL):
        raise CorruptScoreError(f"pool file names an unknown era {era}")
    count = data[7]
    if not 0 < count <= _MAX_POOLS:
        raise CorruptScoreError(f"pool file claims {count} pools")

    pools: list[MusPool] = []
    at = HEADER_SIZE
    for _ in range(count):
        if at + 6 > len(data):
            raise CorruptScoreError("pool file ends inside a chain entry header")
        kind = int.from_bytes(data[at : at + 2], order)
        length = int.from_bytes(data[at + 2 : at + 6], order)
        if length == EMPTY_ENTRY_LENGTH:
            pools.append(MusPool(data=b"", byte_order=order, kind=kind))
            at += 6
            continue
        if length < ENTRY_HEADER_SIZE or length > MAX_MUS_PAYLOAD:
            raise CorruptScoreError(f"pool file entry claims {length} bytes")
        if at + length > len(data):
            raise CorruptScoreError("pool file entry runs past the end of the file")
        start = at + ENTRY_HEADER_SIZE
        pools.append(MusPool(data=data[start : at + length], byte_order=order, kind=kind))
        at += length

    if at != len(data):
        raise CorruptScoreError(f"pool file has {len(data) - at} bytes after its last pool")
    return PoolFile(version=version, byte_order=order, era=era, pools=tuple(pools))
```

- [ ] **Step 4: Run the tests**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/enigma/test_pool_file.py -q`
Expected: PASS.

- [ ] **Step 5: Prove the round-trip test earns its place**

Change `write_pool_file`'s payload append to `out += pool.data + b"\x00"`, run the tests, and
confirm `test_pools_survive_a_round_trip` fails. Restore the line and confirm `git diff` is clean.
A test that passes with the framing broken is worth nothing here.

- [ ] **Step 6: Gate and commit**

```bash
UV_OFFLINE=1 make check
git add src/finale_file_parser/enigma/pool_file.py tests/enigma/test_pool_file.py
git commit -m "feat: frame decompressed .mus pools as one file"
```

---

### Task 2: Identify the pools a zlib-era container does not label

**Files:**
- Modify: `src/finale_file_parser/enigma/pool_file.py`
- Test: `tests/enigma/test_pool_file.py`

**Interfaces:**
- Consumes: `MusPool`; `mus_others._walk`, `mus_details._walk`,
  `mus_entries._looks_like_entry_pool`.
- Produces: `identify_pools(pools: tuple[MusPool, ...]) -> tuple[MusPool, ...]`

- [ ] **Step 1: Write the failing test**

Append to `tests/enigma/test_pool_file.py`:

```python
def test_labelled_pools_are_left_alone() -> None:
    """A DCL container states its pool kinds. Sniffing over the top of that
    could only ever disagree with the file about its own contents."""
    from finale_file_parser.enigma.pool_file import identify_pools

    given = _pools()
    assert [p.kind for p in identify_pools(given)] == [p.kind for p in given]


def test_an_unidentifiable_pool_set_is_refused() -> None:
    """Better no file than a file whose labels are guesses: the kind in the
    header is what sends a reader to a record shape."""
    from finale_file_parser.enigma.pool_file import identify_pools

    unlabelled = tuple(
        MusPool(data=b"\x00" * 64, byte_order="little", kind=None) for _ in range(4)
    )
    with pytest.raises(CorruptScoreError):
        identify_pools(unlabelled)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/enigma/test_pool_file.py -q -k identif`
Expected: FAIL, `ImportError: cannot import name 'identify_pools'`.

- [ ] **Step 3: Implement it**

Add to `src/finale_file_parser/enigma/pool_file.py`:

```python
def identify_pools(pools: tuple[MusPool, ...]) -> tuple[MusPool, ...]:
    """Fill in the `kind` of pools whose container did not label them.

    A DCL container names all four pools; a 2011-era one names none. The kinds
    are recoverable anyway, because each reader already carries a test for
    "is this my pool?" and uses it to pick a stream:

    - `mus_others._walk` returns None unless the stream is an others pool.
    - `mus_details._walk` returns None unless it is a details pool.
    - `mus_entries._looks_like_entry_pool` is the same test for entries.

    Measured over all 99 zlib-era corpus documents: others, details and entries
    identify positively in 99 of 99, with no stream matching two tests. The
    fourth pool is the text pool **by elimination** -- there is no positive test
    for it -- which agrees with the order the DCL container states outright
    (15, 16, 17, 18).

    That is why the elimination is only allowed once. If two pools were left
    unidentified the fourth would be a coin toss, and a wrong kind here is not a
    missing label: it points a reader at the wrong record shape and every field
    after it reads as confident nonsense.

    Raises:
        CorruptScoreError: more than one pool could not be identified, or two
            tests claimed the same pool.
    """
    from finale_file_parser.enigma import mus_details, mus_others
    from finale_file_parser.enigma.mus_entries import _looks_like_entry_pool

    if all(pool.kind is not None for pool in pools):
        return pools

    out: list[MusPool] = []
    unknown: list[int] = []
    for index, pool in enumerate(pools):
        if pool.kind is not None:
            out.append(pool)
            continue
        others = mus_others._walk(pool.data)
        details = mus_details._walk(pool.data)
        claims = []
        if others is not None and len(others) >= mus_others._MIN_RECORDS:
            claims.append(POOL_OTHERS)
        if details is not None and len(details) >= mus_details._MIN_RECORDS:
            claims.append(POOL_DETAILS)
        if _looks_like_entry_pool(pool.data, pool.byte_order):
            claims.append(POOL_ENTRIES)
        if len(claims) > 1:
            raise CorruptScoreError(
                f"pool {index} matches {len(claims)} pool tests, so neither can be trusted"
            )
        if claims:
            out.append(MusPool(data=pool.data, byte_order=pool.byte_order, kind=claims[0]))
            continue
        unknown.append(len(out))
        out.append(pool)

    if len(unknown) > 1:
        raise CorruptScoreError(
            f"{len(unknown)} pools could not be identified; only one may be inferred"
        )
    for index in unknown:
        pool = out[index]
        out[index] = MusPool(data=pool.data, byte_order=pool.byte_order, kind=POOL_TEXT)
    return tuple(out)
```

Add `"identify_pools"` to `__all__`, and add `POOL_DETAILS`, `POOL_ENTRIES`, `POOL_OTHERS`,
`POOL_TEXT` to the existing `mus_payload` import at the top of the module.

- [ ] **Step 4: Run the tests**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/enigma/test_pool_file.py -q`
Expected: PASS.

- [ ] **Step 5: Gate and commit**

```bash
UV_OFFLINE=1 make check
git add src/finale_file_parser/enigma/pool_file.py tests/enigma/test_pool_file.py
git commit -m "feat: identify the pools a 2011-era .mus does not label"
```

---

### Task 3: `finale-parser extract`

**Files:**
- Modify: `src/finale_file_parser/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `read_mus_pools`, `identify_pools`, `write_pool_file`, `era_of`.
- Produces: an `extract` subcommand writing `<stem>.pools.bin`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_extract_writes_one_file_per_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One file, not one per pool: the pools stay delimited by the chain's own
    headers rather than by being separate files."""
    from finale_file_parser.enigma.mus_payload import POOL_OTHERS, MusPool

    monkeypatch.setattr(
        cli, "read_mus_pools", lambda p: (MusPool(data=b"abc", kind=POOL_OTHERS),)
    )
    source = touch(tmp_path / "a.mus")
    assert cli.main(["extract", str(source)]) == cli.EXIT_OK
    written = (tmp_path / "a.pools.bin").read_bytes()
    assert written[:4] == b"FMUS"


def test_extract_refuses_musx_by_name(tmp_path: Path) -> None:
    """A .musx is a ZIP of encrypted XML with no pools of this kind. Saying so
    is more use than a decode error from three layers down."""
    source = touch(tmp_path / "a.musx")
    assert cli.main(["extract", str(source)]) == cli.EXIT_FAILURES
    assert not (tmp_path / "a.pools.bin").exists()


def test_extract_refuses_to_overwrite_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finale_file_parser.enigma.mus_payload import POOL_OTHERS, MusPool

    monkeypatch.setattr(
        cli, "read_mus_pools", lambda p: (MusPool(data=b"abc", kind=POOL_OTHERS),)
    )
    source = touch(tmp_path / "a.mus")
    existing = tmp_path / "a.pools.bin"
    existing.write_bytes(b"MINE")
    assert cli.main(["extract", str(source)]) == cli.EXIT_FAILURES
    assert existing.read_bytes() == b"MINE"
    assert cli.main(["extract", str(source), "--force"]) == cli.EXIT_OK
    assert existing.read_bytes() != b"MINE"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/test_cli.py -q -k extract`
Expected: FAIL — `argparse` exits because `extract` is not a subcommand.

- [ ] **Step 3: Add the subcommand**

In `src/finale_file_parser/cli.py`:

Add to the imports:

```python
from finale_file_parser.enigma.mus_payload import read_mus_pools
from finale_file_parser.enigma.pool_file import era_of, identify_pools, write_pool_file
```

Add beside `FORMATS`:

```python
_POOLS_SUFFIX = ".pools.bin"
"""Not `.bin` alone: a name should say what opening it will show."""
```

Add the function, next to `_convert`:

```python
def _extract(args: argparse.Namespace, out: object) -> int:
    """Write each score's decompressed pools as one framed file."""
    root: Path = args.input
    sources = source_paths(root)
    if not sources:
        print(f"{PROGRAM}: no .mus or .musx files under {root}", file=sys.stderr)
        return EXIT_USAGE

    written = 0
    failures: list[tuple[Path, str]] = []
    for source in sources:
        if source.suffix.lower() == ".musx":
            failures.append((source, "a .musx has no compressed pools to extract"))
            continue
        target = output_path(source, root, args.output, _POOLS_SUFFIX)
        reason = _clobber_reason(target, args.force)
        if reason:
            failures.append((source, reason))
            continue
        try:
            pools = identify_pools(read_mus_pools(source))
            data = write_pool_file(pools, era=era_of(pools))
        except (FinaleFileError, ValueError) as error:
            failures.append((source, _reason(error)))
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as error:
            failures.append((source, _reason(error)))
            continue
        written += 1
        if args.verbose:
            print(f"{source} -> {target}", file=out)  # type: ignore[call-overload]

    if len(sources) > 1 or failures:
        print(f"{written}/{len(sources)} extracted", file=out)  # type: ignore[call-overload]
    for source, reason in failures:
        print(f"  skipped {source}: {reason}", file=sys.stderr)
    return EXIT_FAILURES if failures else EXIT_OK
```

Register it in `_parser()`, after the `inspect` parser:

```python
    extract = sub.add_parser(
        "extract", help="write a .mus file's decompressed pools as one binary"
    )
    extract.add_argument("input", type=Path, help="a .mus file, or a directory of them")
    extract.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output file, or directory for a batch; defaults to beside the input",
    )
    extract.add_argument(
        "--force", action="store_true", help="overwrite an output file that already exists"
    )
    extract.add_argument("-v", "--verbose", action="store_true", help="name each file written")
```

And dispatch it in `main()`, replacing `return _inspect(args, out)`:

```python
    if args.command == "extract":
        return _extract(args, out)
    return _inspect(args, out)
```

**Note on `output_path`:** it calls `Path.with_suffix`, which replaces only the final suffix, so
`a.mus` with `.pools.bin` yields `a.pools.bin` but `a.tune.mus` would yield `a.tune.pools.bin` —
which is correct. Verify with the test above rather than by reading.

- [ ] **Step 4: Run the tests**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/test_cli.py -q`
Expected: PASS, including every pre-existing CLI test.

- [ ] **Step 5: Gate and commit**

```bash
UV_OFFLINE=1 make check
git add src/finale_file_parser/cli.py tests/test_cli.py
git commit -m "feat: add finale-parser extract"
```

---

### Task 4: The pattern generator — header, chain and record shapes

**Files:**
- Create: `scripts/hexpat/__init__.py`, `scripts/hexpat/__main__.py`, `scripts/hexpat/render.py`
- Test: `tests/formats/test_hexpat.py`

**Interfaces:**
- Consumes: `LAYOUTS`, `Layout`, `Field` from `formats.layouts`; the constants from
  `enigma.pool_file`.
- Produces: `render_pattern() -> str` in `scripts/hexpat/render.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/formats/test_hexpat.py`:

```python
"""The generated ImHex pattern.

Nothing here can run the pattern -- ImHex is not installable in CI and there is
no headless evaluator for its language -- so these tests pin what *can* be
checked: that the pattern is generated from the catalog, covers all of it, and
never states an offset the parser does not use. Whether it loads is a hand
check, recorded in the plan.
"""

from __future__ import annotations

from finale_file_parser.enigma.pool_file import HEADER_SIZE, MAGIC
from finale_file_parser.formats.layouts import LAYOUTS
from hexpat.render import HEXPAT_TYPES, render_pattern


def test_the_pattern_reads_the_file_the_extractor_writes() -> None:
    pattern = render_pattern()
    assert MAGIC.decode() in pattern, "does not check the magic"
    assert str(HEADER_SIZE) in pattern or "Header" in pattern


def test_every_field_type_in_the_catalog_maps_to_a_hexpat_type() -> None:
    """A new field type must fail loudly here rather than silently emitting
    nothing into a specification."""
    used = {field.type_ for layout in LAYOUTS for field in layout.fields}
    assert used <= set(HEXPAT_TYPES), f"unmapped field types: {sorted(used - set(HEXPAT_TYPES))}"


def test_the_two_eras_both_appear() -> None:
    """A 2011 pool holds variable-length self-identifying records; a DCL pool
    holds fixed 16-byte rows. One shape cannot describe both."""
    pattern = render_pattern()
    for marker in ("OthersRecord", "DetailsRecord", "DclOthersRow", "DclDetailsRow"):
        assert marker in pattern, f"{marker} missing"


def test_the_pattern_sets_its_endianness_from_the_file() -> None:
    """The order byte is runtime data. 37 of 139 DCL-era corpus documents are
    big-endian, and reading one the wrong way round yields plausible nonsense
    rather than an error."""
    assert "set_endian" in render_pattern()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/formats/test_hexpat.py -q`
Expected: collection error, `ModuleNotFoundError: hexpat.render`. (`pyproject.toml` already puts
`scripts` on `pythonpath` for pytest, so no path change is needed.)

- [ ] **Step 3: Write the generator's skeleton**

Create `scripts/hexpat/__init__.py` (empty file).

Create `scripts/hexpat/render.py`:

```python
"""Render the ImHex pattern for a framed pool file.

Offsets are not written here. Every record layout comes from
`finale_file_parser.formats.layouts`, which the parser and the inspector read
too, so this pattern cannot state an offset the code does not use. What lives
here is the container walk and the two eras' record shapes, which are structure
rather than payload.
"""

from __future__ import annotations

from finale_file_parser.enigma.pool_file import (
    EMPTY_ENTRY_LENGTH,
    ENTRY_HEADER_SIZE,
    HEADER_SIZE,
    MAGIC,
)

HEXPAT_TYPES = {
    "uint8": "u8",
    "uint16": "u16",
    "uint32": "u32",
    "int16": "s16",
    "string": "char",
}
"""Every field type the catalog uses, and the hexpat type that reads it.

`string` maps to `char` because the catalog's only string fields are
NUL-terminated tails, which hexpat writes as `char name[]`.
"""

_PREAMBLE = f'''#pragma description Finale .mus decompressed pools
#pragma magic [ {" ".join(f"{b:02X}" for b in MAGIC)} ] @ 0x00

// GENERATED by scripts/hexpat -- do not edit.
//
// This pattern reads the file `finale-parser extract` writes, NOT a .mus. A
// .mus keeps its pools compressed, and the 2001-2005 era uses PKWARE implode,
// which ImHex cannot decompress. Run:
//
//     finale-parser extract score.mus     -> score.pools.bin
//
// and open that. The chain below is the .mus container's own framing -- kind,
// length, checksum -- with each payload decompressed in place.

import std.core;
import std.mem;

enum PoolKind : u16 {{
    others  = 15,
    details = 16,
    entries = 17,
    text    = 18,
}};

enum Era : u8 {{
    zlib_2011 = 0,
    dcl_2005  = 1,
}};

struct Header {{
    char magic[4];
    u8 version;
    u8 order;          // 0 little, 1 big -- applies to everything after this header
    Era era;
    u8 pools;
}};
'''


def render_pattern() -> str:
    """The whole pattern, as one string."""
    parts = [_PREAMBLE, _record_shapes(), _payload_structs(), _entry_point()]
    return "\n".join(parts)


def _record_shapes() -> str:
    """The two eras' record framings.

    These are not in the catalog because they are container structure rather
    than payload: the catalog describes what is *inside* a record.
    """
    return f'''
// A 2011 pool is a run of self-identifying, variable-length records. One
// occupies 14 + length bytes for `others` and 16 + length for `details`.
struct OthersRecord {{
    u16 tag;
    u16 cmper;
    u16 part;
    u32 length;
    u8 payload[length];
    u8 trailer[4];
}};

struct DetailsRecord {{
    u16 tag;
    u16 cmper1;
    u16 cmper2;
    u16 inci;
    u32 length;
    u8 payload[length];
    u32 extra_length;
    u8 extra[extra_length];
}};

// A 2001-2005 pool is a table of fixed 16-byte rows carrying ETF's
// two-character tags. The tag is a u16, NOT two characters: on a little-endian
// file its letters come out reversed, so `^MS` is stored `SM`. Reading the pair
// verbatim finds no known tag in 102 of 139 corpus documents.
//
// A record too big for one row runs on into further rows under the same tag and
// key -- ETF calls each row an incidence -- so a row is a fragment of a record,
// not a record.
struct DclOthersRow {{
    u16 cmper;
    u16 tag;
    u8 data[12];
}};

struct DclDetailsRow {{
    u16 cmper1;
    u16 cmper2;
    u16 tag;
    u8 data[10];
}};

struct PoolEntry {{
    PoolKind kind;
    u32 length;
    if (length != {EMPTY_ENTRY_LENGTH}) {{
        u32 checksum;   // always 0: the container's checksum covers the
                        // COMPRESSED stream, which this file does not hold
        u8 payload[length - {ENTRY_HEADER_SIZE}];
    }}
}};
'''


def _entry_point() -> str:
    return f'''
Header header @ 0x00;

fn init() {{
    std::core::set_endian(
        header.order == 1 ? std::mem::Endian::Big : std::mem::Endian::Little
    );
}};

init();

PoolEntry pools[header.pools] @ {HEADER_SIZE};
'''


def _payload_structs() -> str:
    """Placeholder until Task 5; returns nothing so Task 4's tests can pass."""
    return ""
```

Create `scripts/hexpat/__main__.py`:

```python
"""Write `docs/formats/finale-mus.hexpat`.

Run through `make hexpat`, never directly, so the output always lands in the
one place the currency test looks for it.
"""

from __future__ import annotations

from pathlib import Path

from .render import render_pattern

OUTPUT = Path("docs/formats/finale-mus.hexpat")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_pattern(), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/formats/test_hexpat.py -q`
Expected: PASS. `LAYOUTS`, `Layout` and `Field` are not imported yet — Task 5 adds them with the
code that uses them, so `ruff` never sees an unused import.

- [ ] **Step 5: Gate and commit**

```bash
UV_OFFLINE=1 make check
git add scripts/hexpat tests/formats/test_hexpat.py
git commit -m "feat: generate the ImHex pattern's container walk"
```

---

### Task 5: The payload structs, from the catalog

**Files:**
- Modify: `scripts/hexpat/render.py`
- Test: `tests/formats/test_hexpat.py`

**Interfaces:**
- Consumes: `LAYOUTS`, `Layout`, `Field`, `HEXPAT_TYPES`.
- Produces: a `_payload_structs()` that emits one struct per non-`computed` layout.

- [ ] **Step 1: Write the failing tests**

Append to `tests/formats/test_hexpat.py`:

```python
def test_every_layout_that_can_be_laid_over_bytes_is_emitted() -> None:
    pattern = render_pattern()
    for layout in LAYOUTS:
        if layout.computed:
            continue
        assert f"struct {layout.name}" in pattern, f"{layout.name} missing"


def test_a_computed_layout_is_named_but_never_laid_over_bytes() -> None:
    """`Layout.computed` means a reader works out where these fields sit, per
    record or era, so the offsets in the catalog are the shape a reader starts
    from and not where the bytes are. Laying it over a record would show
    confident, wrong values -- `report/model.py` skips these for the same
    reason. FrameSpec and GfHold carry it."""
    pattern = render_pattern()
    for layout in LAYOUTS:
        if not layout.computed:
            continue
        assert f"struct {layout.name}" not in pattern, (
            f"{layout.name} is computed and must not be laid over bytes"
        )
        assert layout.name in pattern, f"{layout.name} should still be named, with the reason"


def test_every_field_note_travels_with_its_field() -> None:
    """The evidence is the point. A pattern that gives offsets without saying
    what they mean is worth less than the docstring it came from."""
    pattern = render_pattern()
    noted = [
        field
        for layout in LAYOUTS
        if not layout.computed
        for field in layout.fields
        if field.note
    ]
    assert noted, "the catalog has notes; this test is meaningless without them"
    for field in noted[:20]:
        assert field.note.split(".")[0][:40] in pattern, f"note for {field.name} missing"


def test_a_slot_array_layout_says_it_repeats() -> None:
    """Four layouts have a non-zero `stride`: their payload is an array of
    fixed-size slots, each laid out by the same fields. Emitting one slot and
    stopping would describe a fraction of the record."""
    pattern = render_pattern()
    striped = [layout for layout in LAYOUTS if layout.stride and not layout.computed]
    assert striped, "the catalog has slot arrays; this test is meaningless without them"
    for layout in striped:
        assert f"{layout.name}Slot" in pattern, f"{layout.name} does not emit a slot type"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/formats/test_hexpat.py -q`
Expected: FAIL — `struct MeasSpec` is not in the pattern.

- [ ] **Step 3: Implement `_payload_structs`**

Replace the placeholder in `scripts/hexpat/render.py`:

```python
def _payload_structs() -> str:
    """One struct per layout the catalog permits to be laid over real bytes.

    `Layout.computed` layouts are named and explained but never emitted as a
    struct: a computed layout describes a record whose field positions the
    reader works out per record or era, so pointing it at arbitrary bytes shows
    values that are confidently wrong. `report/model.py` skips them for exactly
    this reason.
    """
    parts = ["\n// ---- record payloads, generated from formats/layouts.py ----\n"]
    for layout in LAYOUTS:
        parts.append(_one_struct(layout))
    parts.append(_tag_comment())
    return "\n".join(parts)


def _one_struct(layout: Layout) -> str:
    tags = _tag_names(layout)
    if layout.computed:
        return (
            f"// {layout.name} ({tags}) is NOT laid out here. Its reader works out where\n"
            f"// the fields sit per record or era, so these offsets are the shape a reader\n"
            f"// starts from rather than where the bytes are. Laying it over a record would\n"
            f"// show confident, wrong values, so the payload stays raw.\n"
        )

    name = f"{layout.name}Slot" if layout.stride else layout.name
    lines = [f"// {layout.record} -- {tags}", f"struct {name} {{"]
    for field in layout.fields:
        lines.append(_one_field(field))
    lines.append("};")
    if layout.stride:
        lines.append(
            f"// {layout.name}: the payload is an array of {layout.stride}-byte "
            f"{name} slots, not one structure."
        )
    return "\n".join(lines) + "\n"


def _one_field(field: Field) -> str:
    hexpat = HEXPAT_TYPES[field.type_]
    note = f"    // {field.note}" if field.note else ""
    if field.is_tail:
        return f"    {hexpat} {field.name}[];{note}"
    if field.type_ == "string":
        return f"    {hexpat} {field.name}[{field.size}];{note}"
    return f"    {hexpat} {field.name};{note}"


def _tag_names(layout: Layout) -> str:
    both = []
    if layout.tag:
        both.append(f"tag {layout.tag}")
    if layout.dcl:
        both.append(f"DCL ^{layout.dcl}")
    return ", ".join(both) if both else "no tag"


def _tag_comment() -> str:
    """Which struct reads which tag, in both spellings.

    A dispatch cannot be generated as pattern code without inventing a record
    shape for the tags this project has not decoded, so the mapping is stated
    for a reader to apply and the undecoded payloads stay raw bytes.
    """
    lines = ["\n// ---- which struct reads which tag ----"]
    for layout in sorted(LAYOUTS, key=lambda item: (item.pool, item.tag or 0)):
        if layout.computed:
            continue
        lines.append(f"//   {layout.pool:8} {_tag_names(layout):22} -> {layout.name}")
    lines.append(
        "// A tag not listed above has no catalogued layout: its payload stays raw bytes\n"
        "// rather than being given an invented structure."
    )
    return "\n".join(lines) + "\n"
```

Add `from finale_file_parser.formats.layouts import LAYOUTS, Field, Layout` to the
module's imports — Task 4 deliberately left it out so nothing was imported unused.

- [ ] **Step 4: Run the tests**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/formats/test_hexpat.py -q`
Expected: PASS.

- [ ] **Step 5: Prove the `computed` guard is load-bearing**

Delete the `if layout.computed:` branch in `_one_struct` so every layout is emitted, run the tests,
and confirm `test_a_computed_layout_is_named_but_never_laid_over_bytes` fails. Restore it. This is
the one guard in the generator whose absence produces a specification that lies.

- [ ] **Step 6: Gate and commit**

```bash
UV_OFFLINE=1 make check
git add scripts/hexpat/render.py tests/formats/test_hexpat.py
git commit -m "feat: generate record payload structs from the catalog"
```

---

### Task 6: Commit the pattern, and pin it current

**Files:**
- Create: `docs/formats/finale-mus.hexpat` (generated)
- Modify: `Makefile`
- Test: `tests/formats/test_hexpat.py`

**Interfaces:**
- Consumes: `render_pattern`.
- Produces: a committed pattern and a `make hexpat` target.

- [ ] **Step 1: Write the failing currency test**

Append to `tests/formats/test_hexpat.py`:

```python
def test_the_committed_pattern_is_current() -> None:
    """The pattern is generated, and a generated file that is committed can go
    stale silently. Adding a field to a layout must either update this file or
    fail this test -- there is no third outcome worth having.

    `docs/formats/finale-formats.{html,pdf}` are generated and committed with no
    such check; this is the one that has it.
    """
    from pathlib import Path

    committed = Path(__file__).parent.parent.parent / "docs" / "formats" / "finale-mus.hexpat"
    assert committed.exists(), "run: make hexpat"
    assert committed.read_text(encoding="utf-8") == render_pattern(), (
        "docs/formats/finale-mus.hexpat is stale -- run: make hexpat"
    )
```

- [ ] **Step 2: Run it and watch it fail**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/formats/test_hexpat.py -q -k current`
Expected: FAIL, `AssertionError: run: make hexpat`.

- [ ] **Step 3: Add the make target**

In `Makefile`, beside the existing `spec` target:

```makefile
# The ImHex pattern is generated from the parser, like the specification above:
# offsets come from formats/layouts.py, never from this file.
hexpat:
	PYTHONPATH=scripts $(PY) python -m hexpat
```

Add `hexpat` to the `.PHONY` line that already lists `spec`, and add a line to the `help` target:

```makefile
	@echo "  hexpat       regenerate docs/formats/finale-mus.hexpat"
```

- [ ] **Step 4: Generate and commit the pattern**

```bash
UV_OFFLINE=1 make hexpat
UV_OFFLINE=1 uv run python -m pytest tests/formats/test_hexpat.py -q
```
Expected: PASS.

- [ ] **Step 5: Prove the currency test is load-bearing**

Append a space to the end of `docs/formats/finale-mus.hexpat`, run the test, confirm it fails, then
`make hexpat` again to restore it.

- [ ] **Step 6: Gate and commit**

```bash
UV_OFFLINE=1 make check
git add Makefile docs/formats/finale-mus.hexpat tests/formats/test_hexpat.py
git commit -m "feat: commit the generated ImHex pattern and pin it current"
```

---

### Task 7: The corpus sweep, and the documentation

**Files:**
- Create: `tests/enigma/test_pool_file_corpus_sweep.py`
- Modify: `README.md`, `docs/ARCHITECTURE.md`
- Test: itself

**Interfaces:**
- Consumes: `read_mus_pools`, `identify_pools`, `write_pool_file`, `read_pool_file`, `era_of`.
- Produces: nothing.

- [ ] **Step 1: Write the sweep**

Create `tests/enigma/test_pool_file_corpus_sweep.py`:

```python
"""Framing every corpus document and reading it back.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser.enigma.mus_payload import POOL_DETAILS, POOL_ENTRIES, POOL_OTHERS
from finale_file_parser.enigma.pool_file import (
    era_of,
    identify_pools,
    read_pool_file,
    write_pool_file,
)
from finale_file_parser.enigma.mus_payload import read_mus_pools

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")


def test_every_document_frames_and_reads_back() -> None:
    """The round trip is the guard. A framing bug that shifted a payload by one
    byte would still produce a valid file of the right size."""
    framed = 0
    for path in corpus_paths(".mus")[:120]:
        try:
            pools = identify_pools(read_mus_pools(path))
        except Exception:  # noqa: BLE001 -- container failures are other sweeps' business
            continue
        data = write_pool_file(pools, era=era_of(pools))
        back = read_pool_file(data)
        assert len(back.pools) == len(pools), "pool count changed across the round trip"
        for before, after in zip(pools, back.pools, strict=True):
            assert after.kind == before.kind
            assert after.data == before.data
            assert after.byte_order == before.byte_order
        framed += 1
    assert framed >= 100, f"only {framed} documents framed; the sweep is not exercising much"


def test_the_unlabelled_era_is_identified_not_guessed() -> None:
    """A 2011-era container labels no pool. Three of the four are identifiable
    by the readers' own walks, and the fourth is the text pool by elimination --
    so if a document ever fails to identify those three, the file is refused
    rather than written with a guess."""
    checked = 0
    for path in corpus_paths(".mus")[:120]:
        try:
            raw = read_mus_pools(path)
        except Exception:  # noqa: BLE001
            continue
        if raw[0].kind is not None:
            continue  # a DCL container states its kinds
        kinds = {pool.kind for pool in identify_pools(raw)}
        assert {POOL_OTHERS, POOL_DETAILS, POOL_ENTRIES} <= kinds
        checked += 1
    assert checked >= 30, f"only {checked} unlabelled-era documents checked"
```

- [ ] **Step 2: Run it**

Run: `UV_OFFLINE=1 uv run python -m pytest tests/enigma/test_pool_file_corpus_sweep.py -q --durations=3`
Expected: PASS. Record the slowest duration in the commit message. The corpus sweeps already run
about ten minutes in total and the suite cannot finish faster than its slowest single test, so if
this lands badly, cut the slice rather than letting it grow the gate.

- [ ] **Step 3: Document it**

In `README.md`, after the "Printing a score" section, add:

```markdown
### Looking at the raw pools

```bash
finale-parser extract score.mus     # writes score.pools.bin beside it
```

A `.mus` keeps its four pools compressed — the 2001–2005 era with PKWARE implode, which no hex
editor can decompress — so `extract` writes them out in one file, framed with the container's own
`kind`/`length`/`checksum` chain. Open that in [ImHex](https://imhex.org/) with
`docs/formats/finale-mus.hexpat` and every record this project knows how to read is laid out at the
offsets the parser uses. The pattern is generated from `formats/layouts.py`, so it cannot state an
offset the code does not.
```

In `docs/ARCHITECTURE.md`, add a subsection immediately before
`### Known format facts — the reserved staff 32767`:

```markdown
### The pattern that reads a `.mus`'s pools in a hex editor

**`finale-parser extract` writes the pools out because ImHex cannot decompress them.** Its
`hex::dec::` namespace covers zlib, bzip, lzma, zstd and lz4 — there is no PKWARE implode, which is
what the 2001–2005 era uses in 139 of the corpus's 238 documents. Implementing implode in the
pattern language does not work either, for reasons that are not about the format: `std::mem` can
copy bytes between sections but cannot emit a *computed* one, overlapping LZ77 copies force
byte-at-a-time loops, and the evaluator caps loop iterations at 4096. Decompressing in Python first
sidesteps all of it.

**The extracted file keeps the container's own framing** — `kind`, `length`, `checksum`, laid end to
end, `length` counting its own header — so walking it teaches a reader the real chain. Only two
things differ: payloads are decompressed, so `length` is the decompressed size, and an 8-byte header
(`FMUS`, version, byte order, era, pool count) is prepended so the file announces itself rather than
impersonating a score. The checksum is written as zero: the container's covers the compressed
stream, which the file does not hold.

**A 2011-era container labels no pool**, so `extract` identifies them with the same walks the
readers already use to pick their own stream — `mus_others._walk`, `mus_details._walk` and
`mus_entries._looks_like_entry_pool`. Across all 99 zlib-era corpus documents those three identify
positively in 99 of 99, with no stream matching two tests; the fourth is the text pool by
elimination, agreeing with the order the DCL container states outright. Only one pool may be
inferred that way — two would make the fourth a coin toss, and a wrong kind sends a reader to the
wrong record shape.

`docs/formats/finale-mus.hexpat` is generated from `formats/layouts.py` by `make hexpat`, and
`tests/formats/test_hexpat.py` fails if the committed copy is stale. Layouts marked `computed` —
`frameSpec` and `gfhold` — are named but never laid over bytes, because their readers work the
offsets out per record or era.
```

- [ ] **Step 4: Gate and commit**

```bash
UV_OFFLINE=1 make check-full
git add tests/enigma/test_pool_file_corpus_sweep.py README.md docs/ARCHITECTURE.md
git commit -m "test: sweep the corpus through the pool file, and document it"
```

---

## Notes for whoever executes this

**The one thing CI cannot tell you.** No test here runs the pattern. ImHex is not installable in
this environment and there is no headless evaluator for its language, so a syntax error, a wrong
`std::mem::Endian` member name, or a `#pragma magic` ImHex rejects would pass everything above.
Before this branch is trusted, open `docs/formats/finale-mus.hexpat` in ImHex against a real
`.pools.bin` and confirm it loads and lays out records. Two things to look at first, because they
are where a guess has been made about ImHex's own API rather than about Finale:

1. `std::core::set_endian(std::mem::Endian::Big)` — the function is documented, the enum member
   spelling is not, and it may be `Endian::Big` or another form.
2. `#pragma magic [ 46 4D 55 53 ] @ 0x00` — the syntax is from ImHex's magic-file convention and
   may need to live in a separate magic file rather than in the pattern.

If either is wrong, fix the generator rather than the generated file, and re-run `make hexpat`.

**Where the corpus is.** `corpus/` is gitignored and exists only in the main checkout. In a worktree
symlink it (`ln -s /path/to/repo/corpus corpus`), and note that `find` needs `-L` to follow it.
Never `git add -A` — the symlink is untracked and not ignored.
