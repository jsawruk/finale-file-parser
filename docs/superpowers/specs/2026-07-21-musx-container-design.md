# `.musx` container reader — design

**Status:** approved, not yet implemented
**Date:** 2026-07-21

Open a `.musx` archive, enumerate its members, and extract the score stream — without interpreting
any of it. This is the layer everything later reads through. Version detection already exists and
currently opens archives itself; it becomes a client of this module.

## Findings from the corpus

Measured across all 401 `.musx` files in the local corpus on 2026-07-21.

| Property | Observed |
|---|---|
| Archives | 401 |
| Member count | min 5, median 6, max 10 |
| Archives lacking `score.dat` | 0 |
| Archives with duplicate member names | 0 |
| Unsafe member names (absolute, `..`, backslash) | 0 |
| `mimetype` first **and** stored uncompressed | 401 / 401 |
| `score.dat` size | min 86,170 · median 96,427 · max 412,805 bytes |
| Per-archive total uncompressed | min 89,156 · median 100,675 · max 419,972 bytes |
| Distinct **ordered** entry-sets | 22 |

Every member name across the corpus matches this pattern, with no exceptions:

```
mimetype | META-INF/container.xml | NotationMetadata.xml | score.dat
presets/<digits>.preset | graphics/<digits>.jpg
```

Notes that shaped the design:

- **Order is part of the structure.** `mimetype` is always the first entry and always stored
  uncompressed — the ODF/EPUB convention. A reader must not assume alphabetical or arbitrary order.
- **22 ordered entry-sets, not 18.** An earlier survey reported 18 by comparing *sorted* member
  sets. Sorting discards order, which is structurally meaningful here. 22 is the correct count.
- **Archives embed images.** `graphics/1.jpg`, `2.jpg`, `3.jpg` appear in the corpus. This widens
  the fixture content rule (below) beyond musical data.
- **`score.dat` is high-entropy** — already obfuscated, so it barely compresses: the corpus's
  distinct variants total 2.94 MB uncompressed and 2.91 MB stored.
- Nothing hostile occurs naturally in this corpus (no duplicates, no unsafe names). The defences
  below are therefore untestable against real files and **must** be tested against synthetic
  hostile input.

## Module layout

New package `src/finale_file_parser/container/`:

| Module | Responsibility | I/O |
|---|---|---|
| `models.py` | `ContainerEntry`, error types | none |
| `names.py` | Member-name validation | none |
| `musx.py` | `open_musx`, `MusxContainer` | zip read |

`src/finale_file_parser/version/musx.py` is refactored to consume `open_musx` instead of opening
archives and validating the mimetype itself. One module owns archive safety; version detection
stops being a parallel implementation that can drift.

## Public interface

```python
@dataclass(frozen=True)
class ContainerEntry:
    name: str
    size: int              # declared uncompressed size
    compressed_size: int
    compress_type: int     # 0 = STORED, 8 = DEFLATE


class MusxContainer:
    """An open .musx archive. Use as a context manager; it owns the zip handle."""

    entries: tuple[ContainerEntry, ...]   # archive order preserved; mimetype first

    def read(self, name: str, *, max_bytes: int) -> bytes: ...
    def score_stream(self) -> bytes: ...


def open_musx(path: str | os.PathLike[str]) -> MusxContainer: ...
```

```python
with open_musx(path) as container:
    for entry in container.entries:
        print(entry.name, entry.size)
    data = container.score_stream()
```

Two deliberate choices:

- **`max_bytes` is required, with no default.** Every call site states its own bound. A default is
  a bound that silently stops fitting as the caller changes.
- **`score_stream()` returns `bytes`, not a file object.** The size caps are only meaningful when
  the size is known up front, and the reader does not interpret the stream. If streaming is needed
  later (e.g. for the hex viewer over very large files), it is an additive method, not a rewrite.

`entries` preserves archive order because order is structural, not incidental.

## Errors

Reuses the existing `NotFinaleFileError` rather than introducing the roadmap's proposed
`InvalidFinaleFile`. Two names for one condition across two modules is worse than a stale roadmap
line; `docs/ROADMAP.md` is corrected instead.

- **`NotFinaleFileError`** — not a readable zip, or a zip without the Finale mimetype.
- **`FileNotFoundError`** — no such path (unchanged, standard).
- **`CorruptContainerError`** (new, subclasses `FinaleFileError`) — the archive opens and is
  genuinely Finale, but violates a structural safety rule: unsafe member name, duplicate names,
  member count over the cap, or total declared size over the cap.
- **`KeyError`** — `read()` for an absent member. `score_stream()` raises `CorruptContainerError`
  instead when `score.dat` is missing, since a Finale archive without one is malformed rather than
  a caller mistake.

A member whose declared size exceeds `max_bytes` raises `CorruptContainerError` from `read()`.
This differs from `version/musx.py`'s existing behaviour, which degrades to an empty result — that
leniency is right for *optional version metadata* and wrong for *an explicitly requested member*.
The version module keeps its lenient behaviour by catching the error at its own boundary.

## Safety

Every archive is treated as hostile. Nothing is ever extracted to disk.

| Check | Limit | Rationale |
|---|---|---|
| Member name validation | reject *unsafe* names only | Zip-slip. Names reach callers and the future hex viewer; refuse dangerous ones at the boundary rather than trusting downstream. |
| Duplicate member names | rejected | Zip permits them; "which one did you read?" is the ambiguity an attacker wants. |
| Member count | 64 | Corpus max is 10. |
| Total declared uncompressed size | 16 MiB | Corpus max is 419,972 bytes per archive (median 100,675). A per-member cap alone does not stop many members each just under it. |
| Per-member read | caller-supplied `max_bytes` | Checked against the declared size *before* reading. |
| Mimetype | must equal `application/vnd.makemusic.notation` | Moved from `version/musx.py`. |

Caps sit roughly 6-40× above observed maxima — loose enough not to reject real files, tight enough
to bound an attack. They are stated as named constants so a future corpus that exceeds one forces a
deliberate change rather than a silent failure.

**Names: reject unsafe, allow unknown.** The reader raises only on names that are genuinely
dangerous — absolute paths, `..` segments, backslashes, control characters, empty names. A name
that is merely *unfamiliar* (a member a future Finale release adds) is allowed through and appears
in `entries` as data.

This is a deliberate split from the fixture generator, which does enforce a strict allowlist of
known names. The asymmetry is the point: we control what gets committed, so there the conservative
rule is free; but rejecting an unrecognised archive would contradict the principle that unknown
variants stay inspectable, and would make a new Finale member name break version detection outright
instead of surfacing something to investigate.

## Fixtures

`scripts/build_container_fixtures.py` sweeps the corpus and emits one synthetic archive per
observed ordered entry-set (22).

**Content rule — no payload bytes from the corpus, ever.** Only *structure* travels: member names,
their order, compression method, and declared uncompressed lengths. Every payload is regenerated.
This is stricter than the version-detection fixtures, which kept real metadata XML; it has to be,
because `score.dat` is the musical work and `graphics/*.jpg` may be licensed artwork.

- Payloads are a **repeating pattern**, so declared sizes stay real (2.94 MB total) while stored
  size collapses to tens of KB. The size caps read declared size, so nothing under test is weakened.
- Member names are **validated against the name pattern**, not copied blindly — a member named
  after a piece cannot ride along.
- `mimetype` is written first and stored uncompressed, matching all 401 observed archives.
- The generator hard-fails rather than emitting anything it cannot validate.

## Testing

**Synthetic fixtures (CI):** all 22 variants open, enumerate in the right order, and yield a
`score_stream()` of the declared length.

**Corpus sweep (local only, skipped in CI):** every one of the 401 archives opens, enumerates, and
yields a `score_stream()` whose length matches its declared `score.dat` size.

**Adversarial (constructed in-test, never from the corpus):** zip-slip names (`../`, absolute,
backslash); duplicate member names; member count over cap; total size over cap; a member whose
declared size exceeds the caller's `max_bytes`; an archive with no `score.dat`; a valid zip with
the wrong mimetype; a `.mus` file passed to `open_musx`; a truncated/corrupt archive.

Because nothing hostile occurs in the corpus, **each defence must be verified by mutation** —
delete the check, confirm the corresponding test fails, restore. This project has produced tests
that passed with the behaviour under test removed in five consecutive review rounds; a defence
without a mutation-verified test is not considered covered.

## Out of scope

Interpreting `score.dat` (the obfuscation), the `.mus` container, the IR, MusicXML export, any GUI.
This layer extracts bytes and reports structure.

## Consequences

- `version/musx.py` becomes a client of `container/`; its behaviour and public results are
  unchanged, and its existing tests must continue to pass untouched as the proof of that.
- `docs/ROADMAP.md` Phase 1 items are corrected: `open_musx` supersedes the `InvalidFinaleFile`
  wording, and the "author a public-domain fixture" item is replaced by the synthetic-profile
  approach, which is what makes CI coverage possible without committing a real score.
