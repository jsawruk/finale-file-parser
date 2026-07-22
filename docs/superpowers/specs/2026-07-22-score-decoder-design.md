# `score.dat` decoder — design

**Status:** approved, not yet implemented
**Date:** 2026-07-22

Turn a `.musx`'s `score.dat` into EnigmaXML. This is the wall between the project and actual musical
content: pitches, rhythms, staves, measures, and the MusicXML exporter all sit behind it.

## The transform

**The pipeline is documented in full at `docs/formats/score-dat.md`** — written so it can be
reimplemented from that page alone, with the corpus measurements and the three details that are
easy to get wrong. This spec covers only the API and safety decisions.

`score.dat` is **encrypted, then the plaintext is gzip**. Decrypt, then inflate.

```
state = 0x28006D45                       # reset at every 0x20000-byte boundary
state = (state * 0x41C64E6D + 0x3039) mod 2**32     # BSD rand() LCG
upper = state >> 16                      # uint16
byte ^= (upper + upper // 255) & 0xFF
```

The plaintext is a gzip stream whose inflation is EnigmaXML with a `<finale>` root.

**The keystream is fixed and resets every 0x20000 (131,072) bytes**, so it is a constant 128 KiB
block: compute once, cache, tile. That is not an optimisation detail — stepping the LCG per byte
across the corpus takes minutes; tiling takes seconds.

### Attribution

The cipher parameters were **not** derived by this project. They come from
[denigma](https://github.com/chrisroode/denigma) (MIT), whose source credits
[Deguerre](https://github.com/Deguerre) for the discovery. This project's implementation is written
independently; the *facts* — which cipher, which seed — are theirs. Both are credited in
`docs/REFERENCES.md` and in a comment in the decoder module.

What this project did establish independently, before reading any source: that the keystream is
fixed rather than per-file (12-14 identical ciphertext bytes across 40 archives at entropy 7.9985);
that the plaintext is gzip (from denigma's prose README, which documents writing a temporary
`score.gz`); that `keystream[0:3] = 09 5c 5b`; and that it is neither a short repeating key (byte
equality at lags 8-512 sits at the 0.39% random baseline) nor a common LCG within a ~25M-combination
search. That search included the correct multiplier and increment — it capped seeds at 65535, and
the true seed is 0x28006D45.

## Findings from the corpus

All 401 archives decrypt and inflate, with zero failures.

| Property | Observed |
|---|---|
| Archives decoded | 401 / 401 |
| `score.dat` size | min 86,170 · median 96,427 · max 412,805 bytes |
| Inflated size | min 2,481,759 · median 2,651,032 · **max 10,781,112** bytes |
| Inflation ratio | min 25.6× · median 28.5× · **max 37.3×** |
| XML root | `<finale version="18.0">` in all 401 |

The uniform `18.0` is the **XML schema** version, not the writing application's — those span majors
15-18. Do not conflate them.

## Public interface

```python
def score_xml(path: str | os.PathLike[str]) -> bytes: ...
```

Returns raw EnigmaXML bytes. Parsing that XML into a model is a **separate slice** — the format has
`mappings`, `header`, `options`, `others`, `details`, `entries`, and `texts` pools, which is too
large a surface to design alongside the decoder.

Returning `bytes` rather than the gzip stream is deliberate: inflation is a decompression-bomb
vector, and this project has consistently refused to push that hazard onto callers.

## Module layout

New package `src/finale_file_parser/enigma/`:

| Module | Responsibility | I/O |
|---|---|---|
| `crypt.py` | The keystream and `decrypt(bytes) -> bytes` | none |
| `score.py` | `score_xml(path)`: open container, decrypt, inflate with caps | via `container` |

`enigma/score.py` consumes `container.open_musx().score_stream()`. It does **not** open archives
itself — `container/` owns archive access, and that separation is already a recorded decision.

## Safety

Inflation is the new hazard. Everything else is already bounded by the container reader.

| Check | Limit | Rationale |
|---|---|---|
| Inflated output | 64 MiB | Corpus max is 10.78 MB. A 6× headroom bounds a bomb without rejecting real files. |
| Inflation performed incrementally | — | Decompress in chunks against the cap rather than calling `gzip.decompress` on untrusted input, which will happily allocate gigabytes before anyone can object. |
| Plaintext must start with the gzip magic | `1f 8b` | A wrong key or a non-Enigma stream fails here rather than deep inside zlib. |

`score.dat` is already capped at read time by `MAX_SCORE_BYTES` (8 MiB) in the container reader, so
the *input* is bounded before decryption begins.

## Errors

- **`CorruptScoreError`** (new, subclasses `FinaleFileError`) — the stream decrypts to something
  that is not gzip, fails to inflate, or exceeds the inflation cap.
- `FileNotFoundError`, `NotFinaleFileError`, `CorruptContainerError` propagate unchanged from
  `open_musx`.

Note this is stricter than the version modules, which degrade to "unknown" so unfamiliar variants
stay inspectable. That leniency is right for *optional metadata* and wrong here: a caller asking for
the score has asked for a specific thing, and half a score is not useful.

## Testing

- Unit tests for `decrypt` over synthetic input, including that the keystream **resets** at the
  0x20000 boundary — a decoder that omits the reset works on every corpus file under 128 KiB and
  fails only on the largest, which is exactly the bug that hides.
- A committed fixture: a small synthetic `.musx` whose `score.dat` is our own XML, encrypted with
  this cipher. **No corpus payload** — the same rule as every other fixture here.
- Adversarial: a stream that decrypts to non-gzip; a gzip bomb exceeding the cap; truncated gzip;
  an archive with no `score.dat`.
- Corpus sweep (local only, skipped in CI): all 401 archives decode; every result has a `<finale>`
  root; inflated sizes stay within the observed range.
- Every safety rule verified by mutation, per project practice.

## Out of scope

Parsing EnigmaXML into a model. The `.mus` record pools. MusicXML export.

## Consequences

- `docs/formats/score-dat.md` is the standalone format reference; `docs/ARCHITECTURE.md` links to it.
- `docs/REFERENCES.md` gains denigma and Deguerre with the MIT license recorded.
- `docs/DECISIONS.md` records that cipher parameters were taken as facts from MIT-licensed source
  after the earlier "documentation as reference" decision proved insufficient — the transform was
  documented nowhere in prose.
- The roadmap's `Next up` item is satisfied; parsing EnigmaXML becomes the new next item.
