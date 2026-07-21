# Architecture

How the system is shaped. Keep this current as the design settles — a fresh session reads this before
working on structure.

## Overview

The system consists of a parser library that reads Finale `.mus` and `.musx` files and exports
MusicXML, plus a frontend desktop application providing two functions:

- A hex viewer that decodes binary entries and shows the structure values
- A rendering of the corresponding music notation

Because parsing supports multiple inputs, all data flows into a single intermediate representation
(IR). The library stays independently usable and takes no GUI dependency.

## Modules

<!-- List the top-level modules under src/ and the single responsibility of each. -->

- `src/` — the main source directory.
- `src/finale_file_parser/version/` — identifies which Finale version wrote a file, before any
  record parsing. `models.py` (types), `family.py` (magic → family), `mus.py` (banner parsing),
  `musx.py` (archive metadata), `detect.py` (public entry).

### Known format facts — version

- `.mus` begins with `ENIGMA BINARY FILE` at offset 0, identical across Finale 2001–2012. The
  writing version is an ASCII banner at offset `0x20`, e.g.
  `Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.`
  Evidence: 238 corpus files; see `docs/superpowers/specs/2026-07-21-version-detection-design.md`.
- That banner field is fixed-size and is **not** zero-filled on rewrite, so a shorter banner can
  leave a tail of the previous, longer one behind (observed: `logy` from the Finale 2004 Coda
  banner surviving into a 2005 file). Always cut at the first NUL.
- `.musx` is a zip with `mimetype` = `application/vnd.makemusic.notation`. Version data lives in
  `NotationMetadata.xml` as plaintext, with separate `created` and `modified` blocks. **`modified`
  is the layout authority** — 264 of 401 corpus files were created by major=16 but last written by
  major=18.
- `score.dat` is obfuscated high-entropy data. Version detection never reads it.
- The `.musx` `major` version number (15/16/17/18) has no established mapping to Finale's
  marketing years (2009/2011/2012/2014...). Nothing in the corpus bridges the two schemes, so
  version labels report the raw major/maint/build instead of a year. Open question.
- `scripts/build_version_fixtures.py` strips `NotationMetadata.xml` down to only the root
  `version` attribute and the `created`/`modified` subtrees, building the output tree fresh so any
  field not explicitly listed is absent by construction. Every attribute on every element within
  those subtrees is also stripped (an allowlist of zero attributes — none are read by version
  detection, so none are kept), and every `<modifiedBy>` is blanked rather than dropped. This is
  deliberate: the corpus metadata carries `title`, `subtitle`, `composer`, `arranger`, `lyricist`,
  `copyright` (including a MakeMusic notice restricting commercial redistribution), and
  `modifiedBy` — which holds real people's initials in 28 corpus files — plus attributes such as
  `<created author="...">` that could carry the same kind of identifying data. Do not loosen this
  filter to pass through more fields or attributes.

## Data flow

<!-- Describe the path of the core operation, input to output, naming the key types. -->

```
.mus  ────────────────▶ parser ──▶ IR ──▶ MusicXML
.musx ──▶ EnigmaXML ──▶ parser ──▶ IR ──▶ MusicXML
```

Both inputs converge on the same IR, so format-specific handling stays inside the readers and never
reaches the exporters. Key types are named here as they are defined.
