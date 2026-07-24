# Key Signature Decoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `decode_key(raw: int) -> KeySignature` — turn the raw `keySig.key` integer into fifths, mode, and tonic.

**Architecture:** A pure `enigma/key.py`. `decode_key` splits the integer (`mode = high byte`, `fifths = signed low byte`) and derives the tonic via circle-of-fifths tables. No document, no I/O.

**Design spec:** `docs/superpowers/specs/2026-07-24-key-decode-design.md`. Read it first — the encoding is reverse-engineered, and the spec records what is proven vs inferred.

## Global Constraints

- Python `>=3.12`; fully type-annotated; `mypy --strict`. ruff line-length 100, rules `E, F, I, UP, B`. `make check` covers `src tests scripts`. Stdlib only (this slice adds no imports beyond `enum`/`dataclasses`).
- **The encoding (reverse-engineered, exact):** `mode = raw >> 8` (0 major, 1 minor); `fifths = signed low byte` (`low = raw & 0xFF`; `fifths = low - 256 if low > 127 else low`).
- **Verified:** all 30 standard keys (mode ∈ {0,1} × fifths ∈ [−7,7]) round-trip; `256` = A minor, `253` = E♭ major, `255` = F major.
- **`decode_key` is a pure `int -> KeySignature` transform** — no document, no I/O, no imports from `document`/`location`/`container`.
- **Raise `UnsupportedKeyError` on `mode >= 2` or `fifths` outside `−7…+7`** — church modes / custom keys are unseen and not decoded; raising beats guessing (a wrong key silently misspells every pitch downstream). 0 corpus incidence.
- Enharmonic keys are distinct by sign: `+6` (F♯ major) is raw byte `6`, `−6` (G♭ major) is raw byte `250`.
- `corpus/` is gitignored — the sweep may read the `keySig.key` integers (structural, not content) but never other record values. No corpus bytes in fixtures.
- Verify by mutation. Clear `__pycache__` and run pytest with `PYTHONDONTWRITEBYTECODE=1` — stale bytecode has produced misleading results here.
- Conventional Commits. One commit per task.

## Reference: the verified decode

This exact logic round-tripped all 30 standard keys and raised on every out-of-range value.

```python
MAJOR_TONIC = {0:"C",1:"G",2:"D",3:"A",4:"E",5:"B",6:"F#",7:"C#",
               -1:"F",-2:"Bb",-3:"Eb",-4:"Ab",-5:"Db",-6:"Gb",-7:"Cb"}
MINOR_TONIC = {0:"A",1:"E",2:"B",3:"F#",4:"C#",5:"G#",6:"D#",7:"A#",
               -1:"D",-2:"G",-3:"C",-4:"F",-5:"Bb",-6:"Eb",-7:"Ab"}

mode = raw >> 8
low = raw & 0xFF
fifths = low - 256 if low > 127 else low
if mode >= 2 or not (-7 <= fifths <= 7):
    raise UnsupportedKeyError(...)
tonic = (MAJOR_TONIC if mode == 0 else MINOR_TONIC)[fifths]
```

---

### Task 1: `decode_key` and `KeySignature`

**Files:**
- Create: `src/finale_file_parser/enigma/key.py`
- Modify: `src/finale_file_parser/enigma/__init__.py`, `src/finale_file_parser/__init__.py`, `tests/test_public_api.py`
- Test: `tests/enigma/test_key.py`

**Interfaces:**
- Consumes: `FinaleFileError` from `finale_file_parser.errors`.
- Produces: `Mode` (enum: `MAJOR = 0`, `MINOR = 1`), `KeySignature` (frozen: `fifths: int`, `mode: Mode`, `tonic: str`), `decode_key(raw: int) -> KeySignature`, `UnsupportedKeyError`. All exported from `finale_file_parser.enigma` and the package root.

- [ ] **Step 1: Write the failing tests**

Create `tests/enigma/test_key.py`:

```python
import pytest

from finale_file_parser.enigma.key import (
    KeySignature,
    Mode,
    UnsupportedKeyError,
    decode_key,
)


@pytest.mark.parametrize(
    "raw,fifths,mode,tonic",
    [
        (0, 0, Mode.MAJOR, "C"),
        (1, 1, Mode.MAJOR, "G"),
        (2, 2, Mode.MAJOR, "D"),          # +2 = D major (the spec's example)
        (3, 3, Mode.MAJOR, "A"),
        (255, -1, Mode.MAJOR, "F"),       # -1 = F major
        (254, -2, Mode.MAJOR, "Bb"),
        (253, -3, Mode.MAJOR, "Eb"),
        (251, -5, Mode.MAJOR, "Db"),
        (256, 0, Mode.MINOR, "A"),        # 0 fifths, minor = A minor
        (257, 1, Mode.MINOR, "E"),
        (511, -1, Mode.MINOR, "D"),
        (510, -2, Mode.MINOR, "G"),
        (507, -5, Mode.MINOR, "Bb"),
    ],
)
def test_decodes_corpus_keys(raw: int, fifths: int, mode: Mode, tonic: str) -> None:
    key = decode_key(raw)
    assert key == KeySignature(fifths=fifths, mode=mode, tonic=tonic)


def test_enharmonic_keys_are_distinct() -> None:
    # +6 (F# major, raw 6) and -6 (Gb major, raw 250) must not collide
    fsharp = decode_key(6)
    gflat = decode_key(250)
    assert fsharp == KeySignature(6, Mode.MAJOR, "F#")
    assert gflat == KeySignature(-6, Mode.MAJOR, "Gb")
    assert fsharp != gflat


def test_extreme_signatures() -> None:
    assert decode_key(7) == KeySignature(7, Mode.MAJOR, "C#")
    assert decode_key(249) == KeySignature(-7, Mode.MAJOR, "Cb")


def test_mode_two_or_more_raises() -> None:
    with pytest.raises(UnsupportedKeyError):
        decode_key(512)   # mode 2 — a church mode / custom key, not decoded


def test_fifths_out_of_range_raises() -> None:
    with pytest.raises(UnsupportedKeyError):
        decode_key(8)     # fifths +8, beyond ±7
    with pytest.raises(UnsupportedKeyError):
        decode_key(248)   # low byte 248 -> fifths -8


def test_frozen() -> None:
    key = decode_key(0)
    with pytest.raises((AttributeError, TypeError)):
        key.fifths = 1  # type: ignore[misc]


def test_error_is_a_finale_file_error() -> None:
    from finale_file_parser.errors import FinaleFileError

    assert issubclass(UnsupportedKeyError, FinaleFileError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enigma/test_key.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finale_file_parser.enigma.key'`

- [ ] **Step 3: Write the implementation**

Create `src/finale_file_parser/enigma/key.py`:

```python
"""Decode the raw `keySig.key` integer into a structured key signature.

The encoding is reverse-engineered from the corpus (documented nowhere read):

    key = (mode << 8) | (fifths & 0xFF)

where `mode` is 0 (major) or 1 (minor) and `fifths` is a signed accidental count
(sharps positive, flats negative) in the MusicXML convention. See
docs/superpowers/specs/2026-07-24-key-decode-design.md for the evidence and for
what is proven vs inferred (notably mode = 1 => minor is inferred).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from finale_file_parser.errors import FinaleFileError

_MAX_FIFTHS = 7

_MAJOR_TONIC = {
    0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#",
    -1: "F", -2: "Bb", -3: "Eb", -4: "Ab", -5: "Db", -6: "Gb", -7: "Cb",
}
_MINOR_TONIC = {
    0: "A", 1: "E", 2: "B", 3: "F#", 4: "C#", 5: "G#", 6: "D#", 7: "A#",
    -1: "D", -2: "G", -3: "C", -4: "F", -5: "Bb", -6: "Eb", -7: "Ab",
}


class UnsupportedKeyError(FinaleFileError):
    """A raw key value outside the reverse-engineered standard model.

    `mode >= 2` (a church mode or custom/linear key we have not established) or
    `fifths` outside -7..+7. Raised rather than guessed: a wrong key would
    silently misspell every pitch that resolves through it.
    """


class Mode(Enum):
    MAJOR = 0
    MINOR = 1


@dataclass(frozen=True)
class KeySignature:
    """A decoded key signature."""

    fifths: int
    """Signed accidental count: sharps positive, flats negative (MusicXML)."""

    mode: Mode
    tonic: str
    """The tonic note name, e.g. "C", "F#", "Bb"; "A" for A minor."""


def decode_key(raw: int) -> KeySignature:
    """Decode a raw `keySig.key` integer into a `KeySignature`.

    Raises:
        UnsupportedKeyError: `mode >= 2`, or `fifths` outside -7..+7.
    """
    mode_value = raw >> 8
    low = raw & 0xFF
    fifths = low - 256 if low > 127 else low
    if mode_value >= len(Mode) or not (-_MAX_FIFTHS <= fifths <= _MAX_FIFTHS):
        raise UnsupportedKeyError(f"unsupported key value {raw} (mode={mode_value}, fifths={fifths})")
    mode = Mode(mode_value)
    tonic = (_MAJOR_TONIC if mode is Mode.MAJOR else _MINOR_TONIC)[fifths]
    return KeySignature(fifths=fifths, mode=mode, tonic=tonic)
```

Note `mode_value >= len(Mode)` uses the enum size (2) as the boundary — `Mode(mode_value)` for a
value ≥ 2 would raise a bare `ValueError`, so the guard must come first.

Export `decode_key`, `KeySignature`, `Mode`, `UnsupportedKeyError` from `enigma/__init__.py` and the
package root; add them to `EXPECTED_PUBLIC_NAMES` in `tests/test_public_api.py`. Satisfy the derived
public-API test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: PASS — the new key tests plus everything else unchanged.

- [ ] **Step 5: Mutation-verify**

| Mutation | Test that must fail |
|---|---|
| Drop the signed-byte conversion (`fifths = low` always) | `test_decodes_corpus_keys` (the flats: 255 would read as +255) |
| Ignore the mode byte (always `Mode.MAJOR`) | `test_decodes_corpus_keys` (the minor rows) |
| Remove the `mode >= 2` guard | `test_mode_two_or_more_raises` |
| Remove the `fifths` range guard | `test_fifths_out_of_range_raises` |
| Swap `_MAJOR_TONIC`/`_MINOR_TONIC` | `test_decodes_corpus_keys` |

The signed-byte one is the important one: without it every flat key decodes as a large positive
fifths and the tonic lookup `KeyError`s or is wrong.

- [ ] **Step 6: Gate and commit**

Run: `make check` — clean.

```bash
git add src/finale_file_parser tests
git commit -m "feat: decode the raw keySig integer into a KeySignature"
```

---

### Task 2: Corpus sweep

**Files:** Create `tests/enigma/test_key_corpus_sweep.py`. Skips when `corpus/` is absent.

- [ ] **Step 1: Write the test**

Over all 401 archives, collect every distinct `keySig.key` integer from the `part`-less `measSpec`
records (`doc.others.of_tag("measSpec")`, filter `"part" not in attrs`, read
`measSpec.fields["keySig"].fields["key"]` when the `keySig` is a `Record`), and assert:

- **every distinct raw value decodes without raising** — `decode_key(v)` for each. The survey found
  all 13 corpus values are standard, so any `UnsupportedKeyError` is a real finding.
- the set of decoded `(fifths, mode)` pairs equals the surveyed set — pin the exact 13 values as an
  expected constant, so a corpus change forces a deliberate update. Expected raw values:
  `{1, 2, 3, 251, 252, 253, 254, 255, 256, 257, 507, 510, 511}`.
- `decode_key` composes with the location layer on at least one file: for a sample of entries,
  `decode_key(locate_entries(doc)[entnum].key_signature)` returns a `KeySignature` without raising.

Assert the file list is non-empty first. **If an observed value disagrees with the expected set,
report it rather than adjusting the assertion.** Report counts and the key integers only (structural)
— never a title, lyric, or other record value.

Note the enigma corpus sweeps are slow (~80-120s). Keep this focused.

- [ ] **Step 2: Run with and without the corpus**

Run: `uv run pytest tests/enigma/test_key_corpus_sweep.py -v` — expected pass.

Then: `mv corpus /tmp/corpus-parked && uv run pytest tests/enigma -v; mv /tmp/corpus-parked corpus`

Expected: this sweep skipped, other enigma tests pass. **Confirm `corpus/` is restored and reports
639 files** (case-insensitive — 101 files are uppercase `.MUS`; use `p.suffix.lower()`).

- [ ] **Step 3: Commit**

```bash
git add tests/enigma/test_key_corpus_sweep.py
git commit -m "test: decode every corpus key signature value"
```

---

### Task 3: Documentation

**Files:** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`. Documentation only — change no code.

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Add `enigma/key.py` to Modules. Add a "Known format facts — key signatures" subsection: the encoding
`key = (mode << 8) | signed-fifths-byte`, mode 0 = major / 1 = minor, fifths the MusicXML signed
accidental count; the corroboration (clean decomposition of all 13 corpus values, `keySig` has no
other field, matches MusicXML, tonic derivation matches theory); and the inferred-vs-proven note
(mode = 1 => minor is inferred; ±6/±7 and church modes are modelled/unseen). Note `mode >= 2` raises
`UnsupportedKeyError`.

- [ ] **Step 2: `docs/ROADMAP.md`**

Mark key decoding done. Set the next item to **pitch spelling** — combine `decode_key` (tonic +
fifths), `read_entry`'s `harm_lev`/`harm_alt`, and `locate_entries` into an absolute spelled pitch;
note it must handle the accidental pattern the key implies and the harmAlt alteration. Then clefs,
time signatures, tuplets, the detail records, toward a MusicXML exporter.

- [ ] **Step 3: Gate and commit**

Run: `make check` — clean.

```bash
git add docs
git commit -m "docs: record the key signature encoding and queue pitch spelling"
```

---

## Completion

After Task 3, open a pull request — this repo requires **all** changes to go through a PR and never
commits to `main` directly.

The PR body should state: what landed (`decode_key` → `KeySignature`); the reverse-engineered
encoding and its corroboration; that `mode = 1 => minor` is inferred not proven, and `mode >= 2` /
out-of-range raises rather than guesses; the mutation results (especially the signed-byte one); that
the corpus sweep decodes all 13 distinct key values with 0 unsupported and skips in CI.
