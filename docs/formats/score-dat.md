# `score.dat` — decoding EnigmaXML from a `.musx`

How to get from a Finale `.musx` file to the EnigmaXML inside it. Written so the pipeline can be
reimplemented from this page alone, without reading this project's code.

Verified against **401 `.musx` archives** (Finale majors 15-18, Mac and Windows): 401/401 decode,
zero failures.

## Attribution

The cipher parameters below were **not** discovered by this project. They come from
[denigma](https://github.com/chrisroode/denigma) (MIT), whose source credits
[Deguerre](https://github.com/Deguerre) for working them out. This document records the facts and
this project's independent implementation; the discovery is theirs.

## The pipeline

```
.musx  ──unzip──▶  score.dat  ──decrypt──▶  gzip stream  ──inflate──▶  EnigmaXML
```

Four steps. Each is described below with the details that matter.

---

### Step 1 — Extract `score.dat` from the archive

A `.musx` is a zip archive. Its members, as observed across the corpus:

```
mimetype                  always first, always STORED (uncompressed)
META-INF/container.xml
NotationMetadata.xml
score.dat                 ← this one
presets/<n>.preset        0 or more
graphics/<n>.jpg          0 or more
```

`mimetype` contains exactly `application/vnd.makemusic.notation`.

Observed `score.dat` sizes: **min 86,170 · median 96,427 · max 412,805 bytes**.

> **Safety.** Treat the archive as hostile. Validate member names, reject duplicates, and cap both
> the member count and the total declared uncompressed size *before* reading anything. Never extract
> to disk.

---

### Step 2 — Decrypt

`score.dat` is XOR-encrypted with a keystream from a **BSD `rand()` linear congruential generator**
seeded with a fixed constant.

```
INITIAL_STATE = 0x28006D45
MULTIPLIER    = 0x41C64E6D
INCREMENT     = 0x3039
RESET_EVERY   = 0x20000        # 131,072 bytes
```

For each byte at index `i`:

1. If `i % RESET_EVERY == 0`, reset `state = INITIAL_STATE`.
2. Advance: `state = (state * MULTIPLIER + INCREMENT) mod 2**32`.
3. Take the high half: `upper = state >> 16` (a 16-bit value).
4. Derive the keystream byte: `c = (upper + upper // 255) & 0xFF`.
5. Output `byte ^ c`.

Reference implementation:

```python
INITIAL_STATE, MULTIPLIER, INCREMENT, RESET_EVERY = 0x28006D45, 0x41C64E6D, 0x3039, 0x20000

def decrypt(data: bytes) -> bytes:
    out = bytearray(len(data))
    state = INITIAL_STATE
    for i, byte in enumerate(data):
        if i % RESET_EVERY == 0:
            state = INITIAL_STATE
        state = (state * MULTIPLIER + INCREMENT) & 0xFFFFFFFF
        upper = (state >> 16) & 0xFFFF
        out[i] = byte ^ ((upper + upper // 255) & 0xFF)
    return bytes(out)
```

#### Three details that are easy to get wrong

**The reset is real and it hides.** The keystream restarts every 131,072 bytes. Because the median
`score.dat` is ~96 KB, **an implementation that omits the reset decodes most files correctly** and
fails only on those above 128 KB. Test with a file over that size, or the bug ships.

**`upper + upper // 255` is not `upper / 255`.** It is integer division added back to the value,
then truncated to 8 bits. This maps the 16-bit range onto 0-255 slightly differently than a plain
shift or modulo, and getting it wrong produces plausible-looking garbage rather than an obvious
failure.

**The keystream is constant**, so it need not be regenerated per file — or per byte. Compute the
131,072-byte block once, cache it, and tile it. Across this corpus that is the difference between
minutes and ~3 seconds.

```python
KEYSTREAM = _build_block()                       # once
def decrypt(data: bytes) -> bytes:
    ks = (KEYSTREAM * (len(data) // RESET_EVERY + 1))[: len(data)]
    return bytes(a ^ b for a, b in zip(data, ks))
```

---

### Step 3 — Inflate

The decrypted bytes are a **gzip stream**. Every corpus file begins:

```
1f 8b 08 00 00 00 00 00 00 03
│  │  │  │  └──── MTIME = 0 ─┘ │  └── OS
│  │  │  └── FLG = 0           └── XFL
│  │  └── CM = 8 (deflate)
└──┴── gzip magic
```

Checking for `1f 8b` first gives a clean failure when the key is wrong or the stream is not Enigma,
instead of an obscure error from deep inside zlib.

> **Safety — this is the dangerous step.** Observed inflation ratios run **25.6× to 37.3×**, and the
> largest output is **10.78 MB**. Decompress incrementally against an explicit cap rather than
> calling a one-shot `decompress()` on untrusted input, which will allocate gigabytes before
> anything can intervene. A 64 MiB cap leaves ~6× headroom over the largest real file.

---

### Step 4 — The result: EnigmaXML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<finale version="18.0" xmlns="http://www.makemusic.com/2012/finale">
  <mappings/>
  <header/>
  <options/>
  <others/>
  <details/>
  <entries/>
  <texts/>
</finale>
```

Observed sizes: **min 2.48 MB · median 2.65 MB · max 10.78 MB** — a ~28× expansion, so a 100 KB
`.musx` yields several megabytes of XML.

**`version="18.0"` is the XML schema version, not the writing application's version.** It is `18.0`
in all 401 corpus archives, even though the applications that wrote them span majors 15-18. The
application version lives in `NotationMetadata.xml`; do not conflate them.

For the meaning of the pools inside `<finale>`, see the community
[EnigmaXML documentation](https://github.com/Project-Attacca/enigmaxml-documentation) — this project
has not yet parsed them.

## Corpus measurements

| Property | Min | Median | Max |
|---|---|---|---|
| `score.dat` (encrypted) | 86,170 | 96,427 | 412,805 |
| Inflated EnigmaXML | 2,481,759 | 2,651,032 | 10,781,112 |
| Inflation ratio | 25.6× | 28.5× | 37.3× |

401 of 401 archives decoded successfully; every result has a `<finale>` root element.

## How this was established

Recorded so the reasoning can be checked, and so the dead ends are not re-walked.

Independently, before consulting any implementation:

- **The keystream is fixed, not per-file.** 40 archives share 12-14 identical leading ciphertext
  bytes while measuring 7.9985 bits/byte of entropy. Per-file keys would randomise that prefix.
- **The plaintext is compressed.** XOR-ing two ciphertexts together — which cancels a shared
  keystream — leaves entropy at 7.9973 rather than collapsing into structure. That means the
  plaintexts themselves are near-random, i.e. compressed.
- **`keystream[0:3] = 09 5c 5b`**, from the ciphertext `16 d7 53` XOR the gzip magic `1f 8b 08`.
- **Not a short repeating key.** Byte equality at lags 8-512 sits at the 0.39% random baseline.
- **Not a common LCG** within a ~25M-combination search over standard multipliers, increments, and
  output shifts. That search contained the correct multiplier and increment; it capped seeds at
  65,535, and the true seed is `0x28006D45` — about 671 million.

The seed came from denigma's source (see Attribution). Everything above is reproducible from the
corpus alone.
