# Version detection — design

**Status:** approved, not yet implemented
**Date:** 2026-07-21

Identify which Finale version wrote a file, for both `.mus` and `.musx`, before any record parsing
happens. Version detection runs first because the writing version determines the on-disk layout
everything else depends on.

## Findings from the corpus

These are empirical, measured across the full local corpus (639 files: 238 `.mus`, 401 `.musx`) on
2026-07-21. They are the basis for the design and should be re-verified if the corpus changes.

### `.mus` — one magic, version in an ASCII banner

Every `.mus` file in the corpus begins with the same magic, regardless of version:

```
offset 0x00   "ENIGMA BINARY FILE"  then NUL padding
offset 0x20   ASCII banner, NUL-terminated within a fixed-size field
```

Observed banners:

```
Finale(R) 2001 Copyright (c) 1987-2000 Coda Music Technology
Finale(R) 2004 Copyright (c) 1987-2003 Coda Music Technology
Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc.
Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.
Finale(R) 2012 Copyright (c) 1987-2011 MakeMusic Inc.
```

Note the vendor rebrand between 2004 and 2005 (Coda → MakeMusic), and that 2005 uses `MakeMusic!`
with an exclamation mark while 2011/2012 do not. Do not pattern-match on the vendor name.

Distribution: 102× 2001, 36× 2005, 89× 2011, 10× 2012, 1× 2004. All 238 files carried the magic;
none failed to parse.

**There is no per-version byte signature.** An earlier draft of this design proposed a signature
table mapping byte patterns to format generations; the corpus disproved it. Detection for `.mus` is
text-field parsing, not signature matching.

**Hazard — the banner field is not zero-filled on rewrite.** A Finale 2005 file in the corpus reads:

```
"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc." NUL NUL NUL NUL "logy" NUL ...
```

The exact trailing bytes are `\x00\x00logy` — a surviving tail of `...Coda Music Technology`, the
60-character banner written by Finale 2004, partially overwritten by the shorter 54-character 2005
banner. **Read to the first NUL; never decode the whole field.** Doing otherwise yields trailing
garbage on an unknown fraction of files.

The mechanism is confirmed rather than assumed: 2004 is the Coda-branded banner, and it is longer
than the 2005 one that replaced it. A side effect is that residue like this is a partial fingerprint
of the *previous* writer — potentially interesting for provenance, but not something detection
should depend on, since it only survives when the earlier banner was longer.

### `.musx` — zip container, structured metadata

A zip archive with `mimetype` = `application/vnd.makemusic.notation`. Version information lives in
`NotationMetadata.xml` as plaintext XML:

```xml
<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">
  <fileInfo>
    <created>  ... <platform>MAC</platform>
      <appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>
    </created>
    <modified> ... <platform>MAC</platform>
      <appVersion><major>18</major><maint>5</maint><devStatus>dev</devStatus><build>7098</build></appVersion>
    </modified>
```

All 401 files report metadata schema `18.0`; 0 parse failures.

> **Correction, 2026-07-22.** This section's "264" was wrong. It was read off a single row of an
> earlier tally (`major=16`, `release`, `MAC`), not the count of all files created by major 16. A
> direct measurement gives **267** files created by major 16, all 267 of which were last modified by
> major 18 — and **370 of 401** archives diverge between `created` and `modified` at all. The
> conclusion is unchanged and in fact stronger. See `docs/ARCHITECTURE.md` for the current figures.

**`created` and `modified` diverge, and only `modified` matters for parsing.** 264 files were
created by `major=16` but last modified by `major=18`. The last writer determines the on-disk
layout, so `modified` is the layout authority. `created` is retained as provenance, not as a
parsing input.

Other observations:

- `score.dat` is high-entropy obfuscated data. Version detection never reads it — the metadata is
  plaintext. This means detection is cheap and does not depend on solving the obfuscation.
- Archive membership varies: 18 distinct entry-sets across the corpus, differing in which
  `presets/*.preset` files are present. Do not assume a fixed manifest; check membership.
- Platform (`MAC`/`WIN`) is available for `.musx` and was not found in the `.mus` header.

  > **Correction, 2026-07-22:** this was wrong. Platform is recoverable from `.mus` as well — see
  > `docs/superpowers/specs/2026-07-22-mus-header-metadata-design.md` and
  > `docs/ARCHITECTURE.md`. Left here uncorrected in place rather than rewritten, per this
  > project's practice of not rewriting a spec's history.

### Corpus directory labels are not version labels

`corpus/CORPUS.md` names directories after marketing releases, which do not match writing versions —
`holiday_tunes_2013/` contains Finale **2012** files, and the Berklee set mixes 2004 and 2005.

Tests must assert against the in-file banner or metadata, never the containing directory.

### Unresolved: `.musx` major number → Finale marketing year

`.musx` reports `major=15/16/17/18`; `.mus` reports years like `2011`. No file in the corpus carries
both, so nothing here bridges the two numbering schemes. **Deliberately left unresolved.** The
`.musx` label reports the major/maint/build as-is rather than guessing a year. Resolving it needs an
external source; see `docs/DECISIONS.md`.

## Public interface

```python
def detect_version(path: Path) -> FileVersion    # raises NotFinaleFileError
```

```python
class Family(Enum):        MUS, MUSX
class Confidence(Enum):    EXACT, UNKNOWN

@dataclass(frozen=True)
class AppVersion:
    major: int
    maint: int | None
    dev_status: str
    build: int | None

@dataclass(frozen=True)
class MusDetail:
    banner: str            # NUL-trimmed, verbatim
    year: int | None       # parsed from "Finale(R) YYYY"

@dataclass(frozen=True)
class MusxDetail:
    created: AppVersion | None
    modified: AppVersion | None      # the layout authority
    metadata_schema: str
    platform: str | None

@dataclass(frozen=True)
class FileVersion:
    family: Family
    label: str                       # "Finale 2011" | "18.5 dev (build 7098)"
    confidence: Confidence
    detail: MusDetail | MusxDetail
```

Common core plus family-specific detail: nothing is falsely optional, and the `.musx`
created/modified distinction has somewhere honest to live. `label` is the one field every caller can
rely on across families.

## Modules

| Module | Responsibility | I/O |
|---|---|---|
| `models.py` | The dataclasses and enums above | none |
| `family.py` | Header bytes → `Family`, or raise `NotFinaleFileError` | none (takes bytes) |
| `mus.py` | Header bytes → `MusDetail` | none (takes bytes) |
| `musx.py` | Path → `MusxDetail` (must open the archive) | zip read |
| `detect.py` | Public entry point; composes the above, builds `FileVersion` | file open |

Only `detect.py` and `musx.py` touch the filesystem. `family.py` and `mus.py` are pure functions
over `bytes`, which is what makes the header-prefix fixtures sufficient for them.

## Data flow

```
path ──▶ read 0x60-byte header ──▶ family.classify()
                                        │
              ┌─────────────────────────┴──────────────────────────┐
              ▼ MUS                                                ▼ MUSX
        mus.parse(header)                                  musx.read(path)
              │                                                    │
              └──────────────────▶ FileVersion ◀───────────────────┘
```

## Error handling

- **`NotFinaleFileError`** — neither magic matched. The file is not a Finale file at all.
- **`confidence=UNKNOWN`** — the family is established but the version is not parseable (banner
  missing or malformed; `NotationMetadata.xml` absent or lacking `appVersion`). The raw evidence is
  preserved in `detail` so an unrecognized variant is inspectable data rather than an exception.

This split is deliberate: on a reverse-engineering project, encountering an unknown variant is
expected work, not an error condition. The future hex viewer needs to display exactly these files.

## Security

Every input file is treated as hostile, per the `CLAUDE.md` guardrail.

- **Bounded reads.** `.mus` detection reads a fixed 0x60-byte header. No read length is ever derived
  from file content.
- **Zip handling.** Check member existence before reading. **Cap the declared uncompressed size of
  `NotationMetadata.xml` before reading it** — an unbounded read here is a zip-bomb vector. Never
  extract to disk; never trust archive member names as paths.
- **XML parsing.** Use **`defusedxml`**, not stdlib `ElementTree`, which is vulnerable to
  entity-expansion (billion laughs) and external-entity attacks. This is the project's first runtime
  dependency and is justified specifically by parsing attacker-controlled XML.

## Testing

**Committed fixtures — no musical content of any kind.**

- `.mus`: the first 0x60 bytes of real files, as `.bin`. Contains magic and banner only; no musical
  expression. One per observed version, plus one carrying the `logy` trailing-garbage case.
- `.musx`: minimal constructed archives containing only `mimetype` and `NotationMetadata.xml`.
  `score.dat` is deliberately excluded, so no musical content is committed. Cover: created/modified
  divergence, a `WIN` platform file, and a missing-`appVersion` file.

Each fixture gets a manifest entry recording its source file, the bytes taken, and its expected
detection result.

**Corpus sweep (local only, skipped in CI).** When `corpus/` is present, assert every file detects
with `EXACT` confidence and that tallies match the findings above (102/36/89/10/1 for `.mus`; 401
`.musx` at schema 18.0). This is the regression net against 639 real files without committing any.

**Adversarial cases.** Empty file; truncated below 0x60 bytes; a valid zip that is not a `.musx`; a
`.musx` whose `NotationMetadata.xml` is absent, is not XML, or declares a huge uncompressed size;
XML containing an entity-expansion payload. All must raise cleanly or return `UNKNOWN` — never
crash, hang, or allocate unboundedly.

## Out of scope

Reading `score.dat` or the `.mus` record body; the obfuscation; the IR; MusicXML export; any GUI.
Detection reads headers and metadata only.

## Consequences for existing decisions

- Closes **`.mus` coverage** as *both formats in scope* (`docs/DECISIONS.md`).
- Partially answers **format versioning**: version is now detectable, but whether each version needs
  distinct record-parsing logic is still unknown and remains open.
- Adds `defusedxml` as the first runtime dependency; record it in `CLAUDE.md`'s tech-stack list.
