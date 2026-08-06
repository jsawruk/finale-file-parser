# Diagnostic frontend — design

**Status:** approved, not yet implemented
**Date:** 2026-08-04

A read-only view of what the parser saw in one document, so that a file which does not convert — or
converts wrongly — can be diagnosed without reading Python.

## Why now, and why this shape

Parsing is finished against the corpus available: 631 of 639 documents build, and the 8 that do not
are the files rather than the reader (six blank scores refused on purpose, one mirror, one incomplete
export). Further progress needs *new examples*, and a new example is only useful if someone can see
where it went wrong.

Today that answer lives in a stack trace and a Python session. The CLI reports *that* a document
failed and its message; it cannot show what the parser saw on the way there.

Two decisions taken during design shape everything below.

**No comparison engine.** The tool does not diff against a paired `.musx`, a previous run, or
anything else. It makes what the parser read legible enough that someone who knows the score can spot
the mistake. This removes a subsystem and, more importantly, means it works on *any* file — end users
will not have a paired `.musx`.

**One document, deeply.** Batch triage stays with the CLI, which already reports what converted and
what was skipped. This is the smallest thing that answers "what happened inside this one document".

## The stage ladder

The load-bearing idea. The tool exists for documents that do not work, so the model's primary job is
recording **how far the pipeline got**.

Each stage is `ok`, `failed(reason)`, or `not attempted`. A failure is **data, not an exception** —
that is what lets one report format cover a file that dies while decompressing and a file that
converts cleanly.

For a `.mus`:

| stage | on success | on failure |
| --- | --- | --- |
| detect version | family, year, platform | not a Finale file |
| decode payload | pool count, sizes, byte order | payload will not decode |
| read records | counts by tag | pool malformed |
| build document | translated records | which record type broke it |
| build score | parts, measures, events, pitches | *entry 39 placed by more than one frame* |
| export MusicXML | byte count | export error |

**The ladder differs by container**, so `stages` is a list the family produces rather than a fixed
enum. A `.musx` goes container → `score.dat` → EnigmaXML → document → score. One report format covers
both.

The four depths fall out of the ladder rather than being a separate structure: **score** and
**document** are the upper rungs' output, **records** and **bytes** the lower rungs'. A file that
fails early simply has its upper depths greyed out, with the reason shown at the rung where it
stopped — so the tool is most informative exactly when the file is most broken, which is the opposite
of how the CLI behaves.

## Architecture

```
finale_file_parser/report/
    model.py    path -> Inspection        pure, serialisable, renderer-agnostic
    html.py     Inspection -> str          self-contained HTML
```

```
path ──> inspect_document(path) ──> Inspection ──> render_html() ──> one .html file
              (model.py)            (dataclass)      (html.py)         (cli.py writes)
```

Delivery is a **self-contained HTML report**: one file, embedded data, no server, no ports, and **no
new dependencies** — this project depends on `defusedxml` and nothing else, and should not acquire a
web framework or GUI toolkit for a read-only viewer. It works offline, can be archived beside the
converted output, and a user with a score they cannot legally send *can* send the report.

A local web server and a terminal UI were both considered and are deliberately left open. The
`Inspection` dataclass is the seam: either would consume it unchanged, and only the renderer varies.
That is why the model is renderer-agnostic rather than fused to the HTML.

The cost accepted: everything is embedded, so there is no lazy loading. A document with a 500 KB
payload produces a few MB of HTML, which is acceptable for a diagnostic artefact.

### `Inspection`

```
Inspection
  file      name, size, sha256
  stages    [Stage(name, status, detail, error)]     the ladder
  score     parts -> measures -> (time, clef, key, events, pitches)
  document  record counts by tag; which tags were translated
  records   per tag: each record's key (cmper / cmper2 / inci / part), its
            decoded fields exactly as the reader produced them, and its length
            in bytes
  raw       pool bytes, base64
```

**No per-record byte offset.** This section originally promised one — "its byte offset and length
within its pool" — and the shipped code cannot supply it: no reader records where a record began.
`MusOther`, `MusDetailRecord` and `MusRowRecord` each carry the decoded payload and nothing about its
position, and an EnigmaXML `Record` has no file position at all. The field was therefore `null` for
every record of every family, so it is not in the report shape.

Delivering it is a **possible future enhancement, in the reader layer, not the report**: the `.mus`
pool readers would have to capture each record's start offset within its decompressed pool and carry
it on the record types. That is a change to the parser's public data model and was deliberately out
of scope here — `model.py` reimplements nothing, so the report can only show what a reader already
knows.

### The model reimplements nothing

`model.py` only calls existing public readers — `detect_version`, `read_mus_pools`, `read_mus_rows`,
`read_mus_others`, `read_mus_details`, `read_mus_document`, `build_score`, `to_musicxml` — and records
what each returned or raised.

This is a constraint, not an implementation note. Parsing logic of its own would be a second
implementation that could disagree with the real one, and **a diagnostic tool that lies about the
parser is worse than no tool**.

### Bytes are base64, not hex

Base64 is 4/3 of the payload where hex is 2×; the JS renders hex on demand for the region in view. A
500 KB payload becomes ~670 KB of text rather than 1 MB, with full fidelity instead of truncation.

**The budget, concretely.** One overall limit of **16 MB of embedded JSON**. The largest corpus
payload is ~500 KB, so no real document approaches it; the limit exists to stop a pathological file,
not to shape normal output. When it is exceeded, sections are truncated in a fixed order — `raw`
first, then `records` — each with an explicit marker naming what was dropped and why. Score and
document summaries are never truncated: they are small and are the part a reader needs most.

### No external assets

Inline CSS and vanilla JS. No CDN, no framework, no build step. The project has no JavaScript
toolchain and should not acquire one for this.

### CLI surface

Extends the existing command rather than adding one:

```
finale-parser inspect score.mus --report out.html
```

Terminal `inspect` is unchanged.

## Error handling

Failure is the normal path here, so the model distinguishes two kinds — which is the most useful
thing it can report:

- **Refused** — `CorruptScoreError` / `MalformedScoreError`. The reader deliberately declined, and its
  message is already good.
- **Unexpected** — any other exception. That is a reader **bug**, not a bad file, and the report says
  so with the exception type.

That distinction turns the frontend into a bug-finder: point it at a new example and it says whether
the file is unusual or the code is wrong.

Two hard rules:

- **Report generation never fails.** A depth that cannot render shows its error; the file still
  writes.
- **Everything is bounded** — the 16 MB JSON budget above, and a nesting cap of **8 levels** when
  walking record fields, since a record's fields may contain records. Broken and hostile files are
  the whole purpose, so neither bound may be exceeded by a malformed input rather than a large one.

**Named hazard: document text goes into the page.** A title or lyric containing `</script>` would
break out of the embedded JSON block. Escaping is required, with a test using a hostile string. The
input is untrusted by definition — see `docs/SECURITY.md`.

## Testing

- **Unit** — stub the readers to fail at stage N; assert the ladder records it and marks later stages
  *not attempted*.
- **Corpus sweep** — every corpus document produces an `Inspection` without raising, including all 8
  known failures, which are ready-made fixtures with known reasons.
- **Agreement with the existing sweeps** — the report's own verdict must match what the sweeps pin. If
  the report thinks 631 documents build and the sweeps pin 631, they agree. Pin the *agreement*, not
  the report's numbers separately: two independent sets of numbers for the same thing would drift.
- **HTML** — well-formed output, embedded JSON present, and the `</script>` escape holds.

No browser-based testing. The generator is a pure function, so all of the above are ordinary fast
tests.

## Out of scope

- Comparison against a paired `.musx`, a previous run, or any other reference.
- Folder or batch triage. The CLI already reports what converted and what was skipped.
- Editing, repair, or re-export of any kind. Read-only.
- Notation rendering. This shows what the parser read, not what the music looks like.
- A local server or terminal UI. Both remain open; the `Inspection` seam is what keeps them cheap.

## Consequences

The roadmap's "desktop frontend: hex viewer with decoded structure values" is satisfied in a smaller
form than it implied, and "desktop frontend: notation rendering" remains unaddressed and unscheduled.
