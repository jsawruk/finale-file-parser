# EnigmaXML document model — design

**Status:** approved, not yet implemented
**Date:** 2026-07-22

Parse raw EnigmaXML bytes into a navigable, keyed document model. This is the layer every typed
record model (notes, staves, options) will sit on. It models the format's *uniform structure*, not
any of its ~191 individual record types.

## Why a generic structural model, not typed records

The `<finale>` document is seven pools of records. Across just 120 corpus files there are **191
distinct record types** (100 in `others`, 48 in `details`, 35 in `options`), and the full corpus has
more. Hand-modelling 191 schemas in one slice is neither feasible nor useful — most would be
field-for-field data-transfer objects.

But every record, whatever its type, shares one structure: it lives in a pool, is identified by a
key appropriate to that pool, and carries fields that are either scalar text or nested records. This
slice models *that*. It gives "fetch any record by pool + key" across all 191 types at once, and is
the foundation typed accessors are added onto later.

## Findings from the corpus

Measured over decoded EnigmaXML from the corpus.

**Root:** `<finale version="18.0">` in every file — the *schema* version, not the writing
application's (those span majors 15-18). Namespace `http://www.makemusic.com/2012/finale`.

**Seven pools.** Records carry key-like attributes (`cmper`, `cmper1`/`cmper2`, `entnum`, `inci`,
`number`, `type`, and others such as `part`), but **this slice does not build keyed lookup** — see
"Keying deferred" below. This layer preserves every record in document order, addressable by tag.

| Pool | Typical record identity | Notes |
|---|---|---|
| `header` | — | one `headerData` record |
| `mappings` | — | one `mapGroup` record |
| `options` | record tag | one record per option type (`beamOptions`, …) |
| `others` | tag + `cmper` (+ `inci`, `part`, …) | the largest pool |
| `details` | tag + `cmper1`+`cmper2`, or + `entnum` (+ `inci`) | mixed |
| `entries` | `entnum` | notes/chords/rests |
| `texts` | tag + `number` (or `type` for `fileInfo`) | community docs call its cmpers "numbers" |

### Keying deferred — why this slice does not offer `get(cmper)`

The corpus survey disproved the simple "each record has a key appropriate to its pool" premise, in
two stages:

- **`cmper` is not a key.** In one file, `cmper=1` appears across **54 different record types** in
  `others`. Identity requires the tag: `articDef cmper=1` and `measSpec cmper=1` are different
  records.
- **Even `(tag, cmper, inci)` is not unique.** `measSpec` carries a `part` attribute that the first
  survey missed — a score version plus per-linked-part variants share one cmper:
  ```
  <measSpec cmper="1"/>
  <measSpec cmper="1" part="1" shared="true"/>
  <measSpec cmper="1" part="2" shared="true"/>
  ```
  So more key attributes exist than an initial pass reveals, and there is no confidence that all of
  them have been found across 191 record types.

A dict keyed by a fixed tuple would **silently drop** whichever variant lost the collision — the
exact data-loss failure this project guards against. So keyed lookup is its own later slice, taken
once the key attributes are fully mapped. This slice preserves everything and lets a caller
navigate by tag and read raw attributes; nothing is dropped.

**Fields nest up to 4 deep.** A field is a child element that is either scalar text
(`<charMain>46</charMain>`) or contains nested records (`<fretboard><cell>…</cell></fretboard>`).
Notably `entry/note` is a nested field — a chord's notes are nested records inside an entry — so the
recursive representation reaches the musical core.

**Empty field text is common** (`<autoHorz></autoHorz>`): flags and defaults. Kept verbatim; the
generic layer does not interpret them.

**Performance:** whole-document parse via `ElementTree` runs ~138 ms/file including decode, on
documents up to 10.8 MB. **Whole-document parsing is viable; streaming is not needed.**

## Content-safety — this format carries copyrighted text

The `texts` pool's `fileInfo` records contain the **title, composer, and full copyright notice**
(`"Copyright © 2012 by MakeMusic, Inc. …"`) directly in the decoded XML — the same bibliographic
data scrubbed from the `.musx` metadata fixtures earlier, now in the score payload itself.

**Committed fixtures are hand-written synthetic EnigmaXML with invented records — no corpus content
at all.** The parser is indifferent to whether records are real, so synthetic documents exercise it
fully. A test asserts no committed fixture contains a `fileInfo` copyright/title, guarding the rule
mechanically rather than by intent.

## Public interface

```python
def parse_enigma(xml: bytes) -> EnigmaDocument: ...
```

Operates on `bytes` and is **pure** — it does not call `score_xml` or `open_musx`. A caller
composes them: `parse_enigma(score_xml(path))`. Decode and parse stay independently testable, the
same way `enigma/score.py` consumes `container/` without owning it.

```python
@dataclass(frozen=True)
class Record:
    tag: str                              # "articDef", "entry", "note", …
    attrs: Mapping[str, str]              # ALL attributes, verbatim — no key/non-key distinction
    fields: Mapping[str, str | tuple[str, ...] | Record | tuple[Record, ...]]

@dataclass(frozen=True)
class Pool:
    records: tuple[Record, ...]           # every record, in document order
    def of_tag(self, tag: str) -> tuple[Record, ...]: ...   # all records with this tag

class EnigmaDocument:
    version: str
    header: Pool                          # one uniform Pool type for all seven;
    mappings: Pool                        # header/mappings simply hold one record
    options: Pool
    others: Pool
    details: Pool
    entries: Pool
    texts: Pool
```

One uniform `Pool` type for all seven pools. Records are preserved in document order and nothing is
dropped. `Record.attrs` holds *all* attributes verbatim rather than a curated `keys` subset,
because this slice does not yet decide which attributes are keys — a consumer reads `attrs["cmper"]`
directly. `of_tag` is the one navigation primitive: "every `measSpec` in `others`, in order,"
which the caller can then filter by `part`/`cmper` itself until the keyed-lookup slice lands.

**Field values.** Group a record's child elements by tag name. A field's value is:
- a `str` (verbatim text, possibly empty) — no child elements, appears once;
- a `tuple[str, ...]` — no child elements, appears more than once (e.g. `shapeData/data`);
- a `Record` — has child elements, appears once;
- a `tuple[Record, ...]` — has child elements, appears more than once (e.g. an entry's `note`).

Verified across the corpus: no tag is scalar in one record and nested in another, so a tag's value
type is consistent. Values are **not coerced** — `"46"` stays a string. Knowing a field is an int,
enum, or flag needs the per-type schemas this slice deliberately omits; coercion belongs to the
future typed layer.

## Safety

The XML is extracted from an untrusted file. Parse with **`defusedxml`**, never stdlib
`ElementTree` — the same reason it is already the project's one runtime dependency. This refuses
entity-expansion and external-entity payloads.

The input is already bounded: `score_xml` caps its output at `MAX_INFLATED` (64 MiB) before this
layer sees it. No additional size cap is needed here, but the parser must not itself amplify —
build the model in a single pass without copying subtrees repeatedly.

## Errors

- **`MalformedEnigmaError`** (new, subclasses `FinaleFileError`) — the bytes are not parseable XML,
  or the root is not `<finale>`. Consistent with `score_xml`'s posture: a caller asking for the
  document asked for a specific thing.
- A pool that is absent yields an empty pool, not an error — a document missing `texts` is unusual
  but not malformed.

## Testing

- Synthetic EnigmaXML documents, hand-written in-test, exercising: all seven pools; `of_tag`
  returning records in document order; a record's raw `attrs`; a repeated scalar field
  (`tuple[str, ...]`); a repeated nested field (chord notes → `tuple[Record, ...]`); a 4-deep nested
  field; the `measSpec`-style collision (score record plus per-`part` variants sharing a cmper) all
  preserved in `of_tag`; an absent pool yielding an empty `Pool`.
- Malformed input: not XML; wrong root element; an entity-expansion payload that `defusedxml` must
  refuse.
- Corpus sweep (local only, skipped in CI): every one of the 401 archives parses; the seven pools
  are present across the sweep; an `entry` with a nested `note` field is reached. **No committed
  fixture carries a `fileInfo`** (content-safety, not a corpus assertion).
- Every parsing rule verified by mutation, per project practice.

## Out of scope

**Keyed lookup** (`get(cmper)`, etc.) — deferred to its own slice once the full key-attribute set is
mapped. Typed record models. Coercing field values. Anything `.mus`. MusicXML export.

## Consequences

- New `src/finale_file_parser/enigma/document.py`; `parse_enigma`, `EnigmaDocument`, `Pool`,
  `Record`, and `MalformedEnigmaError` exported from `finale_file_parser.enigma` and the root.
- `docs/ARCHITECTURE.md` gains the EnigmaXML structure facts, the seven pools, and the finding that
  no fixed key set uniquely identifies a record (the `measSpec`/`part` case).
- The roadmap's "parse EnigmaXML into a model" item becomes: generic structure preserving all
  records (this slice) → **keyed lookup** once key attributes are mapped → typed records. The
  recursive model already reaches `entry`/`note`, so typed entries can follow either.
