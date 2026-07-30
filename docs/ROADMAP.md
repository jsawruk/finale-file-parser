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
- [x] The remaining detail records — beams, articulations and lyrics read in both containers.
      Stems are not read: the IR does not model them, and no container's reading is blocked on it.

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
- [x] **Beams** — `enigma/beams.py`, both containers. 84,593 beams across 366 documents, with
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
- [x] **Empty measures** — every part now covers every measure, with a full-measure rest where it is
      silent. 6,362 rests; 420 of 731 parts had a gap. See `docs/DECISIONS.md`.
- [x] **Text repeats (jumps)** — `enigma/jumps.py`, `.musx` only. The words of "Fine", "D.C. al
      Coda" and their kin, printed at their measure. 6 markings across 3 documents; the palette
      every document carries is deliberately not read. Playback semantics, segno/coda signs and the
      `.mus` side are all out of reach on this corpus — see `docs/ARCHITECTURE.md`.
- [x] **Barline styles** — `enigma/barlines.py`, both containers. Double and final bars: 216 and
      110 measures across 89 documents, identical from `.mus` and `.musx` on all 6 paired documents
      that use them. A `.mus` declines to report a final bar; see `docs/ARCHITECTURE.md`.
- [x] **End-to-end audit** — `tests/export/test_export_audit_corpus_sweep.py`. Invariants asserted
      on the exported document rather than on any one feature, over the whole corpus and through
      both readers: the part list agrees with the parts, groups nest, measures line up, beams close,
      barlines are well formed, and nothing the IR holds is dropped on the way out. Schema
      validation went from 25 documents to all 398. **No defects found.**
- [x] **Fingerings** — `enigma/fingerings.py`, both containers. 834 across 18 documents; the
      numeral character identifies one, which is what unblocked the `.mus`. See
      `docs/ARCHITECTURE.md`.

## Later

### Recommended order for the remaining work

<!-- Written 2026-07-30, from a measurement of the corpus rather than from memory.
     Re-derive before trusting: this file has been stale before. -->

The corpus reads well — **625 of 639 documents build** (`.musx` 401/401, DCL `.mus` 131/139,
2011 `.mus` 93/99), and 6 of the 14 that do not are blank scores refused on purpose. The gaps that
remain are therefore mostly *not* about reading more bytes.

1. **A CLI, before any more format work.** This project is for people who need to migrate, analyse
   or archive scores, and none of them can reach the converter without writing Python: there is no
   `[project.scripts]` entry and no cli module. That is the largest gap between what works and what
   is usable, and it carries no research risk. Conversion is the headline command
   (`in.mus -> out.musicxml`); the structure dump already listed below is the second one.

2. **Staff and group names.** The most visible defect in every `.mus` export — parts come out
   `Staff 1` rather than `Flute`. Narrowed to one unknown, the per-document base, and it unblocks
   group names too. **Time-box it**: the broad search has already been run and failed. Start with
   the one untested idea — whether the base is `lowest id - lowest name block` within a document,
   which falls straight out of the anchors pinned in
   `tests/enigma/test_mus_staff_name_link_corpus_sweep.py`.

3. **Re-derive the `UNTRANSLATED` claims that cite corpus counts.** Cheap and overdue. Several were
   measured when far fewer documents were readable: the final-barline entry says a nibble "does not
   occur once in 4,427 measures across 99 corpus `.mus` documents", and 224 `.mus` documents are
   readable now; the fingering-font entry cites "363 of 373 paired records", and pairing changed
   twice since. Three claims of this exact shape turned out to be harness artefacts in one week
   (see `docs/DECISIONS.md`, 2026-07-29 and 2026-07-30). Some may simply close.

4. **The two documents with no recognisable entry pool.** The only genuinely *unread containers*
   left, and a bounded question — possibly a small container variant.

5. **Verify, then close, the rest.** The 4 dangling `frameSpec` chains, the one entry two frames
   claim, and the one `gfhold` in a measure without a key are one document each, and the dangling
   ones look like data the file simply does not contain. Confirm that once and pin them as not
   fixable, the way the blank scores are — leaving them in a gap list makes them read as open work.

**Deliberately not next.** Text repeats and DCL staff layout order are blocked on the corpus rather
than on effort: no `.mus`/`.musx` pair of the same music carries a text repeat, and the DCL cohort
has no paired `.musx` at all. Rather than searching again, write down what a contributed file would
have to contain to unblock each. The desktop frontend is larger than everything above combined, and
the CLI serves the practical need first.


<!-- Things deliberately deferred. Keep them out of Phase 1 so the MVP stays small. -->
- [x] Notes, pitches, and rhythms as a Python data model — `enigma/music.py` and `ir.py`.
- [x] Staves, measures, and score structure — `ir.py`, built by `enigma/to_ir.py`.
- [x] `.mus` header provenance stamps (created/modified with date, application, platform).
- [x] Unify `.musx` provenance onto `ProvenanceStamp` (see `docs/DECISIONS.md`). `MusxDetail.platform`
      was dropped in favour of a platform on each stamp, matching `.mus`.
- [ ] **2011-era `.mus` internal record pools** — mostly done. The payload decodes, the entry pool
      reads, and both the `others` and `details` pools walk generically from byte zero: their
      records are self-identifying (`tag`, `cmper`, `part`, `length`), so no oracle is needed. See
      `enigma/mus_others.py` and `enigma/mus_details.py`.
      **93 of the 99 build a `Score`.** Of the 6 that do not, 4 name an entry the pool does not hold
      — a dangling reference rather than a decode gap. Remaining: the per-tag payload layouts still
      listed in `mus_document.UNTRANSLATED`.
- [x] **2001–2005 (`DCL`-era) `.mus`** — **done for reading**, and this is 139 of the 238 `.mus`
      corpus. Four labelled pools per file, tiling exactly, 139/139, byte order (102 little-endian,
      37 big-endian) taken from the file. The entry pool reads — 71,801 entries over all 139
      documents. The `others`/`details` rows read as fixed 16-byte rows carrying ETF's
      two-character tags; `MS`, `IS`, `FR` and `GF` are payload-confirmed, including the frame link
      (a `GF` record's frame array starts at +4 in a 2001 file and +6 in a 2005 one, told apart by
      the staff spec's incidence count) and all four layer slots.
      **131 of the 139 build a `Score`** — 410 parts, 14,107 measures, 68,530 pitches — and export.

      **The reader has no unexplained readings left.** Two guesses became rules: an entry the frames
      never reach is dead pool space and is discarded (88% of them provably duplicate live music),
      and a frame's entry pair sits in its last incidence, the leading one carrying a `startTime`.

      Of the 8 that do not build, **6 are correctly refused** — blank scores, carrying staves and
      measures but no music the frames reach. The other two are one entry two frames both claim, and
      one `gfhold` placing entries in a measure that defines no key.

      This cohort has **no paired `.musx`**, so the evidence is the ETF spec, internal
      cross-references, and a control against the 2011 cohort. See
      `docs/formats/mus-dcl-container.md`.
- [ ] **Staff layout order in a DCL `.mus`.** Solved for 2011 (others tag 159, one 24-byte slot per
      staff). The DCL era carries an ETF `^Iu` row that is very likely the same record, but with no
      paired `.musx` anywhere in the cohort there is nothing to check a slot layout against, so it
      keeps the numeric fallback.
- [x] **Durations above a whole note.** A breve (8192 EDU) is a note value now, and the range check
      bounds the *base* rather than the total — which is what had been rejecting a **dotted whole**
      (6144), ordinary notation. `NoteValue`, the range check and the MusicXML `<type>` map moved
      together. A longa is deliberately still refused: no corpus document carries one.
- [x] MusicXML exporter over the IR — shipped and W3C schema-validated across all 398 `.musx`
      documents and 224 `.mus`. See `enigma/to_ir.py` and `export/musicxml.py`.
- [ ] Desktop frontend: hex viewer with decoded structure values (DECIDED — framework still open).
- [ ] Desktop frontend: notation rendering.
- [ ] CLI for dumping file structure.
- [ ] **`.musx` `tupletDef` without `symbolicNum`.** Three corpus `.musx` documents fail to build on
      it — the only remaining `.musx` failures, and the largest single unread thing on that side.
- [ ] **Staff and group names from a `.mus`.** The names are in the file and the id that selects one
      is known; what is missing is the per-document base that turns that id into a text block. One
      anchor per document would resolve every name in it. See `docs/formats/mus-staff-names.md`.
