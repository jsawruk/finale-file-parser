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
> the member count and the total declared uncompressed size _before_ reading anything. Never extract
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

#### Pseudocode

```
state = 0x28006D45                          # reset every 0x20000 bytes
state = state * 0x41C64E6D + 0x3039         # BSD rand() LCG, mod 2^32
upper = state >> 16
byte ^= (upper + upper // 255) & 0xFF
```

Step by step, for each byte at index `i`:

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

**The reset is real and it hides.** The keystream restarts every 131,072 bytes. Only **68 of the
401 corpus archives** have a `score.dat` larger than that, so an implementation that omits the reset
**silently decodes 333 of 401 files (83%) correctly** and fails only on the largest.

Measured directly, on the largest file (`score.dat` = 412,805 bytes, 3.1 keystream blocks):

| Decoder           | Largest file                 | Smallest file (86,170 bytes) |
| ----------------- | ---------------------------- | ---------------------------- |
| With the reset    | OK — 10,781,112 bytes of XML | OK — 2,481,759 bytes         |
| Without the reset | **fails to inflate**         | OK — identical output        |

The smallest file never reaches the boundary, so both decoders agree on it. **Test with a
`score.dat` over 128 KiB, or the bug ships.**

**`upper + upper // 255` is not `upper / 255`.** It is integer division added back to the value,
then truncated to 8 bits. This maps the 16-bit range onto 0-255 slightly differently than a plain
shift or modulo, and getting it wrong produces plausible-looking garbage rather than an obvious
failure.

**The keystream is constant**, so it need not be regenerated per file — or per byte. Because the
generator is reseeded to the same `INITIAL_STATE` at every `0x20000` boundary and nothing else feeds
it, the keystream is one fixed 131,072-byte block repeated end to end. Compute it once, cache it,
and tile it.

Verified on the largest corpus file: the tiled implementation produces **byte-identical output** to
the per-byte LCG version, in 15.1 ms versus 68.7 ms — 4.6× faster on one file, and the gap widens
across a corpus because the block is computed once rather than per file.

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

| Property                | Min       | Median    | Max        |
| ----------------------- | --------- | --------- | ---------- |
| `score.dat` (encrypted) | 86,170    | 96,427    | 412,805    |
| Inflated EnigmaXML      | 2,481,759 | 2,651,032 | 10,781,112 |
| Inflation ratio         | 25.6×     | 28.5×     | 37.3×      |

401 of 401 archives decoded successfully; every result has a `<finale>` root element.

## How this was established

Recorded so the reasoning can be checked, and so the dead ends are not re-walked.

### What was derived from the corpus alone

Before consulting any implementation:

- **The keystream is fixed, not per-file.** 40 archives share 12-14 identical leading ciphertext
  bytes while measuring 7.9985 bits/byte of entropy. Per-file keys or a random IV would randomise
  that prefix; a constant prefix means a constant keystream over a constant plaintext header.
- **The plaintext is compressed.** XOR-ing two ciphertexts together cancels a shared keystream,
  leaving `plaintext_A XOR plaintext_B`. That result stayed at 7.9973 bits/byte instead of
  collapsing into structure — so the plaintexts are themselves near-random, i.e. compressed. The
  first 14 bytes did XOR to zero, which is the shared header showing through.
- **`keystream[0:3] = 09 5c 5b`**, from ciphertext `16 d7 53` XOR the gzip magic `1f 8b 08`.
- **Not a short repeating XOR key.** Byte equality at lags 8, 16, 24, 32, 48, 64, 128, 256 and 512
  all sat at 0.30-0.47%, against a 0.39% random baseline. A repeating key of any of those lengths
  would spike sharply.
- **The output is gzip**, from denigma's _prose_ README, which documents writing a temporary
  `score.gz` before decompressing it.

### Dead ends

**A classic-PRNG search that should have worked, and did not.** Assuming a standard gzip header with
`MTIME = 0` gives `keystream[0:8] = 09 5c 5b a9 a9 8d f5 5f`. That was searched against roughly 25
million combinations: multipliers `0x41C64E6D`, `1103515245`, `214013`, `22695477`, `69069`,
`16807`, `1664525`, `134775813`, `0x5851F42D`; increments `0x3039`, `12345`, `2531011`, `1`, `0`,
`11`; output shifts of 0, 8, 16 and 24 bits; and seeds 0 through 65,535. **No hit.**

The search space contained the correct multiplier (`0x41C64E6D`) and the correct increment
(`0x3039`). It failed on two counts: the seed is `0x28006D45` — about 671 million, four orders of
magnitude past the 65,535 cap — and the output byte is not a plain shift of the state but
`(upper + upper // 255) & 0xFF`, which no shift value would have produced.

**A wrong conclusion drawn from that failure.** The combination of uniform keystream, no
periodicity, and no LCG match was read as pointing at _a stream cipher such as RC4 with a fixed
key_ — which would have been unbreakable from ciphertext alone and would have ended the
investigation. That was wrong. It was an ordinary LCG the whole time; the search was simply bounded
too tightly and assumed too simple an output function. **A failed parameter search is evidence about
the search, not about the algorithm.**

### What came from reading source

The seed `0x28006D45`, the output function `(upper + upper // 255) & 0xFF`, and **the 128 KiB
reset** were read from denigma's `main.cpp` (MIT). None of the three was derived here. The reset in
particular would have been difficult to find from ciphertext: it produces no detectable periodicity
in the ciphertext, because the plaintext beneath it is compressed and therefore random-looking.

All three were then **verified against the corpus**: 401 of 401 archives decrypt and inflate to
valid XML, and the reset specifically was confirmed by decoding the largest file both with and
without it — see the table above.
