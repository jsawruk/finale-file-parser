# `score.dat` Decoder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `score_xml(path) -> bytes` — decrypt and inflate a `.musx`'s `score.dat` into EnigmaXML.

**Architecture:** A new `enigma/` package. `crypt.py` is pure and holds the cipher; `score.py` composes the container reader, the decryption, and a bounded inflate. No new dependencies — `zlib` is stdlib.

**Format reference:** `docs/formats/score-dat.md` — the pipeline, the corpus measurements, and the details that are easy to get wrong. **Read it first.**
**Design spec:** `docs/superpowers/specs/2026-07-22-score-decoder-design.md` — API and safety decisions.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`. Stdlib only.
- **Cipher constants, exact:** `INITIAL_STATE = 0x28006D45`, `MULTIPLIER = 0x41C64E6D`, `INCREMENT = 0x3039`, `RESET_EVERY = 0x20000`. Keystream byte is `(upper + upper // 255) & 0xFF` where `upper = (state >> 16) & 0xFFFF`.
- **`MAX_INFLATED = 64 * 1024 * 1024`.** Corpus max is 10,781,112 bytes.
- **Attribution is required, not optional.** The cipher parameters come from [denigma](https://github.com/chrisroode/denigma) (MIT), which credits [Deguerre](https://github.com/Deguerre). Credit both in a module comment in `enigma/crypt.py` and in `docs/REFERENCES.md`.
- `corpus/` is gitignored copyrighted material. **No corpus bytes may be committed.** Every test input is constructed in-test.
- Verify by mutation: delete a rule, confirm its test fails, restore. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

---

### Task 1: The cipher

**Files:**
- Create: `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/enigma/crypt.py`
- Test: `tests/enigma/__init__.py` (empty), `tests/enigma/test_crypt.py`

**Interfaces:**
- Produces: `decrypt(data: bytes) -> bytes`, and the constants `INITIAL_STATE`, `MULTIPLIER`, `INCREMENT`, `RESET_EVERY`. Task 2 consumes `decrypt`.

Pure module — no I/O, no imports from `container` or `version`.

**The one thing that matters here.** The keystream resets every `0x20000` bytes, so it is a *constant* 131,072-byte block repeated end to end. Build it once, cache it at module level, and tile it. Measured on the largest corpus file, tiling is byte-identical to per-byte LCG stepping and 4.6× faster (15.1 ms vs 68.7 ms), and the gap widens across many files because the block is built once rather than per call.

Because only 68 of 401 corpus archives exceed 128 KiB, **an implementation that omits the reset decodes 333 of 401 files correctly**. The reset must be covered by a test using more than `RESET_EVERY` bytes.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/__init__.py` empty, then `tests/enigma/test_crypt.py`:

```python
from finale_file_parser.enigma.crypt import (
    INITIAL_STATE,
    RESET_EVERY,
    decrypt,
)


def _reference(data: bytes) -> bytes:
    """Per-byte LCG, written independently of the implementation.

    Deliberately the naive form from docs/formats/score-dat.md, so the tiled
    implementation is checked against a different construction rather than
    against itself.
    """
    out = bytearray(len(data))
    state = INITIAL_STATE
    for i, byte in enumerate(data):
        if i % RESET_EVERY == 0:
            state = INITIAL_STATE
        state = (state * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        upper = (state >> 16) & 0xFFFF
        out[i] = byte ^ ((upper + upper // 255) & 0xFF)
    return bytes(out)


def test_matches_the_reference_implementation() -> None:
    data = bytes(range(256)) * 8
    assert decrypt(data) == _reference(data)


def test_round_trips() -> None:
    """XOR is its own inverse, so decrypting twice returns the input."""
    data = b"the quick brown fox" * 100
    assert decrypt(decrypt(data)) == data


def test_known_keystream_prefix() -> None:
    """keystream[0:3] is 09 5c 5b — derived in docs/formats/score-dat.md from a
    real ciphertext XOR the gzip magic, independently of the cipher source."""
    assert decrypt(bytes(3)) == bytes([0x09, 0x5C, 0x5B])


def test_decrypts_a_real_gzip_header_shape() -> None:
    """Ciphertext 16 d7 53 must decrypt to the gzip magic 1f 8b 08."""
    assert decrypt(bytes([0x16, 0xD7, 0x53])) == b"\x1f\x8b\x08"


def test_keystream_resets_at_the_block_boundary() -> None:
    """The byte at RESET_EVERY must use the same keystream as byte 0.

    This is the bug that hides: only 68 of 401 corpus archives exceed
    RESET_EVERY, so an implementation without the reset decodes 333 of 401
    files correctly.
    """
    plain = bytes(RESET_EVERY + 16)
    ks = decrypt(plain)
    assert ks[:16] == ks[RESET_EVERY : RESET_EVERY + 16]


def test_matches_reference_across_the_boundary() -> None:
    data = bytes((i * 7 + 3) & 0xFF for i in range(RESET_EVERY + 5000))
    assert decrypt(data) == _reference(data)


def test_empty_input() -> None:
    assert decrypt(b"") == b""


def test_single_byte() -> None:
    assert decrypt(b"\x00") == bytes([0x09])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.enigma'`

- [ ] **Step 3: Write the implementation**

Create `src/finale_file_parser/enigma/__init__.py` empty. Create `src/finale_file_parser/enigma/crypt.py`:

```python
"""The score.dat cipher.

`score.dat` is XOR-encrypted with a keystream from a BSD `rand()` linear
congruential generator seeded with a fixed constant. The generator is reseeded
at every RESET_EVERY-byte boundary, so the keystream is one constant block
repeated end to end.

The cipher parameters were not discovered by this project. They come from
denigma (https://github.com/chrisroode/denigma, MIT), whose source credits
Deguerre (https://github.com/Deguerre). This implementation is written
independently; see docs/formats/score-dat.md for the full pipeline and for what
this project did and did not derive from the corpus.
"""

from __future__ import annotations

INITIAL_STATE = 0x28006D45
MULTIPLIER = 0x41C64E6D
INCREMENT = 0x3039

RESET_EVERY = 0x20000
"""The generator is reseeded every 131,072 bytes.

Only 68 of 401 corpus archives have a score.dat larger than this, so omitting
the reset decodes 333 of 401 files correctly and fails only on the largest.
"""


def _build_keystream_block() -> bytes:
    """Generate the one constant keystream block, RESET_EVERY bytes long."""
    out = bytearray(RESET_EVERY)
    state = INITIAL_STATE
    for i in range(RESET_EVERY):
        state = (state * MULTIPLIER + INCREMENT) & 0xFFFFFFFF
        upper = (state >> 16) & 0xFFFF
        out[i] = (upper + upper // 255) & 0xFF
    return bytes(out)


_KEYSTREAM = _build_keystream_block()
"""Built once at import. Tiling this is byte-identical to stepping the LCG per
byte and measurably faster; see docs/formats/score-dat.md."""


def decrypt(data: bytes) -> bytes:
    """Return `data` XORed with the score.dat keystream.

    XOR is its own inverse, so this both encrypts and decrypts. Never raises.
    """
    if not data:
        return b""
    repeats = len(data) // RESET_EVERY + 1
    keystream = (_KEYSTREAM * repeats)[: len(data)]
    return bytes(a ^ b for a, b in zip(data, keystream, strict=True))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/enigma -v`
Expected: PASS — 8 passed.

- [ ] **Step 5: Mutation-verify**

| Mutation in `crypt.py` | Test that must fail |
|---|---|
| `INITIAL_STATE` → `0x28006D46` | `test_known_keystream_prefix` |
| `(upper + upper // 255)` → `upper` | `test_matches_the_reference_implementation` |
| `RESET_EVERY` → `0x40000` | `test_keystream_resets_at_the_block_boundary` |
| Tile with `_KEYSTREAM` reversed | `test_matches_the_reference_implementation` |

Record each result. A mutation that does not fail means the test is vacuous — fix it before proceeding.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser/enigma tests/enigma
git commit -m "feat: add the score.dat cipher"
```

---

### Task 2: `score_xml`

**Files:**
- Create: `src/finale_file_parser/enigma/models.py`, `src/finale_file_parser/enigma/score.py`
- Modify: `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/__init__.py`, `tests/test_public_api.py`
- Test: `tests/enigma/test_score.py`

**Interfaces:**
- Consumes: `decrypt` from `crypt.py`; `open_musx` from `finale_file_parser.container`; `FinaleFileError` from `finale_file_parser.errors`.
- Produces: `score_xml(path: str | os.PathLike[str]) -> bytes`, `CorruptScoreError`, `MAX_INFLATED`. Exported from `finale_file_parser.enigma` and the package root.

**Error posture — deliberately stricter than the version modules.** They degrade to "unknown" so unfamiliar variants stay inspectable. That is right for *optional metadata* and wrong here: a caller asking for the score asked for a specific thing, and half a score is not useful. So `score_xml` raises.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/test_score.py`:

```python
import gzip
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser.container.models import CorruptContainerError
from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.score import MAX_INFLATED, score_xml
from finale_file_parser.version.models import NotFinaleFileError

MIMETYPE = b"application/vnd.makemusic.notation"
SAMPLE_XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<finale version="18.0"><entries/></finale>'


@pytest.fixture
def make_score(tmp_path: Path) -> Callable[..., Path]:
    """Build a .musx whose score.dat encrypts to the given payload.

    Everything here is constructed in-test — no corpus bytes.
    """

    def build(
        *,
        xml: bytes = SAMPLE_XML,
        raw_plaintext: bytes | None = None,
        include_score: bool = True,
        name: str = "sample.musx",
    ) -> Path:
        plaintext = raw_plaintext if raw_plaintext is not None else gzip.compress(xml)
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
            archive.writestr("NotationMetadata.xml", "<metadata/>")
            if include_score:
                archive.writestr("score.dat", decrypt(plaintext))
        return path

    return build


def test_round_trips_our_own_xml(make_score: Callable[..., Path]) -> None:
    assert score_xml(make_score()) == SAMPLE_XML


def test_accepts_a_str_path(make_score: Callable[..., Path]) -> None:
    assert score_xml(str(make_score())) == SAMPLE_XML


def test_handles_a_payload_spanning_the_keystream_reset(
    make_score: Callable[..., Path],
) -> None:
    """Exercises the reset end to end, not just in the cipher unit tests."""
    big = b'<finale version="18.0">' + b"<t>x</t>" * 40000 + b"</finale>"
    assert score_xml(make_score(xml=big)) == big


def test_rejects_a_stream_that_is_not_gzip(make_score: Callable[..., Path]) -> None:
    with pytest.raises(CorruptScoreError, match="not a gzip stream"):
        score_xml(make_score(raw_plaintext=b"this is not gzip at all"))


def test_rejects_truncated_gzip(make_score: Callable[..., Path]) -> None:
    truncated = gzip.compress(SAMPLE_XML)[:-8]
    with pytest.raises(CorruptScoreError):
        score_xml(make_score(raw_plaintext=truncated))


def test_rejects_output_over_the_inflation_cap(make_score: Callable[..., Path]) -> None:
    """A decompression bomb: tiny compressed, enormous inflated."""
    bomb = gzip.compress(b"\x00" * (MAX_INFLATED + 1024))
    assert len(bomb) < 1_000_000, "bomb should be small on disk"
    with pytest.raises(CorruptScoreError, match="exceeds"):
        score_xml(make_score(raw_plaintext=bomb))


def test_archive_without_score_dat_raises(make_score: Callable[..., Path]) -> None:
    with pytest.raises(CorruptContainerError):
        score_xml(make_score(include_score=False))


def test_non_finale_zip_raises(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "not a score")
    with pytest.raises(NotFinaleFileError):
        score_xml(path)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        score_xml(tmp_path / "nope.musx")


def test_corrupt_score_error_is_a_finale_file_error() -> None:
    from finale_file_parser.errors import FinaleFileError

    assert issubclass(CorruptScoreError, FinaleFileError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma/test_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.enigma.models'`

- [ ] **Step 3: Write the implementation**

Create `src/finale_file_parser/enigma/models.py`:

```python
"""Types for the EnigmaXML decoder."""

from __future__ import annotations

from finale_file_parser.errors import FinaleFileError


class CorruptScoreError(FinaleFileError):
    """The score stream could not be decoded into EnigmaXML.

    Raised when the decrypted bytes are not a gzip stream, fail to inflate, or
    would inflate past the cap. Unlike the version modules, which degrade to
    "unknown" so unfamiliar variants stay inspectable, this raises: a caller
    asking for the score asked for a specific thing, and half a score is not
    useful.
    """
```

Create `src/finale_file_parser/enigma/score.py`:

```python
"""Decode a .musx's score.dat into EnigmaXML.

Pipeline: open the container, read score.dat, decrypt, inflate. See
docs/formats/score-dat.md.
"""

from __future__ import annotations

import os
import zlib

from finale_file_parser.container.musx import open_musx
from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.models import CorruptScoreError

GZIP_MAGIC = b"\x1f\x8b"

MAX_INFLATED = 64 * 1024 * 1024
"""Refuse output larger than 64 MiB. The largest corpus file inflates to
10,781,112 bytes, and observed ratios run 25.6x to 37.3x."""

_CHUNK = 1 << 20
_GZIP_WBITS = 31
"""zlib window size selecting gzip framing rather than raw or zlib framing."""


def score_xml(path: str | os.PathLike[str]) -> bytes:
    """Return the EnigmaXML inside the `.musx` at `path`.

    Raises:
        FileNotFoundError: no such path.
        NotFinaleFileError: not a readable zip, or not a Finale archive.
        CorruptContainerError: the archive violates a structural limit, or
            carries no score.dat.
        CorruptScoreError: the score stream is not decodable EnigmaXML.
    """
    with open_musx(path) as container:
        encrypted = container.score_stream()
    plaintext = decrypt(encrypted)
    if not plaintext.startswith(GZIP_MAGIC):
        raise CorruptScoreError(
            f"{path} score stream is not a gzip stream after decryption "
            f"(starts {plaintext[:4].hex(' ')!r})"
        )
    return _inflate(plaintext, path)


def _inflate(data: bytes, path: str | os.PathLike[str]) -> bytes:
    """Inflate `data`, refusing to allocate past MAX_INFLATED.

    Decompresses incrementally rather than in one call: a one-shot decompress
    on untrusted input allocates the whole output before anything can object,
    which is the entire decompression-bomb problem.
    """
    engine = zlib.decompressobj(wbits=_GZIP_WBITS)
    out = bytearray()
    try:
        chunk = engine.decompress(data, _CHUNK)
        while chunk:
            out += chunk
            if len(out) > MAX_INFLATED:
                raise CorruptScoreError(
                    f"{path} score stream inflates past {MAX_INFLATED} bytes; refusing"
                )
            # Feed back `unconsumed_tail`, NOT b"". When `decompress` is given a
            # max_length it parks the rest of the input there; passing b"" makes
            # the loop exit early and silently truncates the output to one chunk.
            chunk = engine.decompress(engine.unconsumed_tail, _CHUNK)
    except zlib.error as exc:
        raise CorruptScoreError(f"{path} score stream failed to inflate: {exc}") from exc
    if not engine.eof:
        raise CorruptScoreError(f"{path} score stream is a truncated gzip stream")
    return bytes(out)
```

Export from `src/finale_file_parser/enigma/__init__.py`:

```python
"""Decoding score.dat into EnigmaXML."""

from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.score import MAX_INFLATED, score_xml

__all__ = ["MAX_INFLATED", "CorruptScoreError", "decrypt", "score_xml"]
```

Add `CorruptScoreError` and `score_xml` to the package root's imports and `__all__`, and to `EXPECTED_PUBLIC_NAMES` in `tests/test_public_api.py`. Note the derived export test asserts every subpackage `__all__` is reachable from the root — check whether it requires `decrypt` and `MAX_INFLATED` at the root too, and satisfy it rather than weakening it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: PASS — 10 new tests, everything else unchanged.

- [ ] **Step 5: Mutation-verify**

| Mutation in `score.py` | Test that must fail |
|---|---|
| Remove the `GZIP_MAGIC` check | `test_rejects_a_stream_that_is_not_gzip` |
| Remove the `MAX_INFLATED` check | `test_rejects_output_over_the_inflation_cap` |
| Remove the `engine.eof` check | `test_rejects_truncated_gzip` |
| Replace incremental inflate with `gzip.decompress(data)` | `test_rejects_output_over_the_inflation_cap` |

The last one matters: if a one-shot decompress still passes the cap test, the cap is being applied *after* allocation and provides no protection.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests
git commit -m "feat: add score_xml to decode EnigmaXML from a .musx"
```

---

### Task 3: Corpus sweep

**Files:** Create `tests/enigma/test_corpus_sweep.py`.

Skips when `corpus/` is absent, like the other sweeps. Expected values from `docs/formats/score-dat.md`.

- [ ] **Step 1: Write the test**

Assert, across all 401 `.musx` archives:

- every archive decodes without raising — **401 of 401**
- every result starts with `<?xml` and contains a `<finale` root element
- every result's `version="18.0"` (the XML schema version — *not* the writing application's, which spans majors 15-18)
- inflated sizes fall within the observed range: min 2,481,759, max 10,781,112
- at least 60 archives have a `score.dat` exceeding `RESET_EVERY`, so the sweep genuinely exercises the keystream reset against real data (observed: 68)

Assert the file list is non-empty first so nothing passes vacuously. **If an observed value disagrees, report it rather than adjusting the assertion** — these are pinned so a corpus change forces a deliberate update to both the test and `docs/formats/score-dat.md`.

Report counts and sizes only. Never quote a corpus filename, title, or payload.

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/enigma/test_corpus_sweep.py -v` — expected pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/enigma -v; mv /tmp/corpus-parked corpus`

Expected: sweep skipped, cipher and score tests still pass. **Confirm `corpus/` is restored and reports 639 files** — it is the user's data and is not in git.

- [ ] **Step 3: Commit**

```bash
git add tests/enigma/test_corpus_sweep.py
git commit -m "test: sweep the corpus through the EnigmaXML decoder"
```

---

### Task 4: Documentation

**Files:** `docs/REFERENCES.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: Attribution in `docs/REFERENCES.md`**

Under "Community reverse engineering", add **denigma** — https://github.com/chrisroode/denigma, MIT — noting it is the source of the `score.dat` cipher parameters and that its source credits **Deguerre** (https://github.com/Deguerre) for the discovery. This is the attribution the decision below requires; it is not optional.

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Add `src/finale_file_parser/enigma/` to the Modules section — `crypt.py` (the cipher, pure), `models.py`, `score.py` (`score_xml`, composing the container reader). Add a short "Known format facts — score.dat" subsection that **links to `docs/formats/score-dat.md`** as the full reference rather than duplicating it, and states the headline: encrypted with a fixed-seed BSD LCG keystream that resets every 128 KiB, plaintext is gzip, inflates ~28× to EnigmaXML, 401/401 corpus archives verified.

- [ ] **Step 3: `docs/DECISIONS.md`**

```markdown
## 2026-07-22 — DECIDED: cipher parameters taken as facts from MIT-licensed source

The `score.dat` cipher — seed `0x28006D45`, the BSD `rand()` LCG, the
`(upper + upper // 255)` output function, and the 128 KiB keystream reset — was read from
denigma's source (MIT), which credits Deguerre for the discovery. The implementation here is
written independently; the parameters are not.

Reason: the earlier decision was to use published *documentation* as reference and write
implementations independently. That proved insufficient — the transform is documented nowhere in
prose, only in code. An algorithm choice and a seed value are facts rather than creative
expression, and MIT would permit outright porting with attribution in any case.

Consequence: attribution to both denigma and Deguerre is required in `docs/REFERENCES.md` and in
`enigma/crypt.py`. `docs/formats/score-dat.md` records precisely what this project derived from the
corpus and what it did not.
```

- [ ] **Step 4: `docs/ROADMAP.md`**

Mark the `score.dat` item done. Replace the `Next up` section with **parsing EnigmaXML into a model** — the `<finale>` document carries `mappings`, `header`, `options`, `others`, `details`, `entries`, and `texts` pools, and the community [EnigmaXML documentation](https://github.com/Project-Attacca/enigmaxml-documentation) describes them. Note that inflated documents run 2.5-10.8 MB, so parsing strategy (streaming vs whole-document) is a real design question rather than an obvious one.

- [ ] **Step 5: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record the EnigmaXML decoder and its attribution"
```

---

## Completion

After Task 4, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed; the mutation results for both the cipher and the inflate
caps; that the corpus sweep decodes 401/401 locally and skips in CI; that no corpus bytes are
committed and every test input is constructed in-test; and the attribution to denigma and Deguerre.
