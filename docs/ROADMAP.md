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

## Next up — decode `score.dat`

`score.dat` is the wall between this project and actual notes. Every remaining item in `Later` —
pitches, rhythms, staves, measures, score structure, and the MusicXML exporter — sits behind it:
nothing there can start until the byte stream is turned into records. Community EnigmaXML
reverse-engineering documentation may be read as reference for what the format is (DECIDED — see
`docs/DECISIONS.md`), but the decoder is written independently, not ported from it.

- [ ] Decode `score.dat` (extracted by the Phase 1 container reader) into records/chunks.

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
