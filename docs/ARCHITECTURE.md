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

## Data flow

<!-- Describe the path of the core operation, input to output, naming the key types. -->

```
.mus  ────────────────▶ parser ──▶ IR ──▶ MusicXML
.musx ──▶ EnigmaXML ──▶ parser ──▶ IR ──▶ MusicXML
```

Both inputs converge on the same IR, so format-specific handling stays inside the readers and never
reaches the exporters. Key types are named here as they are defined.
