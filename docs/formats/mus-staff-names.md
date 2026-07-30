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
