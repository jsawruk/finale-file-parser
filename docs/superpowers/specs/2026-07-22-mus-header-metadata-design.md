# `.mus` header metadata — design

**Status:** implemented
**Date:** 2026-07-22

Parse the two metadata stamps in a legacy `.mus` header into created/modified records carrying a
date, application tag, and platform — making `.mus` and `.musx` report comparable provenance.

## Why this slice, and what it is not

The roadmap called for a "legacy `.mus` container reader", by analogy with the `.musx` container.
**That analogy does not hold.** A `.mus` file is a monolithic binary with no member table, no
directory, and no confirmed record framing. There is no container abstraction to build.

Investigation did find a well-defined header region, which is what this slice implements. Locating
the internal record pools remains open-ended research and is explicitly out of scope.

## Findings from the corpus

Measured across all 238 `.mus` files in the local corpus on 2026-07-22.

Two metadata stamps sit at fixed offsets. Both are present in every file:

| Field | Created stamp | Modified stamp |
|---|---|---|
| `year - 1900`, `month`, `day` (3 × u8) | `0x66` | `0x8C` |
| Application tag, NUL-terminated | `0x70` | `0x96` |
| Platform tag, NUL-terminated | `0x74` | `0x9A` |

| Property | Observed |
|---|---|
| Files with the `FIN\0` tag at both `0x70` and `0x96` | 238 / 238 |
| Date fields plausible (year 1980-2030, month 1-12, day 1-31) | 476 / 476 |
| `created <= modified` | 238 / 238 |
| Application tag | `FIN` in all 476 stamps |
| Platform tag | `MAC` in 136 files, `WIN` in 102 — identical in both stamps in every file |
| Date range | 1998 - 2012 |

Notes:

- **Platform is recoverable for `.mus`.** Earlier documentation recorded platform as `.musx`-only;
  that was wrong.
- **No file in this corpus was edited across platforms** — both stamps always agree. The parser
  must not assume that holds generally; each stamp carries its own platform.
- The date encoding is the classic C `tm` convention (`year - 1900`).

### The plist trailer — recorded, not implemented

89 of 238 files end in a macOS XML plist occupying the last 1-3% of the file (938-1694 bytes).
It is **Mac-only**: 89 of 136 `MAC` files, 0 of 102 `WIN` files. It appears to be appended OS-level
metadata rather than score data. Out of scope here; recorded so the next investigation starts from
it rather than rediscovering it.

### A hypothesis that did NOT survive

An initial observation suggested `.mus` might share `.musx`'s record-type numbering (`10001`,
`10002`, ...), which would have meant work on either format informed the other. Tested by scanning
all 238 files for those values as aligned little-endian `u16`: occurrence rates (e.g. `10001` in 98
of 238 files, 119 occurrences) sit close to the ~0.4-hits-per-file-per-id baseline expected by
chance in files dense with small integers and zero runs. **The hypothesis is not supported.** It is
recorded here so it is not re-derived from the same single-file coincidence.

## Public interface

```python
@dataclass(frozen=True)
class MusStamp:
    """One provenance stamp from a .mus header."""
    year: int
    month: int
    day: int
    application: str      # observed: "FIN"
    platform: str         # observed: "MAC" or "WIN"


@dataclass(frozen=True)
class MusDetail:
    banner: str
    year: int | None
    created: MusStamp | None = None      # new
    modified: MusStamp | None = None     # new
```

The two new fields **default to `None`**, so every existing construction site and test keeps
working unchanged. Those existing tests passing untouched is the proof that this slice adds
information without altering behaviour.

`MusDetail` now names its fields `created`/`modified` to match `MusxDetail`, but the two are not
interchangeable: `MusDetail`'s pair is a `MusStamp` (date, application, platform) while
`MusxDetail`'s is an `AppVersion` (major/maint/devStatus/build) — they share zero fields. Both
formats expose created/modified provenance, but `.mus` records *when and where* a file was written
while `.musx` records *which application version* wrote it. A caller cannot ask "the same
question" of `detail.created` generically across formats. `detect_version`'s `label` and
`confidence` are unchanged — they still derive from the banner year alone. The stamps are detail,
not identity.

See `docs/DECISIONS.md`'s open question on unifying the two: `.musx`'s metadata blocks carry the
same year/month/day/application/platform fields a `MusStamp` models, so a future slice could make
`.musx` produce `MusStamp` provenance too, closing this gap for real instead of just documenting
it.

## Parsing rules

- **Never raises.** `mus.parse` is already contract-bound never to raise; an unparseable stamp
  yields `None` for that stamp, with the banner and year unaffected. An unfamiliar `.mus` variant
  stays inspectable.
- A stamp parses only if its date is plausible (year 1980-2030, month 1-12, day 1-31) **and** its
  application tag is non-empty. A stamp failing either test is `None` rather than partially filled —
  half a stamp is worse than none, because a caller cannot tell which half to trust.
- Tags are read to the first NUL and decoded `latin-1`, matching the existing banner handling.
- The header slice is bounded and fixed. No length is ever derived from file content.

## Header read size

`family.HEADER_SIZE` is `0x60` today and is pinned by an invariant test to equal
`BANNER_OFFSET + BANNER_FIELD_SIZE`. The stamps extend to `0x9D`.

Add a separate `MUS_METADATA_SIZE = 0xA0` in `version/mus.py`. `detect_version` reads
`max(HEADER_SIZE, MUS_METADATA_SIZE)` bytes once and passes the buffer to both `classify` (which
inspects only the leading magic) and `mus.parse`. `HEADER_SIZE` keeps its banner-geometry meaning
and its invariant test unchanged.

## Testing

- Unit tests over synthetic headers built in-test, covering: both stamps present; an implausible
  date; a missing application tag; a `WIN`/`MAC` pair; a truncated header shorter than `0x9D`.
- The existing `.mus` header-prefix fixtures in `tests/fixtures/version/` are `0x60` bytes and do
  **not** reach the stamps. Regenerate them at `0xA0` so they do, and extend `MANIFEST.toml` with
  the expected created/modified values. The fixtures still contain only magic, banner, and
  provenance stamps — no musical content.
- Corpus sweep: assert all 238 files yield both stamps, `created <= modified`, application `FIN`,
  and the platform tallies 136 `MAC` / 102 `WIN`.
- Every parsing rule verified by mutation, per project practice.

## Out of scope

Internal record pools; the plist trailer's contents; any `.mus` score data. This slice reads a
fixed header window and nothing else.

## Consequences

- Closes the stale open question **"`.musx` only, or `.mus` too?"** as DECIDED: both formats are in
  scope, evidenced by shipped `.mus` version detection and this slice.
- Corrects the `docs/ARCHITECTURE.md` claim that platform is `.musx`-only.
- Corrects the roadmap's "legacy `.mus` container reader" wording, which presumes a container that
  does not exist.
