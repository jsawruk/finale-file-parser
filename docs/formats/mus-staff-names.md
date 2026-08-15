# `.mus` staff names: what is established, and the one link still missing

A `.mus` has been recorded as unable to supply staff names, which also blocks group names and would
have supplied the instrument identity the whole-octave transposition case wanted. This is what an
investigation established, and precisely where it stops.

**The names are in the file.** That much is now certain, and it was not before.

## 1. Where the text lives

Text stream 3 carries tagged sections, and `^block(N)…^end` holds the strings:

    ^block(6)^font(Times,4096)^size(14)^nfx(0)Flute^end

**Stream 3, not stream 2.** Both carry `^block` sections and stream 2 is a stale partial copy;
merging them silently picks the wrong text.

The blocks are a **palette**, not a list of what the score uses — every document carries the same
opening run (Score, Percussion, Perc., Flute, Fl., Alto Saxophone…) whether it uses them or not.
This is the third record in this format with that shape, after `textRepeatText` and the reserved
staff, so it is worth assuming until disproved: *~N occurrences across N documents means a
template.*

## 2. Which field selects one

`staffSpec` **+30**, a `u16`.

* It is non-zero **exactly** when the `.musx` names that staff: 156 agree, 1 disagrees, over 157
  staves.
* Within a document it is the **only** offset that distinguishes differently-named staves — 4 of 4
  documents that have two, with no collisions. Every other offset collides.

A caution for anyone re-checking this: across the corpus 62 differently-named staves all read
**93**, which looks like proof it *cannot* be a name reference. It is not: those are 62 staves in 62
different documents, nearly all with a single named staff, and 93 is simply a common id in a shared
template. Only the within-document test discriminates.

+32 is the abbreviated name by the same argument, and the two are consecutive (93/94).

## 3. The missing link

**How the +30 id reaches a block number.** Nothing found so far performs that lookup:

* it is not the block number itself — ids run 92–97 while blocks run 1–30;
* no `others` record keyed at the id contains the block number at any stable offset. The one
  apparent hit, tag 148, is the chord-suffix table ("Dim 7 (add maj7)", "Aug") and matched by
  coincidence;
* ~~it is **not arithmetic**~~ — **RETRACTED, 2026-07-29. See §3a.**

### 3a. The arithmetic route was retracted, and why that matters

The bullet above used to say the relation is not arithmetic, on two grounds. Both were artefacts of
how the corpus was being read, not facts about the corpus.

**"Only one document resolves two names, so constancy is vacuous — and that one varies."** Five
documents resolve two or three. They were invisible because oracle pairing chose a `.musx` for each
filename stem by directory-walk order, and the candidate it happened to pick for those five failed
the same-music filter, so they reached no paired sweep. In **all five** the delta `id - block` is
constant: 70, 71, 71, 71, 69.

And the blocks it lands on are the right ones, which is the part arithmetic alone would not give:
`1st Violin / 2nd Violin / 3rd Violin`, `Oboe / English Horn / Clarinet in B♭`,
`Soprano-Alto / Tenor-Bass`, `Trombone`. Three staves, three different correct names, in order.

**"Across documents the delta ranges 63–87."** That number was computed across two *different id
spaces* and therefore measured nothing. The `.mus` id and the `.musx` `textBlock` cmper agree for only
**25 of 83** named staves: where a `.musx` was re-saved it renumbered its text blocks, so it says
`fullName` 2 where the `.mus` says 93. A cross-container delta is meaningful only for those 25.

Both of these, and the count of documents that can test the relation at all, are pinned in
`tests/enigma/test_mus_staff_name_link_corpus_sweep.py` — including the count itself, because a
harness that hid this evidence once can hide it again.

**One other fact confirmed on the way:** the `.musx`'s `textID` *is* the `.mus` stream-3 block number.
Following `staffSpec.fullName -> textBlock -> textID` in a `.musx` and reading that block number out
of the paired `.mus` yields the staff's own name. So the two containers agree on block numbering even
where they disagree on id numbering.

### 3b. What is actually still missing

**The per-document base.** The delta is constant within a document but differs between documents, and
nothing yet found supplies it. Searching for a record keyed at the id that holds the block number
still fails: with the exact oracle above (the `.musx`'s `textID` rather than a name string, which only
matches verbatim 45 times in 75) the best candidate explains 27 of 83 — tag 121 at +42, which is the
articulation-definition table and matching by coincidence.

So one anchor per document would resolve every name in it. That is the whole of the remaining gap,
and it is a much smaller one than "there is a lookup record nobody can find".

### 3d. RETRACTED AGAIN: there is no per-document base

**The unknown was mis-stated, by me, twice.** §3a and §3b describe what is missing as a
*per-document base* — a number that turns an id into a block and differs from document to document.
It does not exist, because **the mapping is document-independent**.

The evidence is a single id measured across genuinely different music. **Name id 2 selects text
block 30 in ten documents — ten distinct pieces, ten distinct entry counts** (Angels We Have Heard,
Away in a Manger, Deck the Hall, Good King Wenceslas, Hark! the Herald, Jingle Bells, Joy to the
World, Ode to Joy, Silent Night, We Wish You). Across all 25 anchors and 9 distinct ids, **no id ever
selects two different blocks**.

The delta appeared to vary between documents only because different documents use different ids.
Within a document it is constant because the ids and blocks both advance by two (§3c); between
documents it "varies" for the trivial reason that a document starting at id 93 and one starting at
id 2 are not comparable numbers.

The independence matters as much as the constancy, and is pinned separately: three of the other
repeats are variants of one arrangement, and reading those as ten-fold corroboration is exactly the
near-duplicate trap this corpus has sprung before. Entry count stands in for "different music",
which is the same filter the oracle pairing uses.

**What this changes.** The remaining work is to recover a *fixed table*, not to compute anything per
document. Observed so far, and never contradicted:

| name id | text block |
| --- | --- |
| 2 | 30 |
| 89 | 20 |
| 91, 92, 93 | 22 |
| 94, 95 | 24 |
| 97 | 26 |
| 98 | 37 |

That is 9 ids over about 6 independent documents — enough to establish the *shape* of the answer and
far too little to ship as a table. Note that the map is many-to-one and not arithmetic: 91, 92 and 93
all select block 22. Any attempt to fit a formula to nine points would be the palette trap again.

**So the gap is now a data problem rather than a reverse-engineering one.** It closes when either
more paired documents cover more ids, or Finale's own default table is obtained from outside this
corpus. It does not close by staring harder at these files.

### 3e. §3d re-tested and upheld — and how it nearly got overturned wrongly

**2026-08-15.** §3d says the id-to-block map is document-independent, resting on
25 anchors. That looked thin, so it was re-tested against a larger set — and the
larger set was wrong.

The tempting move is to treat every `.mus` name id paired with the block the
`.musx` reaches through `staffSpec.fullName -> textBlock -> textID` as evidence.
There are **144** of those, not 25, and read that way ids 93 and 94 each select
half a dozen different blocks — which would overturn §3d outright. It does not,
because 119 of the 144 are not anchors at all:

| | |
| --- | --- |
| **25** | valid: the block exists in the `.mus` **and holds that staff's name** |
| **116** | the block is absent from the `.mus` stream entirely |
| **3** | the block exists but holds different text |

The 116 are re-saved `.musx` files whose text blocks were renumbered, so their
`textID` points at a block this `.mus` does not have. In **65** of them the name
appears in no block at all: the `.mus` does not carry that name.

So **a candidate is only an anchor if the block exists and holds the name**, and
that criterion — not "the id spaces agree" — is what reduces 144 to 25. Two
independent routes now reach the same 25, which is the strongest thing that can be
said for it. `ANCHOR_VALIDITY` in the sweep pins all three counts, because
inflating this set produces a confident wrong answer rather than a visible
failure.

**One real discrepancy survives.** Among the 25, id **94** selects block 23 twice
and block 24 once. §3d's table records 94 -> 24. That is a 2-against-1 split on
three votes, far too little to rewrite the table with and too definite to ignore,
so it is recorded rather than resolved.

### 3f. Two more routes closed

**The lookup record does not exist.** Searched two ways over all 144 candidates:

* a record keyed at the name id holding the block at any even offset — best is
  tag 183 at `+0`, **28 of 144**, which is noise;
* the `(id, block)` pair written adjacently as two `uint16`s **anywhere** — any
  `others` payload, any `details` payload, any stream. Absent in **129 of 144**,
  and the 15 hits scatter across four unrelated tags.

The pair is not stored anywhere in the file. That is now a measured negative
rather than a search that failed.

**The renumbering cannot be undone.** The obvious rescue for the 116 is to find
the staff's name among the blocks and take the difference as a per-document
offset. 47 resolve to exactly one block, and their deltas are 1, 2, 21, 16, 20,
22, 17, 3, 5 and 23 — ten values, no rule, and only 37 of 42 documents are even
self-consistent. It is also the palette trap wearing a new hat: a staff called
`Flute` matches the template's `Flute` block rather than its own.

### 3c. Why the delta is constant, and four more approaches ruled out

**The constancy now has a reason.** A staff has a full name and an abbreviated one, at `staffSpec`
+30 and +32, and those are consecutive ids. The blocks they select are consecutive too. So each named
staff consumes **two ids and two blocks**, the sequences advance in lockstep — verified, id step 2 and
block step 2, in all five multi-anchor documents — and `id - block` cannot drift within a document.

That reduces the problem precisely: the two sequences are rigid, so **everything hinges on where they
start**. One anchor per document is still the whole of it.

Ruled out since, each stated with the method so it is not re-run:

| searched | result |
| --- | --- |
| the block region derived from the shared palette | fails. Block 1 is the document title, so "first block whose text differs from the palette majority" is always 1; and the name blocks (20, 22, 24, 26, 30, 37 across the corpus) sit *inside* the palette's numeric range rather than after it |
| the blocks a document overrides, as a set | not a rule, a heuristic. Blocks 14-19 hold title, composer and markup; the names are somewhere after, and picking them out by inspecting text is the kind of fit this file already warns about |
| a record holding the base directly, at any offset to +80 | no `others` record matches all 17 anchored documents; the best explains 4 |
| **a table indexed by the id** — the shape `instUsed` (tag 159) and `repeatPassList` both turned out to have | none. No `(tag, base, stride)` satisfies `u16(payload, base + stride x id) == block` for even one document's anchors, over strides 2-24 and bases 0-64, in `others` or `details` |

The table search is the one worth noting as a genuine surprise: two other fields in this format
resolved to arrays in a single record, so a text-block table was the natural next guess, and it is
not there.

**Searched for, and not found: a record holding the base.** With the anchors above the target is
exact — for a document with an anchor, the base *is* `id - block` — so a candidate can be required to
equal it in **every** anchored document rather than merely correlate. 17 documents have an anchor
with a single consistent delta. **No `others` record at any offset up to +80 matches all 17**; the
best explains 4. Nor is the delta a constant: it takes values −28, 61, 69, 70 and 71 across those
documents.

The 25 anchors themselves are sound — each resolves to a plausible name in its own `.mus`
(`Voice`, `Percussion`, `Soprano-Alto`, `1st Trumpet`, `Trombone`), which is what rules out the
worry that requiring only "the id is *a* textBlock cmper" would manufacture anchors that merely
point somewhere.

Worth recording for whoever picks this up: tag 183 at +0 is the *shape* a base would have — one value
per document, constant while the block varies — and §3's original table dismissed it for exactly that
property, on the assumption the record should hold the block number. It is not the base either
(4 of 17), but the reasoning that dismissed it was looking for the wrong thing.

So there is a genuine lookup record, equivalent to the `.musx`'s `textBlock[cmper] -> textID`, and it
has not been located. Ruled out so far, each against the 45 name/block pairs the corpus yields:

| searched | result |
| --- | --- |
| every `others` record keyed at the id, every offset | best 24% (tag 183 at +0) — and its value is constant per document while the block varies, so it is coincidence |
| every `details` record keyed at the id (either cmper), every offset | best 4 of 540 |
| an arithmetic relation | delta varies across documents, 63–87, unrelated to block count |
| blocks numbered in the id range | none: every `^block(` has an `^end` (2,654 of 2,654) and the highest is 37 |
| **stream 2**, which no reader consumes, as a flat table | no stride/base fits; and its size varies (9,044–13,376), so it is not a fixed table |

**Stream 2 is worth naming even so: nothing reads it.** A `.mus` with four streams uses 0 for the
`others` pool, 1 for `details`, 3 for text — and 2 is untouched by any reader in this project.
Whatever it holds is unexamined.

A second thing surfaced while mapping the streams: **38 of 137 `.mus` documents appeared to have
only one stream.** That has since been chased down and was wrong twice over — the count was 139 of
238 (a case-sensitive glob was dropping every `.MUS`), and those files have four pools, not one.
See `docs/formats/mus-dcl-container.md`. Their `others` pool is now reachable, but it is a different
record encoding, so it does not yet yield staff names either.

## 4. A limit that will remain even then

The two containers do not agree on the strings. Where both name a staff, the `.musx` says
`Tenor Sax` and the `.mus` says `B♭ Tenor Saxophone`; `Double Bass` against `Bass`. Only 45 of 75
named staves match verbatim.

So a paired comparison can never be an exact-match test here — it has to tolerate abbreviation, or
be treated as a fuzzy oracle, as the part-name work already found.

## 5. What was fixed along the way

`plain_text` failed to strip the binary markup dialect whenever the text was decoded as **cp1252**.
The pattern matched `\^[-ÿ].{4}`, but cp1252 maps the opcode bytes 0x84, 0x85 and 0x86 to
U+201E, U+2026 and U+2020 — all outside Latin-1. A `.mus` staff name came back as
`^…\x01\x01\x01\n^†\x01\x01\x01\rScore` instead of `Score`.

Widening the class to any non-ASCII character fixed it, and took verbatim name matching from 12 of
75 to 45 of 75. The bug affected every `.mus` string that uses that dialect, not only staff names.
