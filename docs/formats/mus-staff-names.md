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
* it is **not arithmetic**. The delta `id - block` is constant within a document in 40 of 41 cases,
  which looks promising until you notice nearly all of those documents resolve only *one* name, so
  constancy is vacuous — and the single document resolving two names has a delta that varies. Across
  documents the delta ranges 63–87 with no relation to the block count.

So there is a genuine lookup record, equivalent to the `.musx`'s `textBlock[cmper] -> textID`, and it
has not been located. The ETF notes list a `TX` record for text blocks, which is the thing to look
for next.

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
