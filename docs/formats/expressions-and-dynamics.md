# Expressions, and how a dynamic is written

Status: **identified.** Measured 2026-08-15 against 80 corpus `.musx` documents.

## A dynamic is a character, not a word

`"ff"` appears nowhere in a Finale file. Searching every record payload and the
text streams of the whole corpus finds the `ff` inside *Staff*, the `mp` inside
*Simple* and *Tempo*, and nothing else. A dynamic is stored as **one character
in the Maestro music font**, and Maestro draws one glyph per marking rather
than one per letter.

`fontName` records name fonts by cmper, and **cmper 0 is `Maestro`** in every
document checked — so `^font(Font0,…)` is a music-font reference and the
character after the markup is a glyph, not a letter to read.

## Both containers keep the text the same way

A `.musx` carries it in `texts/expression`; a `.mus` carries the same thing in
its text stream (payload stream 3) as `^expression(n)…^end`. The markup differs
by one word and is otherwise the same dialect:

    .musx   ^fontMus(Font0,0)^size(24)^nfx(0)ë
    .mus    ^font(Font0,0)^size(24)^nfx(0)ë

`^smartshape(n)` sections share the stream and are **not** expressions: they
label glissandi, octave lines and bends. Every Maestro-set section in one
sampled document was a `^smartshape`, which is an easy way to mistake them for
dynamics.

## The file classifies its own expressions

`markingsCategory` carries a `categoryType` — `dynamics`, `tempoMarks`,
`tempoAlts`, `expressiveText`, `techniqueText`, `rehearsalMarks`, `misc` — and
`markingsCategoryName` gives its display name (`Dynamics`). A `textExprDef`
names its `categoryID`. None of this is inferred.

## The table

A `textExprDef` in the dynamics category carries a playback `value`, and its
**`cmper`** selects the expression text holding the character. Nine of the ten
are unanimous across 80 documents; `P` is 62 in 80 and 58 in one, a file whose
playback level was edited. These are the defaults a document ships with:

| glyph | code | velocity |
| --- | --- | --- |
| `ë` | 0xEB | 127 |
| `ì` | 0xEC | 114 |
| `Ä` | 0xC4 | 101 |
| `f` | 0x66 | 88 |
| `F` | 0x46 | 75 |
| `P` | 0x50 | 62 |
| `p` | 0x70 | 49 |
| `¹` | 0xB9 | 36 |
| `¸` | 0xB8 | 23 |
| `¯` | 0xAF | 10 |

`subito p` shares piano's 49, being piano with a word in front of it.

**The order is certain; the names are not claimed.** Calling these `fff`, `ff`
and so on needs Maestro's character chart, and Finale's manual renders it as
images. Two anchors do fall where they should, which is why the ordering can be
trusted: Maestro writes *forte* as `f` and *piano* as `p`, and those sit at 88
and 49 — exactly forte's and piano's places in a ten-step ladder.

## A join error worth recording

`textExprDef.textIDKey` is **not** the expression number. It runs exactly
`cmper + 13`, and reading it as the number pairs every definition with the text
thirteen slots later. Done that way the dynamics category appears to contain
`Adagio`, `Largo` and `Grave`, and the velocity ladder appears to be a
meaningless per-slot default.

It is neither. Pairing on `cmper` puts the tempo words in `tempoMarks` where
they belong and leaves the dynamics category holding only dynamics.

The tell was a **constant offset in a supposed foreign key** — 1→14, 2→15,
3→16. That is a join error, not a fact about the format, and it survived a
first reading because tempo text under a Dynamics heading is odd enough to look
like a real discovery.

## `^DT` — the 2001–2005 text expression, partly decoded

`DT` is the DCL spelling of `textExprDef`. Payloads are 36, 48, 60 or 72
bytes — every one a multiple of 12, the row data width, so the length says
nothing about structure on its own.

**`+4` is a `uint16` playback value.** Confirmed two ways. A velocity from the
dynamics ladder appears there in 405 of 1,794 records (22.6%), which is the
share of expressions that are dynamics — in a `.musx`, about 21% of
`textExprDef` records fall in that category. And three consecutive records read
straight off:

    00 13 00 00 00 7f …   →  +4 = 0x007f = 127
    00 14 00 00 00 72 …   →  +4 = 0x0072 = 114
    00 15 00 00 00 65 …   →  +4 = 0x0065 = 101

the top three rungs of the ladder, in order. `+0` is a plain counter — `0x13`,
`0x14`, `0x15`.

**Read it in the document's byte order.** 37 corpus documents are big-endian,
where `+4` read little-endian gives 32,512 rather than 127.

### What the other offsets look like, and what is not claimed

Measured across 1,794 records. These are *shapes*, not identifications — the
`.musx` `textExprDef` carries `categoryID`, `playType`, `horzMeasExprAlign`,
`vertMeasExprAlign` and `yAdjustBaseline`, and any of them could be here:

| offset | observed | reading |
| --- | --- | --- |
| `+2`, `+6`, `+8`, `+16` | zero in 96–100% | padding, or fields this corpus never sets |
| `+10` | 0 ×608, 2 ×406, 3 ×62 | small enum |
| `+12` | 3 ×1240, 0 ×326, 1 ×165, 4 ×63 | small enum |
| `+14` | 0 ×1275, 1 ×519 | flag |
| `+18` | 1 ×921, 4 ×444, 0 ×410, 5 ×19 | small enum |

**No offset holds the record's own cmper** — the best is 2.1%, which is noise.
So `DT` carries no `textIDKey`-style pointer to its text, and the link to the
`^expression(n)` section is likely positional. That is untested.

### How to finish it

The 2011 era has **95 paired documents**, so its numeric equivalent can be
decoded field by field against the `.musx` twin that names them — the method
that settled the clef table. Then check whether `DT` shares the layout.

Two traps, both hit already: `textIDKey` is `cmper + 13`, so joining through it
yields coherent nonsense; and the enum offsets above will look meaningless read
in the wrong byte order.
