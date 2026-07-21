# Roadmap

The build order. Ship the MVP path end-to-end **first**, then layer features. A fresh session should
read this to know what to work on next.

## Phase 0 — Foundations (done by the scaffold)

- [x] Repo structure, CLAUDE.md, docs/, Makefile, tests, CI, `.remember/`.

## Phase 1 — MVP: read the `.musx` container

Goal: given a path to a `.musx` file, open it and hand back its internal streams, with malformed
input failing cleanly. No musical interpretation yet — this is the foundation everything else reads
through. Each item is one branch / one PR.

- [ ] Create a public-domain test fixture: a tiny score we author ourselves, saved as `.musx`.
- [ ] `open_musx(path)` — validate the file is a readable zip container; raise a typed
      `InvalidFinaleFile` on anything else.
- [ ] Enumerate the container's entries (name + size) and expose them as structured data.
- [ ] Extract the primary score stream as bytes, with size caps on untrusted length fields.
- [ ] Document the container layout found so far in `docs/ARCHITECTURE.md`, with evidence.

Done when: a test opens the fixture, lists its entries, pulls the score stream, and a second test
proves a truncated/garbage file raises `InvalidFinaleFile` rather than crashing.

## Later

<!-- Things deliberately deferred. Keep them out of Phase 1 so the MVP stays small. -->
- [ ] Decode the score stream into records/chunks (needs the Phase 1 bytes first).
- [ ] Notes, pitches, and rhythms as a Python data model.
- [ ] Staves, measures, and score structure.
- [ ] Legacy `.mus` reader behind the same public API (see DECISIONS.md — open).
- [ ] MusicXML export (see DECISIONS.md — open).
- [ ] CLI for dumping file structure.
