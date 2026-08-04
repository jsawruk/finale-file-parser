# finale-file-parser

A parser for Finale music notation files (.mus/.musx).

Finale was discontinued in 2024 and its format is proprietary and undocumented. This project reads
those files and converts them to MusicXML, so scores that only exist as `.mus` or `.musx` can be
migrated, analysed or archived.

## Converting scores

```bash
finale-parser convert score.mus                 # writes score.musicxml beside it
finale-parser convert score.musx -o out.musicxml
finale-parser convert ./scores -o ./converted   # a whole tree, layout preserved
```

A batch does not stop at the first bad file: what fails is reported and skipped, the rest are
converted, and the exit status is non-zero if anything was skipped. Existing output is never
overwritten unless you pass `--force`.

```bash
finale-parser inspect score.mus     # what the file is, and what was read from it
```

`inspect` prints the detected version and the shape of the score — parts, measures, events,
pitches.

A `.mus` is read by reverse engineering, so a converted score can be missing things the original
had — part names come out positional, for instance. What is and is not carried is recorded in
`UNTRANSLATED` in `src/finale_file_parser/enigma/mus_document.py`.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python environment + package manager)
- Python 3.12+ (uv can install this for you)

## Getting started

```bash
make install     # create the virtual environment and install dependencies
make check       # run lint, format-check, type-check, and tests
```

## Development

This project uses a single command surface — run `make help` to see every target. All code quality
checks run together via `make check`, which is also what Continuous Integration (CI) runs on every
push and pull request.

Contributor and AI-assistant conventions for this repo live in `CLAUDE.md`; design notes and
decisions live in `docs/`.
