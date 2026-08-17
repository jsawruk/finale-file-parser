# Percussion resolver design

**Status:** approved for implementation

**Date:** 2026-08-17

**Scope:** typed Enigma-layer resolution only; no output changes

## Problem

Finale stores percussion meaning outside the ordinary entry note. An entry's
`percussionNoteCode` identifies a note-code assignment, the staff's
`playbackRoute` selects a percussion map, and `percussionNoteInfo` gives that
code's staff position and duration-specific noteheads. The current reader
ignores this chain and treats every note as pitched music.

The raw `percussionNoteInfo` count is misleading. It is a shipped palette, not
score usage: all 401 corpus `.musx` archives carry it, for 149,533 records in
total. Actual assignments are much smaller and must be found through the full
linkage.

Corpus measurements establish:

- 4,692 `percussionNoteCode` assignments in 10 documents;
- every assignment identity is unique and satisfies `inci == noteID - 1`;
- 605 assignments reach a placement whose staff route selects a percussion
  map;
- 597 of those select a complete `percussionNoteInfo` row;
- eight select no row in that map: all use code 13, all selected maps contain
  four rows, and another map in the document defines code 13;
- every one of the 597 resolved rows has a `harmLev` different from the entry
  note currently interpreted as a pitch.

The last point demonstrates a real fidelity gap, but this slice deliberately
does not change score construction or exported output. It creates the typed,
validated Enigma-layer seam needed by a later IR design.

## Goals

- Resolve only percussion assignments that are used by score placements.
- Hide the palette/assignment/routing join behind one typed interface.
- Preserve legitimate unresolved assignments without guessing from another
  map.
- Validate every identity and field on the path to used data.
- Keep the result placement-aware so one mirrored entry may resolve differently
  on two staves.
- Pin the corpus evidence without reporting filenames or score content.

## Non-goals

- No changes to `ir.py`, `build_score`, MusicXML, the CLI, reports, or current
  conversion output.
- No interpretation of the notehead character values.
- No conversion of `percNoteType` to a MIDI instrument or human-readable drum
  name.
- No legacy `.mus` translation. The known DCL `^DF` and `^DN` records remain
  corroborating format evidence only.
- No public additions to the package-root stable facade.

## Public Enigma-layer interface

Add `finale_file_parser.enigma.percussion` and re-export its public names from
`finale_file_parser.enigma`, not from `finale_file_parser`.

```python
@dataclass(frozen=True)
class PercussionAppearance:
    harm_lev: int
    percussion_type: int
    double_whole_notehead: int
    whole_notehead: int
    half_notehead: int
    closed_notehead: int


@dataclass(frozen=True)
class PercussionNote:
    map_id: int
    note_code: int
    appearance: PercussionAppearance | None


def percussion_notes(
    document: EnigmaDocument,
) -> dict[tuple[int, int], tuple[PercussionNote | None, ...]]:
    ...
```

The dictionary key is `(entry_number, staff_number)`. Its tuple is parallel to
`read_entry(entry).notes`; a `None` means that note has no percussion-code
assignment. Keys exist only for entry placements whose staff selects a
percussion map and which carry at least one percussion assignment.

`PercussionNote.appearance is None` has one precise meaning: the note has a
valid assignment and a selected map, but that map has no definition for the
assigned code. The resolver keeps the selected `map_id` and `note_code` so no
information is lost.

## Resolution flow

The module owns the complete join:

```text
details.percussionNoteCode(entnum, inci, noteID, noteCode)
    -> entries.entry(entnum), note at noteID - 1
    -> locate_entries(document), one or more staff placements
    -> others.playbackRoute(cmper=staff).percMapRefID
    -> others.percussionNoteInfo(cmper=map_id, inci=note_code)
```

Implementation order:

1. Index score `percussionNoteCode` records by `(entnum, noteID)` and validate
   that `inci == noteID - 1`.
2. Read each referenced entry and validate that `noteID` addresses an existing
   note.
3. Resolve the entry's placements with the existing `locate_entries` function.
4. Index score `playbackRoute` records by their staff `cmper`. A route without
   `percMapRefID` is an ordinary staff for this purpose.
5. Index raw `percussionNoteInfo` records by `(map_id, note_code)`, but decode a
   row into `PercussionAppearance` only when a used placement selects it.
6. Build one tuple per `(entnum, staff)`, preserving the entry note order.

Lazy appearance decoding is load-bearing. Thousands of unused palette rows
omit `harmLev`; treating the whole palette as score content would either reject
valid documents or force optional fields into every resolved appearance. Every
used row in the corpus is complete.

## Failure behavior

Add `MalformedPercussionError(FinaleFileError)` for percussion-specific
structural contradictions. Raise it for:

- missing or non-integer assignment identities;
- duplicate `(entnum, noteID)` assignments;
- `inci != noteID - 1`;
- a `noteID` outside the referenced entry's notes;
- duplicate map-definition identities not already rejected by the generic
  document model;
- a selected definition missing any of `harmLev`, `percNoteType`,
  `dwholeNotehead`, `wholeNotehead`, `halfNotehead`, or `closedNotehead`.

Do not raise when a staff has no `percMapRefID`; codes on that placement do not
select percussion notation and are ignored. Do not raise when the selected map
has no row for a valid code; return `PercussionNote(appearance=None)`.

Never search another map for a missing code. The corpus proves that this would
manufacture a plausible answer for the eight unresolved assignments, but gives
no evidence that the other map is the correct one.

Existing errors from entry reading and location resolution remain unchanged;
the percussion module does not wrap them in a less specific exception.

## Tests

### Unit tests

Synthetic `EnigmaDocument` tests cover:

- the complete assignment-to-appearance join;
- output tuple positions matching entry note order;
- a mirrored entry selecting different maps on two staves;
- codes on an ordinary staff being ignored;
- a selected map without the code producing `appearance=None`;
- all six appearance fields;
- malformed numeric fields, duplicate assignments, inconsistent
  `inci`/`noteID`, out-of-range note IDs, and incomplete used definitions.

The tests use the public `percussion_notes` interface. Private indexes are not
tested directly.

### Corpus sweep

One aggregate-only corpus sweep pins:

- 10 documents and 4,692 unique assignments;
- 4,692 zero-based `inci`/`noteID` agreements;
- 605 used percussion placements;
- 597 complete resolutions;
- eight unresolved assignments;
- zero incomplete used definitions.

The sweep reports counts only. It never prints corpus paths, filenames, titles,
record text, or individual note values.

## Documentation

- Add the confirmed linkage and the palette trap to `docs/ARCHITECTURE.md`.
- Update `docs/ROADMAP.md` with the measured resolver status: 149,533 palette
  rows are present, but only 605 assignments select percussion maps in this
  corpus. The earlier 43,470-incidence premise lived in the session queue, not
  in the tracked roadmap, so there is no stale roadmap text to remove.
- Do not change README feature claims because user-visible score output is
  unchanged.

## Deferred follow-up

A separate design and PR may consume this resolver in `build_score`. That work
must decide how the format-neutral IR represents unpitched notes, how
`harm_lev` becomes a display step and octave, which notehead characters can be
named safely, and how MusicXML `<unpitched>` and instrument routing are emitted.
This resolver intentionally makes none of those decisions.
