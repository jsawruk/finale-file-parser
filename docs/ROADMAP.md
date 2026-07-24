# Roadmap

The build order. Ship the MVP path end-to-end **first**, then layer features. A fresh session should
read this to know what to work on next.

## Phase 0 — Foundations (done by the scaffold)

- [x] Repo structure, CLAUDE.md, docs/, Makefile, tests, CI, `.remember/`.

## Phase 1 — MVP: read the `.musx` container

Goal: given a path to a `.musx` file, open it and hand back its internal streams, with malformed
input failing cleanly. No musical interpretation yet — this is the foundation everything else reads
through. Each item is one branch / one PR.

- [x] Version detection for `.mus` and `.musx` (`detect_version`). Landed ahead of the container
      reader below.
- [x] `open_musx(path)` — open and structurally validate a `.musx` container. Raises
      `NotFinaleFileError` (not a Finale file) or `CorruptContainerError` (the archive violates a
      structural safety limit). Structural validation runs *before* the Finale mimetype value is
      confirmed, so `CorruptContainerError` can fire on an archive that turns out not to be a
      Finale file at all, not only on a confirmed-Finale archive that is malformed or hostile. The
      earlier `InvalidFinaleFile` name was dropped in favour of reusing the existing error type.
- [x] Enumerate the container's entries (name, declared size, compressed size, method) in archive
      order.
- [x] Extract the score stream as bytes, with size caps applied before reading.
- [x] Synthetic container fixtures harvested from corpus *structure* — this replaced "author a
      public-domain fixture", which needed a working Finale install. Structure-only harvesting is
      what makes CI coverage possible without committing a real score.
- [x] Document the container layout in `docs/ARCHITECTURE.md`, with evidence.

**Done.** Tests open each of the 22 synthetic fixtures, enumerate their entries in archive order,
and pull a score stream of the declared length; adversarial tests prove that a truncated or hostile
archive raises `NotFinaleFileError` or `CorruptContainerError` rather than crashing. Every safety
limit is verified by mutation, because no real corpus archive trips one.

## `score.dat` decoding — done

- [x] Decode `score.dat` (extracted by the Phase 1 container reader) into EnigmaXML
      (`finale_file_parser.enigma.score_xml`). Verified against all 401 corpus archives: 401/401
      decode, every result schema `version="18.0"`. See `docs/formats/score-dat.md` and
      `docs/ARCHITECTURE.md`.

## EnigmaXML generic structure — done

- [x] Parse EnigmaXML into a Python document model: seven pools (`header`, `mappings`, `options`,
      `others`, `details`, `entries`, `texts`), each holding recursive `Record`s (tag, attrs, text,
      fields) in document order, navigable via `Pool.of_tag`. Verified against all 401 corpus
      archives. See `docs/ARCHITECTURE.md` and
      `docs/superpowers/specs/2026-07-22-enigma-document-design.md`.

## Keyed lookup — done

- [x] Map the key-attribute set each record tag actually needs (`cmper`, `part`, the `details`
      pool's compound `cmper1`/`cmper2` keys, or `entnum`) and add keyed lookup once it is unique.
      Five keyed `Pool` subclasses (`OptionsPool`, `OthersPool`, `DetailsPool`, `EntriesPool`,
      `TextsPool`) add `get`/`all_with`/`for_entry`, verified unique across all 401 corpus
      archives — 3.1 million records, zero collisions. A duplicate identity raises
      `MalformedEnigmaError` rather than silently keeping one. See `docs/ARCHITECTURE.md` and
      `docs/superpowers/specs/2026-07-23-enigma-keyed-lookup-design.md`.

## Typed entries — done

- [x] `read_entry` converts a generic `entry` `Record` into a typed `Entry`/`Note`/`Duration`: the
      written duration (base note value + dots, decoded from `dura` in EDU), whether the entry is
      a rest (`numNotes == 0`), and its notes (`harmLev`/`harmAlt`, tie flags) — the musical core
      the recursive model already reaches. Pitch stays key-relative (spelling is the next slice);
      tuplet scaling of the written duration is also deferred. Verified against all 401 corpus
      archives: every entry reads without raising
      (`tests/enigma/test_music_corpus_sweep.py`). See `docs/ARCHITECTURE.md` and
      `docs/superpowers/specs/2026-07-23-typed-entries-design.md`.

## Cross-pool link resolution — done

- [x] `locate_entries` resolves every entry to its (staff, measure) and the effective raw key
      signature in force, walking `gfhold → frameSpec → entry next-chain` and `measSpec` (with
      per-measure key inheritance). The first cross-pool link resolution — what a `cmper` on one
      record *refers to* on another pool, rather than only retrieving a record by its own
      identity. `MalformedScoreError` on an orphan entry or a broken link, rather than degrading.
      Verified against all 401 corpus archives, 0 orphans (`tests/enigma/test_location_corpus_sweep.py`).
      The key is exposed **raw** (undecoded) — decoding it is the next slice. See
      `docs/ARCHITECTURE.md` ("Known format facts — score linkage") and
      `docs/superpowers/specs/2026-07-23-entry-location-design.md`.

## Next up — key signature decoding, then pitch spelling

- [ ] **Decode the key signature** — turn the raw `int` `locate_entries` exposes into a
      tonic/mode/accidentals per the recorded decode hints (fifths-style signed accidental count,
      e.g. `-1` = F major, `+2` = D major), minding the traps: enharmonic equivalents are distinct
      key values, a signature alone does not fix major vs. minor, and a transposing instrument's
      written key differs from concert pitch.
- [ ] **Pitch spelling** — combine the decoded key with `harmLev`/`harmAlt` to resolve absolute
      spelled pitches.
- [ ] Clefs, time signatures, tuplet duration scaling (the written `dura`/`Duration` needs a
      tuplet ratio applied to reach the sounded duration), and the remaining detail records
      (beams, stems, articulations, lyrics) — toward a MusicXML exporter (see `## Later`).

## Later

<!-- Things deliberately deferred. Keep them out of Phase 1 so the MVP stays small. -->
- [ ] Notes, pitches, and rhythms as a Python data model.
- [ ] Staves, measures, and score structure.
- [x] `.mus` header provenance stamps (created/modified with date, application, platform).
- [x] Unify `.musx` provenance onto `ProvenanceStamp` (see `docs/DECISIONS.md`). `MusxDetail.platform`
      was dropped in favour of a platform on each stamp, matching `.mus`.
- [ ] `.mus` internal record pools — open research. A `.mus` file has no member table, so there is
      no container abstraction to mirror from `.musx`; the pools must be located empirically.
- [ ] MusicXML exporter over the IR (DECIDED — see DECISIONS.md).
- [ ] Desktop frontend: hex viewer with decoded structure values (DECIDED — framework still open).
- [ ] Desktop frontend: notation rendering.
- [ ] CLI for dumping file structure.
