# Expressions, and how a dynamic is written

Status: **identified, and now named.** Measured 2026-08-15 against 401 corpus
`.musx` documents.

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

## The file names them itself: `descStr`

A `textExprDef` carries a **`descStr`**, and for a dynamic that field spells the
marking out in words with its playback level attached:

    descStr = 'fortissimo (velocity = 101)'   value = 101
    descStr = 'forte (velocity = 88)'         value = 88

So no font chart is needed to say which glyph is which. This is worth dwelling
on, because the previous reading of this file concluded the opposite — that
naming them "needs Maestro's character chart, and Finale's manual renders it as
images". The chart was never the obstacle. `descStr` was in the record all
along, in the same record already being read for `value`, and was not looked at.
It is the recurring failure in this project: *"the corpus cannot tell us" is
usually "our selection code did not ask"*.

`descStr` and `value` sit in the **same record**, so name-to-velocity needs no
join at all: they agree in 4,369 records against 9 exceptions, and every
exception is a document whose playback level a user edited.

## The table

Measured across 401 parsed `.musx` documents, of which 393 contribute a glyph.
The abbreviations are the conventional spellings of the Italian words the file
uses; the words and the velocities are what was read out of the file.

| glyph | code | `descStr` | marking | velocity |
| --- | --- | --- | --- | --- |
| `ë` | 0xEB | fortissississimo | `ffff` | 127 |
| `ì` | 0xEC | fortississimo | `fff` | 114 |
| `Ä` | 0xC4 | fortissimo | `ff` | 101 |
| `f` | 0x66 | forte | `f` | 88 |
| `F` | 0x46 | mezzo forte | `mf` | 75 |
| `P` | 0x50 | mezzo piano | `mp` | 62 |
| `p` | 0x70 | piano | `p` | 49 |
| `¹` | 0xB9 | pianissimo | `pp` | 36 |
| `¸` | 0xB8 | pianississimo | `ppp` | 23 |
| `¯` | 0xAF | pianissississimo | `pppp` | 10 |

The two anchors land where they must: Maestro writes *forte* as `f` and *piano*
as `p`, and those are the fourth and seventh rungs — exactly forte's and piano's
places in a ten-step ladder. That was the only evidence for the ordering before
`descStr` was read; it is now a cross-check on it.

### The five that shape an attack

These carry **no `value`** in the shipped library — they modify an attack rather
than setting a level:

| glyph | code | `descStr` | marking |
| --- | --- | --- | --- |
| `ê` | 0xEA | forte piano | `fp` |
| `Z` | 0x5A | forzando | `fz` |
| `S` | 0x53 | sforzando | *not claimed* |
| `§` | 0xA7 | sforzato | *not claimed* |
| `\x8d` | 0x8D | sforzato | *not claimed* |

**Three are deliberately unnamed.** `§` and `\x8d` have the *same* `descStr`, so
the file does not say which is which, and *sforzando* is written `sf` and `sfz`
both. Naming them needs evidence this project does not have.

"No `value`" is the shipped default, not a rule: a user may set a playback level
on any expression, and one corpus document gives its *sforzando* 88 with
`playType='amplitude'`.

`subito p` — the one library entry whose text is more than one character —
shares piano's 49, being piano with a word in front of it.

### A cross-check from another category

`value` is not velocity-specific; it is *the playback number for this
expression*. In `tempoMarks` the same field holds beats per minute, and the
words confirm it: `Adagio` 40, `Moderato` 108, `Allegro` 120, each matching the
`q = …` printed in its own text.

## Which key joins a definition to its text

Join on **`cmper`**. `textExprDef.textIDKey` is not the expression number:
reading it as one pairs every definition with a text some slots later, and done
that way the dynamics category appears to contain `Adagio`, `Largo` and `Grave`
while the velocity ladder looks like a meaningless per-slot default. Pairing on
`cmper` puts the tempo words in `tempoMarks` where they belong and leaves the
dynamics category holding only dynamics. `descStr` now confirms this
independently: the definition described `forte (velocity = 88)` prints `f`,
where the `textIDKey` reading would pair *forte* with *Adagio*.

The tell was a **constant offset in a supposed foreign key** — 1→14, 2→15,
3→16 — which is a join error, not a fact about the format.

### The offset is not 13, and that matters

An earlier note here recorded `textIDKey` as running "exactly `cmper + 13`".
Measured across all 396 documents that reach a named dynamic, the offset
`textIDKey − number` is **13 in 368 documents, 19 in 21, and 1 in 7**. It is not
a constant, so it is not a rule — 13 is just what the MakeMusic template
documents happen to use. What `textIDKey` actually indexes is **not established**
and is not guessed at here.

Counting which join names all ten dynamics correctly: `cmper` in 391 documents,
`textIDKey − 13` in 357. `cmper` wins, which is why it is the rule.

### `cmper` can still slip, in one known way

`Christmas Canon.musx` had its *mezzo forte* **deleted**. Expression text number
5 is simply missing from the pool (`…'4', '6', '7'…`) while the definitions were
renumbered to close the gap, so definition 6 is now *piano* and every glyph
below the hole pairs with its neighbour's description:

| cmper | `descStr` | `texts[cmper]` | correct glyph |
| --- | --- | --- | --- |
| 5 | mezzo piano | *(missing)* | `P` |
| 6 | piano | `P` | `p` |
| 7 | pianissimo | `p` | `¹` |

In *this* document `textIDKey − 13` gives the right answer for every row, and
`textIDKey` even skips 18 exactly where the deleted text was — so it is a real
pointer into the text pool, just one whose base this project cannot yet predict.

The corpus sweep therefore **validates the join per document before trusting a
glyph**: the definition described `forte` must print `f` and the one described
`piano` must print `p`, or the document contributes nothing and is counted as
desynchronised. Dropping such a document silently would be worse than failing.

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

Two traps, both hit already: joining through `textIDKey` yields coherent
nonsense (see above — and the offset that makes it look tidy is not even
constant); and the enum offsets above will look meaningless read in the wrong
byte order.

A third, learned the expensive way here: **read the fields the record already
has before reaching for an external source.** `descStr` named all ten dynamics
and was sitting in a record this project had been parsing for weeks.
