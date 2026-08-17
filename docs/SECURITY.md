# Security & guardrails

The invariants Claude Code and human contributors must never trade away for convenience. The short
version lives in `CLAUDE.md`; this is the detail.

## Secrets

- Real secrets live only in a git-ignored `.env`. `.env.example` lists variable names with
  placeholder values. Never commit a real credential, key, or token.
- If a secret is ever committed by accident, treat it as compromised: rotate it, then remove it from
  history. Do not just delete it in a later commit.

## Dependencies

- Prefer well-maintained, widely-used libraries and keep them pinned in `uv.lock`. No advisory
  dependency audit is currently wired into `make check` or CI, so a green gate does **not** cover
  dependency advisories. Escalate any advisory found during release review to the owner.

## The `.musx` container reader's threat model

`finale_file_parser.container.musx.open_musx` treats every `.musx` file as untrusted zip input —
a file a caller opens with no prior guarantee it was produced by Finale, or by anything benign.
Nothing is ever extracted to disk; only bytes are read into memory, and only up to caller-stated
bounds. Structural limits are checked once at open time against the central directory, before any
member's bytes are read.

Five structural limits enforce that:

| Check | Limit | Guards against |
|---|---|---|
| Member-name safety (`container/names.py`, `is_safe_name`) | reject only names that are absolute, contain a `..` segment, a backslash, a colon, or a control/format character | Zip-slip and path-traversal via a hostile member name reaching a caller or a future hex viewer. |
| Duplicate member names | rejected | Zip permits two entries with the same name; "which one did you read?" is exactly the ambiguity a hostile archive wants a reader to get wrong. |
| Member count | `MAX_MEMBERS` = 64 | An archive with an enormous number of (possibly tiny) members — corpus maximum observed is 10. |
| Total declared uncompressed size | `MAX_TOTAL_UNCOMPRESSED` = 16 MiB | A zip bomb built from many members each just under a per-member cap — corpus maximum observed is 419,972 bytes. |
| Per-call read bound | caller-supplied `max_bytes` to `MusxContainer.read()` (`score_stream()` uses `MAX_SCORE_BYTES` = 8 MiB) | An individual member declaring far more bytes than the caller is prepared to receive, checked against the *declared* size before any decompression is attempted. |

Every one of these five is verified by mutation — delete the check, confirm the corresponding test
fails, restore — rather than assumed correct because a test exists. See
`docs/superpowers/specs/2026-07-21-musx-container-design.md` for the full rationale behind each
cap's value.

**Why no real corpus archive can exercise any of this.** All 401 local corpus archives have no
duplicate or unsafe member names, stay well under every cap, and decompress cleanly. That means
every one of the five defences above is, in this codebase, covered exclusively by synthetic
hostile input constructed in-test (zip-slip names, duplicate entries, oversized member counts,
declared sizes and byte counts crafted to sit over a cap) — never by anything derived from
`corpus/`. A defence with a test that passes only because the check happens to be present, but
would pass just as well with the check deleted, is not considered covered; that is why mutation
verification is mandatory here rather than optional.

**The scoped `except Exception` around decompression.** Both places this module calls
`archive.read()` on a member (the mimetype-value check in `open_musx`, and
`MusxContainer.read()`) wrap that single stdlib call in `except Exception`, not an enumerated
tuple of concrete exception types. This is deliberate, not sloppy: decompressing a hostile member
can fail via whatever exception its codec happens to raise — `BadZipFile` (local header disagrees
with the central directory), `RuntimeError` (encryption bit set), `OSError` (a codec rejects the
stream outright, e.g. bzip2), `NotImplementedError` (unsupported or deflate64 method), or
`zlib.error` (a DEFLATE-declared member with corrupt bytes, which subclasses only `Exception` —
not any of the others). Three successive review passes each named a concrete tuple of types and
each missed one; the fourth pass replaced the tuple with a category catch. Each guard covers
exactly one stdlib call with no project logic inside it, so there is no bug of ours a broad except
could mask, and `KeyboardInterrupt`/`SystemExit` still propagate since they derive from
`BaseException`, not `Exception`. **Do not narrow this back to a named list of exception types** —
that is precisely the regression that has recurred on this module four times.

## Data & licensing

- Large binaries, datasets, and model weights stay out of git.
- Licensing / access tier is mandatory metadata, never defaulted to permissive. When in doubt, mark
  it OPEN in `docs/DECISIONS.md` and ask the owner.

## The meta-rule

Flag legally, ethically, or security-sensitive calls for the owner instead of deciding them.
