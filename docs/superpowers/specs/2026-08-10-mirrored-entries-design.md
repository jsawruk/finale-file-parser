# Mirrored entries: design

**Goal:** let one entry sound in more than one place in the score, so a document
containing a Finale *mirror* reads instead of being rejected.

**Status:** design approved 2026-08-10. Implementation not started.

## The problem

A **mirror** is a staff that displays another staff's music rather than holding
its own copy. Coda's own term: `docs/eeppd.txt` warns that "mirrors and voice 2
create complications", and Finale shipped a Mirror Tool for making them. An
engraver reaches for one when two parts play the same thing — a doubled line, a
cue, a piano reduction of what the winds are doing.

Stored, there is **one** set of entries and **two** `gfhold` records naming the
same entry span. Walking the frame chain, the same entries turn up twice, in two
different places in the score.

`locate_entries` maps an entry to exactly one `EntryLocation`, and raises when a
second frame claims one:

    raise MalformedScoreError(f"entry {entnum} placed by more than one frame")

So a document Finale wrote deliberately is refused. This is the last reader-side
DCL failure; the remaining ones are properties of the files (see
`docs/ROADMAP.md` item 3).

## What the corpus contains

Measured 2026-08-10 across the DCL cohort — 133 documents readable, 6 refused as
empty. The implementation should re-derive these numbers as corpus pins rather
than copy them from here:

| Fact | Value |
| --- | --- |
| Documents where two `frameSpec` records share an entry span | 5 |
| Documents where two `gfhold` records name that span — i.e. the mirror reaches the score | **1** (`Bach Concerto.MUS`) |
| Entries in that document holding more than one location | **239** |
| Locations per multi-placed entry | exactly 2, never more |
| Entries placed at the *same* (staff, measure, layer) twice | **0** |
| Staves involved | 4 and 14, always the same measure on both |
| Entries placed once multi-location is allowed | 5,407 of 5,407, **0 orphans** |

Two consequences worth stating plainly:

- The other four documents need no change. Their duplicate `frameSpec` is never
  named by a `gfhold`, so nothing places those entries twice.
- **The mirror is the only thing wrong with `Bach Concerto.MUS`.** Allowing
  multiple locations places every entry with no orphans, so this is not the
  first of several blockers.

## The file does not say which staff is the copy

Nothing in the record marks one placement as the original and the other as the
mirror. What is stored is symmetric: two `frameSpec` records name the same span,
and two `gfhold` records name those frames. Direction could only be *inferred* —
from the lower frame `cmper`, or from `gfhold` order — and both are guesses of
the kind `docs/DECISIONS.md` exists to keep out of the code.

The design therefore treats the placements as **peers**. This costs nothing:
a mirrored passage remains identifiable as *an entry whose location tuple holds
more than one member*, so "is this staff independent music or a duplicate?"
stays answerable without inventing a direction.

## Design

### `locate_entries` returns a tuple of locations

```python
def locate_entries(doc: EnigmaDocument) -> dict[int, tuple[EntryLocation, ...]]:
```

An entry names every place the file puts it, ordered by the frame walk.
`EntryLocation` itself is unchanged — no `is_mirror` field, because mirroring is
a property of the mapping, not of a location.

This is a **breaking change to a published export** (`locate_entries` and
`EntryLocation` are both in `finale_file_parser.__all__`, shipped in 0.2.0), so
the release is **0.3.0**. Chosen over adding a parallel function because the
single-location form has no correct behaviour left: on a mirror it must either
raise, drop half the music, or guess a source.

### The double-place check narrows, it does not disappear

Today any second placement raises. After this change:

- an entry may hold several **distinct** locations — that is a mirror;
- the same `(staff, measure, layer)` twice is still `MalformedScoreError`.

The narrowed check still guards something real: the corpus has 239 multi-placed
entries and **zero** exact-duplicate placements, so no legitimate document
depends on the looser reading, and a genuine double-walk still fails loudly.

The orphan check is untouched.

### `build_score` emits the entry into each location

`to_ir.build_score` currently does:

```python
here = location.get(entnum)
if here is None or record is None:
    continue
```

It becomes a loop over the tuple. Nothing downstream needs to change, because
`_event` is already built per location: it takes `here.staff` for the staff
transposition and `here.key_signature` for spelling. A mirror onto a
differently-transposing staff therefore re-spells correctly with no new code.

Durations, lyrics, articulations and fingerings are keyed by `entnum` and
duplicate along with the note. That is correct — the mirrored staff prints the
same syllables and the same marks.

MusicXML has no mirror concept, so writing the notes onto both staves is the
faithful rendering of what Finale displays.

## Error handling

| Case | Before | After |
| --- | --- | --- |
| Entry claimed by two frames, different locations | `MalformedScoreError` | placed in both |
| Entry claimed twice at the same (staff, measure, layer) | `MalformedScoreError` | `MalformedScoreError` (unchanged) |
| Entry no frame places | `MalformedScoreError` (orphan) | unchanged |
| `gfhold` frame naming a missing `frameSpec` | `MalformedScoreError` | unchanged |
| `next`-chain cycle | `MalformedScoreError` | unchanged |

## Testing

**Unit** (`tests/enigma/test_location.py`), synthetic documents only:

- two `gfhold` records naming frames that share one span → the entry holds two
  locations, differing in staff, agreeing in measure and key.
- the same `gfhold` slot reaching one entry twice → still raises.
- an ordinary single-placement document → one-element tuple, so the common path
  is covered by the same shape.

**Corpus** (`tests/enigma/test_mus_dcl_score_corpus_sweep.py`):

- `DOCUMENTS_WITH_MIRRORED_FRAMES = 5` stays — it counts shared spans, which
  this change does not affect.
- new pin: documents where the mirror reaches the score (1), and entries holding
  more than one location (239). Pinned so that a regression which silently stops
  duplicating shows up as a number rather than as "it still parses" — the
  failure mode this project has hit before.
- `EXPECTED_SCORES` 131 → 132, `EXPECTED_MALFORMED` 2 → 1, and
  `EXPECTED_PARTS` / `MEASURES` / `EVENTS` / `PITCHES` all rise as the document
  enters the counts. **Measure the new values, do not predict them**, and check
  each moves in the expected direction: a count that *drops* means semantics
  changed, not coverage, and must be understood before the pin is touched.

**Export** (`tests/export/`): across the mirrored measures of `Bach Concerto.MUS`,
staff 4 and staff 14 hold the same events.

**Every new test gets the mutation check.** Delete or invert the thing it guards
and confirm the test fails. A test that passes against the unfixed code is not
evidence.

## Documentation

- `mus_document.UNTRANSLATED`: drop the mirror entry; add a narrower one for the
  limit below.
- `docs/ROADMAP.md`: close item 2.
- `scripts/format_spec/__main__.py`: rewrite the "One mirror" paragraph in the
  supported-formats section. It currently explains why the reader refuses a file
  it understands; it becomes a description of how mirrors are read. Regenerate
  with `make spec`.
- `docs/DECISIONS.md`: record that mirror direction is deliberately not inferred.

## Known limit, deliberately not closed

Finale's Mirror Tool appears to allow a mirror to carry its own transposition or
octave displacement. No field carrying that has been identified, and both staves
in the only corpus mirror transpose by zero — so nothing here can test it, and
guessing at an offset would be fitting a rule to a single point. Mirrors are
therefore read as *the same music in both places*, which is right for this
corpus and may be incomplete in general. Recorded in `UNTRANSLATED` rather than
claimed as done.

## Out of scope

- Round-tripping a mirror back out as a mirror. The IR materialises the notes on
  both staves; nothing preserves the fact for a writer, and there is no writer.
- 2011-era and `.musx` mirrors. Measured, not assumed: **0 of 99** 2011-era
  `.mus` documents and **0 of 401** `.musx` documents contain a shared entry
  span, so there is nothing to verify against in either container. The change
  is in container-independent code (`enigma/location.py`, `enigma/to_ir.py`) and
  would serve them if such a document appeared, but no test can prove that here
  and none will claim to.
