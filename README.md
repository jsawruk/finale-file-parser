# finale-file-parser

A parser for Finale music notation files (.mus/.musx).

Finale was discontinued in 2024 and its format is proprietary and undocumented. This project reads
those files and converts them to MusicXML, so scores that only exist as `.mus` or `.musx` can be
migrated, analysed or archived.

## Installing

```bash
uv tool install finale-file-parser     # just the `finale-parser` command
pip install finale-file-parser         # or as a library, into your own environment
```

Python 3.12 or newer. Runtime dependencies are `defusedxml`, which makes parsing untrusted XML safe,
and Verovio, which engraves the inspection report's notation view.

To run a change that has landed on `main` but is not yet released:

```bash
uv tool install git+https://github.com/jsawruk/finale-file-parser
```

## Using the library

```python
from finale_file_parser import read_document, read_score

score = read_score("archive/score.musx")
document = read_document("archive/legacy-score.mus")
```

`read_score` is the ordinary high-level entry point and returns the format-neutral `Score` model.
`read_document` stops one layer earlier at `EnigmaDocument` for callers that need Finale records.
Both detect `.mus` versus `.musx` from the file contents rather than the filename extension, and
preserve the existing parser exceptions.

## Converting scores

```bash
finale-parser convert score.mus                 # writes score.musicxml beside it
finale-parser convert score.musx -o out.musicxml
finale-parser convert ./scores -o ./converted   # a whole tree, layout preserved
```

A batch does not stop at the first bad file: what fails is reported and skipped, the rest are
converted, and the exit status is non-zero if anything was skipped. Existing output is never
overwritten unless you pass `--force`.

### Printing a score

```bash
pip install finale-file-parser[pdf]             # once; adds svglib and reportlab
finale-parser convert score.mus --format pdf    # writes score.pdf beside it
finale-parser convert ./scores -o ./printed --format pdf
```

`--format pdf` engraves the score and writes it as a multi-page PDF on US Letter, using the same
notation the inspection report shows. PDF support is an optional extra so that installing the
library does not pull in a PDF stack you may never use; without it, `--format pdf` exits with a
message naming the extra rather than a traceback.

```bash
finale-parser inspect score.mus     # what the file is, and what was read from it
```

`inspect` prints the detected version and the shape of the score — parts, measures, events,
pitches.

```bash
finale-parser inspect score.mus --report score-report.html
```

Writes one self-contained HTML file showing what the parser saw: how far the pipeline got, the
engraved score and music tree it built, the records it read, and the raw bytes. A `.musx` report also
shows the file's complete EnigmaXML as a foldable tree; a binary `.mus` has no source XML, so that tab
is absent. The report is most informative when a document does *not* convert — it names the stage
that stopped and why, which is what to send when reporting a file that will not parse.

A `.mus` is read by reverse engineering, so a converted score can be missing things the original
had — part names come out positional, for instance. Later-era `.mus` title, composer and copyright
metadata is preserved; the older DCL cohort carries no tagged bibliographic records. What is and is
not carried is recorded in `UNTRANSLATED` in `src/finale_file_parser/enigma/mus_document.py`.

## How well does it read a file?

Of the 639 documents in the maintainer's test corpus, 632 build a score: 401 of 401 `.musx`, 99 of
99 Finale 2011 `.mus`, and 132 of 139 Finale 2001–2005 `.mus`. The seven are the files rather than
the reader — six are blank scores the parser refuses deliberately, one an incomplete export.

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
