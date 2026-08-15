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

## Which expressions a score actually places

The table above is the **library** every document ships. What a score *uses* is a
`measExprAssign`, and the difference matters: reading the library would print a
fortissimo in every part of every file, the same trap `textRepeatText` sets.

    measExprAssign(measure)  -- placed here, on this staff, in this layer
      -> textExprID          -- names a textExprDef
        -> cmper             -- names the expression text

**The join holds.** Across 401 documents every assignment that carries an id
resolves — 5,663 through `textExprID` and 91 through `shapeExprID` — with none
dangling. The other 7,488 carry no id and place nothing.

Read this way the corpus yields **11,543 placed expressions**, of which 6,366 are
dynamics in 319 documents:

| marking | f | mf | p | mp | ff | fp | fz | pp | ppp | fff | pppp | ffff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| count | 1715 | 1516 | 1503 | 834 | 420 | 330 | 276 | 191 | 60 | 38 | 22 | 15 |

That shape is itself the evidence. A palette read by mistake gives a flat count,
about one of each per document; real music is steeply uneven, with the middle of
the range dominant and the extremes rare.

### When a glyph counts as a dynamic

Five of the ten characters are **plain ASCII letters** — Maestro writes forte as
`f` — so matching the character alone would read a literal "f" label as a
fortissimo. The font markup settles it:

| category | font | glyph in the table | count |
| --- | --- | --- | --- |
| `dynamics` | `^fontMus` | yes | 6,182 |
| `techniqueText` | `^fontMus` | yes | 1,191 |
| `dynamics` | none | yes | 114 |
| `misc` / `tempoMarks` / `expressiveText` | none | yes | 129 |
| anything | `^fontTxt` | **yes** | **0** |

**Nothing set in a text font ever matches the table**, so the font never produces
a false dynamic. The 1,191 `techniqueText` rows are user copies of a Maestro
dynamic filed in a custom category — still dynamics. A marking is therefore
claimed when the glyph is in the table *and* either the text is set in a music
font or the document's own category is `dynamics`; the 129 rows with neither
signal are carried as text and left unnamed.

### Score expressions, and the 317 that still do not reach the IR

Read: 11,462. Reaching a `Measure`: **11,145**.

**A score expression names no staff.** `staffAssign = -1` means it belongs to a
staff list — 746 corpus assignments — and the file says so, since all of them
also carry `staffGroup` *and* `staffList` where a positive-staff assignment
almost never does (138 of 11,687). 81 are a redundant second copy of a marking
already placed on a real staff and are dropped; the other **515 are placed on the
topmost part**.

**What the staff list selects is still not decoded**, and the placement is
therefore a *convention*, not a reading. The list record is now understood
structurally: `others` **306** for the score and **304** for the parts, a
**six-slot `uint16` array** where zero fills an unused slot.

| pattern | tag 306 | tag 304 |
| --- | --- | --- |
| `(-1, 0, 0, 0, 0, 0)` | 1486 | 1546 |
| `(2, 0, 0, 0, 0, 0)` | 88 | — |
| `(-1, 1, 0, 0, 0, 0)` | — | 28 |
| `(-1, 3, 0, 0, 0, 0)` | 8 | 8 |
| `(-1, 2, 0, 0, 0, 0)` | 2 | 2 |

That kills the reading I could not previously rule out: **zero is the empty-slot
filler, so `-1` is a value rather than an end-of-list marker.** What it stands for
is still unestablished — `(2, 0, …)` shows a slot can hold a real staff with no
`-1` present at all, and `(-1, 3, …)` shows `-1` sitting beside one.

**The key is `staffList`, not `categoryID`.** Those differ in **all 746** cases,
and `categoryID` reaches values (25, 26, 29) for which no list record exists —
custom categories. The tag name `categoryStaffList*` misleads.

Placing on every staff was rejected on measurement: it would turn 596 markings
into **2,481**, printing a dynamic on staves the list may exclude. One part is
recoverable information; eighteen copies would be an invention. `<sound>`-style
score-wide direction does not exist in MusicXML, so a part had to be chosen, and
the top staff is where such a marking is engraved.

**The 317 still dropped** are all one cause: assigned to a staff holding no notes,
so no `Part` exists for them. All of these counts are pinned in both directions by
`tests/enigma/test_expressions_ir_corpus_sweep.py`.

### Rehearsal marks: the label is computed, not stored

113 assignments carry an expression whose text is the bare insert
`^fontTxt(Times New Roman,4096)^size(12)^nfx(65)^rehearsal()`. There is no letter
in it. `plain_text` yields `""` — correctly, since the block has no literal text
— and every one of them was dropped for having nothing to print.

Finale works the label out when it draws, and the file says **how**:
`rehearsalMarkStyle`.

| style | corpus | label |
| --- | --- | --- |
| `measNum` | 99 | the measure number — **a fact, not a convention** |
| `letters` | 12 | A, B, C in measure order — the one convention here |
| absent | 2 | none; the mark is dropped rather than given a made-up letter |

For the great majority the label is simply the bar the mark sits at, so nothing
is invented. Only the twelve `letters` marks are numbered by position, and that
is Finale's own sequence (past Z it continues AA, AB).

**One mark, one label.** A mark drawn across a system is several assignments —
the corpus has one on staff `-1` and on staves 9 and 13 of the same measure — so
the label is keyed by measure. Numbering per assignment would give one bar two
different letters.

**90 marks are placed**, in 10 documents, and all 90 reach the IR. The other 23
are accounted for: 21 are a score-wide copy of a mark the same measure already
places on a real staff, and 2 have no readable style.

They export as `<rehearsal>`, not `<words>` — different elements, and a consumer
treats a rehearsal mark as a navigation target.

### What the exporter does with them

`<dynamics><ff/></dynamics>` for a named marking, `<words>` for anything that
reads as words, and nothing at all for an unidentified music-font glyph — a
literal `§` in a score is worse than an omission. `subito p` goes to
`<other-dynamics>`, since its name has a space and `<subito p/>` is not XML.

**Velocity is not exported.** MusicXML carries playback on `<sound dynamics>` as
a percentage of MIDI velocity 90, and that conversion is unverified here. The IR
keeps the number; the exporter drops it at the edge.

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

## The 2011 `.mus`: both records decoded

A 2011-era `.mus` carries the same two records as a `.musx`, under numeric tags,
and both are now read — **3,022 markings across 186 documents**.

**How the definition was found.** By asking the record to name itself. A
`textExprDef` carries a `descStr`, so every 2011 payload was searched for text of
that shape: **exactly one tag matched** — `241`, 958 records in 85 documents. The
same move that named the ten dynamics found the record that holds them.

Decoded against the 97 paired documents, little-endian, by **exact equality**
rather than a fitted mapping:

| offset | field | agreement |
| --- | --- | --- |
| `+0` u16 | `textIDKey` | 7180/7180 |
| `+4` u16 | `value` | 2107/2107 |
| `+6` u16 | `auxdata1` | 457/457 |
| `+8` u16 | `playPass` | 34/34 |
| `+12` u16 | `horzMeasExprAlign` | 4 values, clean over 6892 rows |
| `+24` u16 | `vertMeasExprAlign` | 4 values, clean over 5147 rows |
| `+30` s16 | `yAdjustBaseline` | 4700/4700 |
| `+32` s16 | `yAdjustEntry` | 5079/5079 |
| `+36` | the description, NUL-terminated | **wording identical to the `.musx`** |

The enum vocabularies, read off the pairs rather than guessed:
`horzMeasExprAlign` 1 `startTimeSig`, 3 `manual`, 13 `leftOfPrimaryNotehead`,
14 `rightOfAllNoteheads`; `vertMeasExprAlign` 2 `manual`, 4 `topNote`,
8 `aboveStaffOrEntry`, 9 `belowStaffOrEntry`.

**Not identified, and not guessed.** `categoryID` peaks at 20.3%, which is noise.
`playType` partitions cleanly at no offset. `+4` also matches `execShape` at
234/234, but that is a coincidence of coverage — the records carrying `execShape`
are a subset of those carrying no `value` — and `value` is independently confirmed
by the dynamics ladder and by the description stating the same number.

### The assignment: tag 177, in 24-byte slots

Found by content, not by counting: count-matching against the `.musx` assignment
total peaked at 14 of 97 documents, which is chance. Asking instead *which
tag/offset holds a number that the paired `.musx` assigns as an expression id at
that same measure* gave one answer — tag 177 at `+0`, **1133/1166 = 97.2%**, with
every rival at or below 18%.

The payload is an **array of 24-byte slots**, one per marking. The stride is
measured: read at 24, a slot's first u16 is an assigned expression id in 96.3% of
1,555 slots; read at 12 it is 48.1% and the slot count stops matching the
assignment count.

| offset | field | agreement |
| --- | --- | --- |
| `+0` u16 | `textExprID` | 1044/1044 |
| `+2` s16 | `horzEduOff` | 400/401 |
| `+4` s16 | `horzEvpuOff` | 975/976 |
| `+6` s16 | `vertOff` | 981/982 |
| `+8` s16 | `staffAssign` (−1 means a staff list) | 1044/1044 |
| `+11` u8 | flags; `0x20` marks a **shape** assignment | 57/57 and 0/1497 |
| `+12` u16 | `staffGroup` | 57/57 |
| `+14` u16 | `staffList` | 57/57 |

**The flag at `+11` matters more than it looks.** A shape assignment's `+0` is a
`shapeExprID`, so reading it as a `textExprID` places whatever definition happens
to share that number. That produced **44 spurious markings** across the paired
corpus — dynamics in scores that have none there. The bit separates the groups
completely: set on all 57 shape slots, on none of the 1,497 text slots.

`layer` is not identified: its best offset is `+8`, which `staffAssign` already
holds at 100%.

### Checked against the other container

For 91 documents the corpus holds both, so the markings compare triple by triple:
**1,464 of 1,476 `(staff, measure, marking)` triples agree** — 99.2%. Before the
shape flag it was 1,464 against 52, and **44 of those 52 were the wrong
direction**: markings the `.mus` invented rather than missed. The remaining 12 are
markings the `.mus` path misses, which is a gap rather than wrong output, and the
sweep asserts that direction explicitly.

**A `.mus` expression has no category and no layer.** Both are absent rather than
invented, and the dynamics are named anyway — from `descStr`, which is the
stronger signal in any container.

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

### `DT` names itself too

The DCL payload carries a description, exactly as the 2011 record does — but in
that era's wording, which states the **placement** rather than the marking:
`'Below Staff (Vel. 127)'`, `'Below Staff'`, `'Adagio'`, `'Tempo = 40'`.

That is enough to confirm `+4` **without any paired document**: the velocity the
description states equals the u16 at `+4` in **434 records out of 434, with zero
disagreements**. `DT` vouches for its own field.

It is not enough to carry the rest of the layout across. The 2011 record puts
`vertMeasExprAlign` at `+24`, and if `DT` did the same then a description reading
"Below Staff" should pin one value there — **no offset separates the "Below
Staff" descriptions from the rest**. The shared offsets are `+0`, `+4`, `+32` and
the description at `+36`; the enums are not claimed.

Because the DCL description names a placement instead of a dynamic, it also
cannot name the marking the way the 2011 one does. That route works for the newer
era only.

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
