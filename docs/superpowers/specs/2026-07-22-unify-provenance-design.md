# Unified provenance stamps — design

**Status:** implemented
**Date:** 2026-07-22

Make `.mus` and `.musx` express provenance with one shared type instead of two incompatible ones.
Resolves the OPEN question in `docs/DECISIONS.md`.

## The problem

Both formats record who wrote a file, when, and with what — and the codebase models that twice,
one module apart:

| | `.mus` today | `.musx` today |
|---|---|---|
| `detail.created` | `MusStamp` — date, application, platform | `AppVersion` — major/maint/devStatus/build |
| dates | kept per stamp | **discarded** |
| platform | per stamp | collapsed from both blocks with `or` into one `MusxDetail.platform` |

The two `created` fields share an attribute name and **zero** fields. A caller cannot ask
`detail.created` a generic question across formats — they get a type error or a wrong answer.

This is not a limitation of the formats. `.musx`'s `NotationMetadata.xml` blocks are a strict
*superset* of `.mus` stamps, and the parser throws most of it away.

## Findings from the corpus

401 `.musx` archives, 802 `created`/`modified` blocks:

| Field | Present |
|---|---|
| `year`, `month`, `day` | 802 / 802 |
| `application`, `platform` | 802 / 802 |
| `appVersion` → `major`, `devStatus`, `build` | 802 / 802 |
| `appVersion` → `maint` | 293 / 802 |
| `modifiedBy` | 802 / 802 present; **28 non-empty** |
| `appRegion` | 802 / 802, value `US` in every one |

`.mus` stamps carry year/month/day/application/platform and nothing else — so `.musx` is a superset
by `appVersion` and `modifiedBy`.

`appRegion` is deliberately **not** modelled: a field with one observed value across 802 blocks
carries no information yet. Add it when a second value appears.

## The shared type

```python
@dataclass(frozen=True)
class ProvenanceStamp:
    """When a file was written, by what, on which platform.

    Both formats produce these. `.musx` additionally fills `app_version` and
    may fill `modified_by`; `.mus` leaves both at their defaults.
    """

    year: int
    month: int
    day: int
    application: str          # observed: "FIN"
    platform: str             # observed: "MAC" or "WIN"
    modified_by: str = ""     # .musx only; non-empty in 28 of 802 corpus blocks
    app_version: AppVersion | None = None    # .musx only
```

`MusStamp` is **renamed** to `ProvenanceStamp`. A type named for one format, used by both, is
exactly what confuses a later reader.

```python
@dataclass(frozen=True)
class MusDetail:
    banner: str
    year: int | None
    created: ProvenanceStamp | None = None
    modified: ProvenanceStamp | None = None


@dataclass(frozen=True)
class MusxDetail:
    created: ProvenanceStamp | None
    modified: ProvenanceStamp | None
    metadata_schema: str
    # platform: REMOVED — now carried per stamp
```

`modified_by` is exposed rather than hidden. It is the user's own file, and provenance is the
point of the type. The safeguard that matters is the fixture generator, which already blanks it so
it never reaches the repo — that guards *committing*, not parsing.

## This is a breaking change, and the test rule inverts

Previous slices required existing tests to pass **unmodified**, as proof that behaviour did not
change. That rule does not apply here: `MusxDetail.created` changes type and
`MusxDetail.platform` disappears, so tests asserting on them **must** change. That is correct, not
a smell.

Which removes the usual safety net, so the guard becomes narrower and more specific:

- **`detect_version`'s `label` and `confidence` must not change for any input.** The label for a
  `.musx` still reads `"18.5 dev (build 7098)"`, derived from the same `major`/`maint`/`devStatus`/
  `build` — now reached through `stamp.app_version` rather than directly. **Every existing label
  assertion must pass untouched.** If a label test needs editing, behaviour changed; stop.
- The corpus sweep must report the same tallies as today: 401 `.musx` at schema 18.0, 238 `.mus`
  with 136 `MAC` / 102 `WIN`.
- `modified` remains the layout authority for `.musx` — 267 of 401 files were created by major=16
  and last modified by major=18, and **370 of 401 diverge between the two majors at all**, so
  preferring `created` would misreport most real files. This rule is unchanged and its existing
  test must keep passing.

  (The 2026-07-21 version-detection spec put the first figure at 264. That was read off a single
  row of a tally rather than measured; a direct count gives 267. A correction note is appended
  there rather than rewriting it.)

## Consequences

- `version/musx.py` extracts dates and `modifiedBy` it currently discards, and stops collapsing
  platform across blocks. Each stamp carries its own platform — `.mus` already documents that both
  stamps agreeing "must not be assumed to hold generally".
- `version/detect.py`'s `_musx_label` reaches `app_version` through the stamp.
- `scripts/build_version_fixtures.py` and the `.musx` fixture manifest gain the stamp fields.
- Public exports: `MusStamp` → `ProvenanceStamp`.
- Closes the OPEN question on unifying provenance.

## Out of scope

`appRegion`. Any `.mus` record-pool work. `score.dat`.

After this lands, **`score.dat` decoding is the next roadmap item** — it is the wall between this
project and actual notes, and everything downstream (pitches, rhythms, staves, MusicXML) sits
behind it.
