# EnigmaXML keyed lookup — design

**Status:** approved, not yet implemented
**Date:** 2026-07-23

Add keyed lookup to the EnigmaXML document model. The previous slice preserved every record but
offered only `of_tag` (linear scan); this adds O(1) `get` by a record's identity, and `all_with`
for the linked-part case — without dropping any record.

## Why this is now safe

The document-model slice deferred keyed lookup because no fixed key set was known to be unique:
`cmper=1` spans 54 record types, and `measSpec` carries a `part` attribute that an early survey
missed. This slice is built on a **complete** survey.

## Findings from the corpus

Every record's identity attributes, and a uniqueness check, measured across **all 401 archives —
3.1 million records — with zero collisions**:

| Pool | Identity | Records checked |
|---|---|---|
| `options` | tag alone (one record per option type) | 13,691 |
| `others` | tag + `cmper` + `inci` + `part` | 1,739,819 |
| `details` | tag + (`cmper1`+`cmper2` **or** `entnum`) + `inci` + `part` | 1,065,174 |
| `entries` | `entnum` (single tag `entry`) | 228,957 |
| `texts` | tag + `number` **xor** `type` | 67,438 |

Details that shaped the design:

- **`part` is the identity attribute an earlier survey missed** — Finale's linked parts: a score
  record (no `part`) plus per-part variants (`part="1"`, `part="2"`) sharing one cmper. `shared`
  co-occurs with `part` but is a data flag, not identity — dropping it from the key still gives zero
  collisions.
- **`entries`** has one tag (`entry`); `entnum` is unique; `prev`/`next` are linked-list pointers,
  not keys.
- **`texts`** records carry `number` **or** `type`, never both, never neither (`type` only on
  `fileInfo`, `number` on everything else).
- **`header`/`mappings`** are singletons; `mappings`' `minInclusive`/`maxExclusive` are data.

## Public interface

Five keyed subclasses of the existing `Pool`. Each inherits the shipped `.records` and `.of_tag()`
unchanged, and adds lookup fitting its identity. `header`/`mappings` stay plain `Pool` with a new
`.record` singleton convenience.

```python
class OptionsPool(Pool):
    def get(self, tag: str) -> Record | None

class OthersPool(Pool):
    def get(self, tag: str, cmper: int | str, inci: int | str = 0,
            part: int | str | None = None) -> Record | None
    def all_with(self, tag: str, cmper: int | str) -> tuple[Record, ...]

class DetailsPool(Pool):
    def get(self, tag: str, cmper1: int | str, cmper2: int | str, inci: int | str = 0,
            part: int | str | None = None) -> Record | None
    def for_entry(self, tag: str, entnum: int | str, inci: int | str = 0,
                  part: int | str | None = None) -> Record | None
    def all_with(self, tag: str, cmper1: int | str, cmper2: int | str) -> tuple[Record, ...]

class EntriesPool(Pool):
    def get(self, entnum: int | str) -> Record | None

class TextsPool(Pool):
    def get(self, tag: str, number: int | str | None = None,
            type: int | str | None = None) -> Record | None
```

- **`get` returns the one exact record** for a full identity, or `None`. The full key (including
  `part`) is unique over 3.1M corpus records, so a single return is correct. Omitting `part`
  addresses the score record (`part` absent); passing it addresses a specific part variant.
- **`all_with` returns every record sharing a cmper** — the score record plus all per-part variants,
  in document order — for callers who need the linked-part set. Nothing is dropped.
- **`details` exposes both keying forms** (`get` for the cmper-pair records, `for_entry` for the
  entnum-keyed subset like `perfData`) rather than pretending one scheme fits.
- **Argument normalization:** the model stores attribute values as strings (`attrs["cmper"] ==
  "1"`), so lookups normalize every key argument to `str`. `get("articDef", 1)` and
  `get("articDef", "1")` are equivalent.

`EnigmaDocument.others`, `.details`, `.entries`, `.texts`, `.options` are now typed as the
corresponding subclass; `.header`/`.mappings` stay `Pool`. Reading a pool is source-compatible — the
shipped `.records`/`.of_tag` still resolve, and the narrowed types are subtypes so a `Pool`
annotation still holds. The one thing that changes is `EnigmaDocument`'s own construction signature
(it now takes the typed pools), but only `parse_enigma` constructs it, so no reader breaks.

## Indexes

Each keyed pool builds its indexes once, when constructed at parse time:

- an **exact-key dict** — the full identity tuple → `Record` — backing `get` in O(1);
- a **cmper multimap** — `(tag, cmper)` → records in document order — backing `all_with`.

`parse_enigma` already iterates each pool's records once to build them; index construction is one
dict insert per record on that existing pass, no extra traversal. Indexes are built eagerly (a
parsed document is queried far more than once), and the pools stay immutable after construction.

## Safety and errors

- **Duplicate identity is a defect, and this slice makes it loud.** `get`'s single-return contract
  depends on identity uniqueness. If two records collide on a full identity key while the index is
  built, raise `MalformedEnigmaError` rather than silently keeping one. The corpus proves this never
  happens on real files (0 of 3.1M), so a collision means genuinely malformed input.
- No new I/O, no new dependency. Pure over the parsed model.

## Testing

- Unit tests over synthetic documents: exact `get` for each pool; `get` omitting `part` hits the
  score record while a specific `part` hits its variant; `all_with` returns the score plus every
  part variant in order; `details.for_entry`; `int` and `str` key arguments equivalent; a missing
  key returns `None`; `header.record`/`mappings.record` singletons; a duplicate-identity document
  raises `MalformedEnigmaError`.
- Corpus sweep (local only, skipped in CI): **assert full-identity uniqueness holds across all 401
  archives** (this is the guarantee `get` rests on); and that a known lookup pattern round-trips —
  e.g. every `entry`'s `entnum` is retrievable via `entries.get`. Report counts only, never record
  values.
- Every rule verified by mutation: dropping `part` from the key must fail a test (the
  measSpec-variant collision), and so must dropping the uniqueness check.

## Out of scope

Typed record models (coercing fields to notes/pitches). Interpreting what a cmper *references*
(cross-pool links). Anything `.mus`. This slice is keyed access to the existing generic records.

## Consequences

- `enigma/document.py` gains the five pool subclasses and the singleton `.record`; the new pool
  types and any are exported as needed. `parse_enigma` constructs the typed pools.
- `docs/ARCHITECTURE.md` records the complete per-pool identity table and that it is unique across
  the corpus.
- The roadmap's "keyed lookup" item is done; **typed record models** (notes first) become next.
