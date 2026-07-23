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

**Seven pools, each with its own keying:**

| Pool | Keyed by | Notes |
|---|---|---|
| `header` | — | singleton (one `headerData` record) |
| `mappings` | — | singleton (one `mapGroup` record) |
| `options` | record tag name | one record per option type (`beamOptions`, `chordOptions`, …) |
| `others` | `cmper` (+ optional `inci`) | the largest pool; `cmper` is a 16-bit id |
| `details` | `cmper1`+`cmper2` (+ optional `inci`), **or** `entnum` (+ optional `inci`) | mixed keying — see below |
| `entries` | `entnum` | notes/chords/rests; `entnum` is a signed 32-bit id |
| `texts` | `number` (or `type` for `fileInfo`) | community docs: texts calls its cmpers "numbers" |

`details` key signatures observed: `cmper1+cmper2` (79457), `entnum+inci` (16391),
`cmper1+cmper2+inci` (9875), `entnum` alone (1288). Both the pair-keyed and entry-keyed forms are
real and common.

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
    keys: Mapping[str, str]               # e.g. {"cmper": "1"} or {"entnum": "5", "inci": "0"}
    fields: Mapping[str, str | Record | tuple[Record, ...]]

class EnigmaDocument:
    version: str
    header: Record | None                 # singletons
    mappings: Record | None
    options: PoolByTag                    # options.get("beamOptions") -> Record | None
    others: PoolByCmper                   # others.get(cmper, inci=0)  -> Record | None
    details: PoolByCmperPair              # details.get(cmper1, cmper2, inci=0), and
                                          # details.for_entry(entnum, inci=0)
    entries: PoolByEntnum                 # entries.get(entnum) -> Record | None
    texts: PoolByNumber                   # texts.get(number) -> Record | None
```

Each pool offers exactly the lookup its keying supports — `entries` cannot be asked for a `cmper1`,
and a missing record returns `None`, not an error. `details` exposes both its keying forms
explicitly (`get` for the pair-keyed records, `for_entry` for the entnum-keyed ones) rather than
pretending one scheme fits.

**Field values.** A field's value is:
- a `str` (verbatim text, possibly empty) when the element has no child elements;
- a `Record` when it contains a single nested record;
- a `tuple[Record, ...]` when it contains repeated nested records (e.g. an entry's `note` children).

Values are **not coerced** — `"46"` stays a string. Knowing a field is an int, enum, or flag needs
the per-type schemas this slice deliberately omits; coercion belongs to the future typed layer.

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

- Synthetic EnigmaXML documents, hand-written in-test, exercising: each pool's keying; `others` with
  and without `inci`; both `details` keying forms; a repeated nested field (chord notes); a
  4-deep nested field; a missing lookup returning `None`; an absent pool.
- Malformed input: not XML; wrong root element; an entity-expansion payload that `defusedxml` must
  refuse.
- Corpus sweep (local only, skipped in CI): every one of the 401 archives parses; the seven pools
  are present; record counts are within observed ranges; and **no committed fixture carries a
  `fileInfo` copyright or title** (a content-safety assertion, not a corpus one).
- Every parsing rule verified by mutation, per project practice.

## Out of scope

Typed record models (notes, staves, options as structured data). Coercing field values. Anything
`.mus`. MusicXML export. This slice is the generic structural layer only.

## Consequences

- New `src/finale_file_parser/enigma/document.py`; `parse_enigma`, `EnigmaDocument`, `Record`, the
  pool types, and `MalformedEnigmaError` exported from `finale_file_parser.enigma` and the root.
- `docs/ARCHITECTURE.md` gains the EnigmaXML structure facts and the seven-pool keying table.
- The roadmap's "parse EnigmaXML into a model" item becomes: generic structure (this slice) →
  typed records (next), starting with `entries`/`note` since the recursive model already reaches
  them.
