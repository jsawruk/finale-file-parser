# Typed entry/note model — design

**Status:** approved, not yet implemented
**Date:** 2026-07-23

Turn generic `entry` and `note` Records into typed musical values: `Entry` (duration, rest-or-not,
notes) and `Note` (the pitch encoding). This is the first slice where the parsed structure becomes
music. It reads a record's **own** fields only — no cross-pool links, no key.

## Scope boundary

The reference and the corpus place a clean boundary here.

- **Duration is self-contained.** `entry/dura` is the *written* note value in EDU; it decodes to a
  base note-value plus dots with pure arithmetic (verified 100% clean below), needing nothing else.
- **Pitch is only half-resolvable.** `note/harmLev` is a diatonic displacement *relative to the
  key's tonic*, and `note/harmAlt` an alteration *relative to the key* — so `harmLev=0` is C in C
  major but G in G major. Spelling an absolute letter (C♯4) needs the key, which lives in `measSpec`
  reachable only by walking `gfhold → frameSpec → entry`. That is cross-pool link resolution,
  deliberately deferred.

So this slice types what a record carries by itself and stops at the key boundary. **Full pitch
spelling is the immediate next slice** — it will pull in the minimal key linkage.

## Findings from the corpus

Measured over the `entries` pool.

**Entry fields** (of ~34k entries): `dura`, `numNotes`, `isValid`, `isNote` always meaningful;
`note` present when `numNotes > 0`; the rest (`beam`, `stemDetail`, `articDetail`, …) are optional
detail flags not modelled here.

- **`numNotes` equals the number of nested `note` records — exactly, 0 mismatches of 27,474.** A
  rest is `numNotes == 0` (no `note` records); 1545 rests observed. `isNote` is an Enigma boolean
  flag (present = true) that tracks the same distinction.
- **Notes per entry:** 1 (single note) common, 2–5 (chords) observed, 0 (rest).

**Duration (`dura`, EDU where a whole note = 4096):**

| EDU | Note value |
|---|---|
| 4096 | whole |
| 2048 | half |
| 1024 | quarter |
| 512 | eighth |
| 256 | 16th |
| 128 | 32nd |
| 1536 | dotted quarter |
| 3072 | dotted half |
| 768 | dotted eighth |

- **All 34,066 durations decode cleanly** to a base power-of-two note value plus dots — tuplets
  included, because `dura` is the *written* value; tuplet scaling is a separate `tupletStart`
  detail (a later concern, like spelling).

**Pitch (`note/harmLev`, `note/harmAlt`):**

- `harmLev`: signed diatonic displacement from the tonic-at-middle-C. Observed range ≈ −21…14 (about
  ±3 octaves). `harmLev=0` is the tonic in the octave from middle C up; each step is one diatonic
  scale degree; +7 is one octave.
- `harmAlt`: signed alteration relative to the key. `0` diatonic, `+1` sharp, `−1` flat (the format
  allows −8…+7). **Not the displayed accidental** — it is relative to the key signature.

Reference: `docs/eeppd.txt` (Enigma Entry Pool documentation) — the "Note Record / TCD" section
documents this pitch encoding.

## Public interface

A new pure module `src/finale_file_parser/enigma/music.py`, a typed transform over generic Records.

```python
def read_entry(record: Record) -> Entry: ...

class NoteValue(Enum):          # base written note values
    WHOLE = 4096; HALF = 2048; QUARTER = 1024
    EIGHTH = 512; SIXTEENTH = 256; THIRTY_SECOND = 128; SIXTY_FOURTH = 64
    # (down to the smallest observed; extend if a smaller base appears)

@dataclass(frozen=True)
class Duration:
    edu: int                    # raw Enigma Duration Units, verbatim
    base: NoteValue
    dots: int
    @property
    def whole_notes(self) -> Fraction:   # edu / 4096, e.g. Fraction(1, 4) for a quarter

@dataclass(frozen=True)
class Note:
    harm_lev: int               # diatonic displacement from the key's tonic (verbatim)
    harm_alt: int               # alteration relative to the key: 0 natural, +1 sharp, -1 flat
    tie_start: bool
    tie_end: bool
    @property
    def diatonic_step(self) -> int:   # harm_lev % 7  — scale degree from the tonic (0..6)
    @property
    def octave_offset(self) -> int:   # harm_lev // 7 — octaves from the middle-C tonic octave

@dataclass(frozen=True)
class Entry:
    entnum: int
    duration: Duration
    is_rest: bool               # numNotes == 0
    notes: tuple[Note, ...]     # empty for a rest
```

`read_entry` is pure over one `Record` (an `entry`). A caller composes it:
`[read_entry(r) for r in doc.entries.of_tag("entry")]`, or `read_entry(doc.entries.get(entnum))`.
This keeps the typed layer an independent transform over the generic model, the same way every layer
sits on the one below.

**Key-independent, on purpose.** `diatonic_step` and `octave_offset` are relative to the key's
tonic, not absolute letters — deriving `C♯4` needs the key. They are exposed because they are the
structure available *without* cross-pool links; the spelling slice adds the rest.

**Not modelled this slice:** tuplet duration scaling; beams, stems, articulations, lyrics, and the
other optional detail records; anything requiring another pool.

## Coercion and errors

- Field values are strings in the generic model; this layer coerces: `dura`/`numNotes`/`harmLev`/
  `harmAlt` to `int`, the boolean flags (`tieStart`, `tieEnd`) by presence.
- **`MalformedEntryError`** (new, subclasses `FinaleFileError`) — a `dura` that is not a positive
  integer, or does not decode to a base+dots note value; a `numNotes` that disagrees with the note
  count; a `harmLev`/`harmAlt` that is not an integer. The corpus has 0 such cases (100% clean), so
  this fires only on genuinely malformed input — consistent with the score/parse layers raising
  rather than degrading.
- `read_entry` requires the record's tag to be `entry`; a different tag raises `MalformedEntryError`.

## Testing

- Unit tests over synthetic `entry` Records built in-test (not from corpus): a quarter-note single
  pitch; a dotted rhythm (base + dots); a rest (`numNotes=0`, no notes); a chord (2–3 notes);
  negative `harmLev` (below middle C) giving the right `octave_offset`/`diatonic_step` via floor
  division; `harm_alt` of −1/0/+1; tie flags; `whole_notes` fraction for several durations.
- Malformed: non-integer `dura`; a `dura` that is not base+dots (e.g. 1000); `numNotes`
  disagreeing with the note count; wrong record tag — each raises `MalformedEntryError`.
- Corpus sweep (local only, skipped in CI): **every entry in all 401 archives reads without
  raising**; the `numNotes == len(notes)` invariant holds; every `dura` decodes; and rest/note
  counts are within observed ranges. Report counts only.
- Every coercion rule verified by mutation.

## Out of scope

Pitch spelling (needs the key — the immediate next slice). Tuplet scaling. The detail records
(beam/stem/artic/lyric). Cross-pool links. `.mus`. MusicXML export.

## Consequences

- New `enigma/music.py`; `read_entry`, `Entry`, `Note`, `Duration`, `NoteValue`, `MalformedEntryError`
  exported from `finale_file_parser.enigma` and the package root.
- `docs/ARCHITECTURE.md` gains the entry/note encoding facts (EDU durations, the harmLev/harmAlt
  pitch encoding and its key-relative nature) and cites `docs/eeppd.txt`.
- Roadmap next: **pitch spelling** — resolve `harmLev`/`harmAlt` + key (via minimal `gfhold →
  frameSpec → measSpec` linkage) into absolute spelled pitches. Then tuplets, then the detail
  records, toward a MusicXML exporter.
