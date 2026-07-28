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

## Next up — pitch spelling

- [x] **Decode the key signature** — `decode_key` turns the raw `int` `locate_entries` exposes into
      a `KeySignature` (fifths, mode, tonic). Encoding reverse-engineered: `(mode << 8) | signed
      fifths byte`, mode 0=major/1=minor; enharmonic keys stay distinct by sign, and mode
      distinguishes parallel major/minor. See `enigma/key.py`.
- [x] **Pitch spelling** — combine `decode_key` (tonic + fifths → the key's accidental pattern),
      `read_entry`'s `harm_lev`/`harm_alt` (diatonic displacement from the tonic + alteration
      relative to the key), and a staff's transposition into an absolute spelled pitch (letter +
      octave + accidental), for both written and concert (sounding) pitch. `SpelledNote` gives both
      in one call; see `enigma/pitch.py` and `docs/ARCHITECTURE.md` ("Known format facts — pitch
      spelling and transposition").
- [x] **Tuplet duration scaling** — `enigma/tuplet.py`. Container-agnostic over an `EntryChain`;
      grace notes sound for zero time. Validated by measure balance: 1,420 of 1,423 layer-measures
      sum to their time signature, against 1,136 using written durations.
- [x] **Time signatures** — `enigma/timesig.py`. Enigma stores beats x divbeat, not a numerator over a
      denominator, so 6/8 is two dotted-quarter divisions. `useDisplayTimesig` gates the display
      signature.
- [x] **Clefs** — `enigma/clef.py`. An 18-entry table referenced by index from `staffSpec.defaultClef`
      and `gfhold.clefID`.
- [x] **Layers** — `EntryLocation.layer`. Each layer fills its measure independently, so duration sums
      must group by (staff, measure, layer).
- [ ] The remaining detail records (beams, stems, articulations, lyrics).

## MusicXML exporter — slice 1 done

- [x] Format-neutral IR (`ir.py`), `.musx -> IR` (`enigma/to_ir.py`), `IR -> MusicXML`
      (`export/musicxml.py`). Notes, rests, chords, ties, tuplets, grace notes, keys, time signatures,
      clefs, layers as voices. Output validates against the **official W3C MusicXML 4.0 schema** —
      opt-in via `MUSICXML_XSD`, see `tests/export/test_musicxml_corpus_sweep.py`.
- [x] **Part names, title and composer** — `enigma/text.py`. `staffSpec.fullName` resolves through
      `textBlock` → `textID` → `blockText`; `fileInfo` supplies title/composer/copyright.
- [x] **`.mus` input** — `read_mus_document(path)` yields an `EnigmaDocument`, so
      `to_musicxml(build_score(read_mus_document(path)))` exports a legacy `.mus`. Validated IR
      against IR on 73 paired documents: parts, measures, events, keys, time signatures and written
      rhythm all match exactly. Sounded durations and tuplet ratios match too. The
      remaining gaps are all instrument-derived — transposing staves, 22 clefs — plus part names.
      See `enigma.UNTRANSLATED`.
- [x] **Lyrics** — `enigma/lyrics.py`, both containers, schema-validated. 12,912 syllables
      across 85 corpus documents.
- [x] **Articulations** — `enigma/articulations.py`, both containers. 22,821 marks across 273
      documents, from the five music-font characters with cross-font evidence; fingerings and the
      other 24 characters are deliberately not guessed at.
- [x] **Beams** — `enigma/beams.py`, both containers. 84,620 beams across 366 documents, with
      secondary beams and hooks; Enigma stores only a "starts a group" bit, so the rest is derived.
- [x] **Repeats** — `enigma/repeats.py`, both containers. Forward and backward repeat barlines,
      total passes, and ending brackets. 109 forward, 121 backward and 142 brackets across 109
      documents; identical from `.mus` and `.musx` on all 19 same-content pairs that use them.
      Jumps (D.C., D.S., Fine, To Coda) are a separate slice and are not read.
- [x] **Part groups** — `enigma/groups.py`, both containers. Braces and brackets, group barlines
      and names, nested and numbered in the part list. 201 groups across 155 documents; extent,
      symbol and barline identical from `.mus` and `.musx` on all 15 paired documents that have
      them, names being the one known `.mus` gap.
- [x] **Part order** — parts follow `instUsed`, the score's own staff layout, rather than staff
      number. 10 documents were laying parts out in the wrong order; fixing it also recovers the 8
      staff groups that were dropped as non-contiguous. See `docs/DECISIONS.md`.
- [x] **Staff 32767** — resolved: a reserved staff no score lays out, no longer exported as a part.
      See `docs/DECISIONS.md`.
- [ ] **Empty measures** — a part currently skips a measure where its staff is silent, rather than
      writing a full-measure rest. 1,375 measures across 162 documents reach no part at all. This is
      the next correctness item; see `docs/DECISIONS.md`.
- [ ] Fingerings, jumps, barline styles.

## Later

<!-- Things deliberately deferred. Keep them out of Phase 1 so the MVP stays small. -->
- [ ] Notes, pitches, and rhythms as a Python data model.
- [ ] Staves, measures, and score structure.
- [x] `.mus` header provenance stamps (created/modified with date, application, platform).
- [x] Unify `.musx` provenance onto `ProvenanceStamp` (see `docs/DECISIONS.md`). `MusxDetail.platform`
      was dropped in favour of a platform on each stamp, matching `.mus`.
- [ ] `.mus` internal record pools — part done. The payload decodes (both eras), the entry pool
      reads, and the **`others` pool now reads generically**: its records are self-identifying
      (`tag`, `cmper`, `part`, `length`), so the whole pool walks from byte zero without an oracle
      — see `enigma/mus_others.py`. The **`details` pool reads the same way** (one extra key
      field; `enigma/mus_details.py`), and `gfhold` is payload-confirmed, which is the link from a
      (staff, measure) to its entry frames. Remaining: the per-tag payload layouts, and the seven
      corpus documents whose walk halts inside one unrecognised record type.
- [ ] MusicXML exporter over the IR (DECIDED — see DECISIONS.md).
- [ ] Desktop frontend: hex viewer with decoded structure values (DECIDED — framework still open).
- [ ] Desktop frontend: notation rendering.
- [ ] CLI for dumping file structure.
