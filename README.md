# finale-file-parser

A parser for Finale music notation files (.mus/.musx).

Finale was discontinued in 2024 and its format is proprietary and undocumented. This project reads
those files and converts them to MusicXML, so scores that only exist as `.mus` or `.musx` can be
migrated, analysed or archived.

## Installing

From source, which works today regardless of what is on PyPI:

```bash
uv tool install git+https://github.com/jsawruk/finale-file-parser     # the `finale-parser` command
pip install git+https://github.com/jsawruk/finale-file-parser         # or as a library
```

Once a release is on PyPI, the shorter form works too:

```bash
uv tool install finale-file-parser
pip install finale-file-parser
```

Python 3.12 or newer. The only runtime dependency is `defusedxml`.

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

## How well does it read a file?

Of the 639 documents in the maintainer's test corpus, 631 build a score: 401 of 401 `.musx`, 99 of
99 Finale 2011 `.mus`, and 131 of 139 Finale 2001–2005 `.mus`. The eight are the files rather than
the reader — six are blank scores the parser refuses deliberately, one is a mirror, one an
incomplete export.

That corpus is licensed material and is not in this repository, so those sweeps **do not run in
CI** — they are skipped on any checkout without a corpus. CI verifies lint, formatting,
`mypy --strict`, and every test that does not need one.

## Requirements for development

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

`make check` is what CI runs, but a CI checkout has no corpus, so the corpus sweeps skip there. A
green CI run verifies less than a green local run on a machine that has one.

## License

MIT — see [`LICENSE`](LICENSE).

The format knowledge this project rests on came from elsewhere, and two modules were written from
third-party work: the PKWARE DCL decompressor is a port of Mark Adler's `blast.c`, and the
`score.dat` cipher parameters were taken from denigma. [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)
carries those notices; `docs/REFERENCES.md` records every source consulted.

The reference documents vendored in `docs/` are third-party works reproduced for research and
scholarship, and are **not** covered by this project's MIT license. They are documentation only —
no published package contains them.
