# The transposition octave: where it is, and why Finale does not need it

This project recorded, for several sessions, that a `.mus` "cannot supply the transposition octave"
and that 2,491 written pitches therefore came out an octave wrong. The first half is true and is now
proven exhaustively. **The second half was the wrong conclusion.**

## What was asked

If the octave is absent from the file, how does Finale itself display these staves correctly?

## 1. The octave is not in the file

Three independent searches, over the 84 paired documents that carry a transposing staff (58
document-and-staff cases, 15 of them transposing by a whole octave or more):

| search | result |
| --- | --- |
| every byte of `staffSpec`, comparing staves an octave apart | **no byte separates them.** Interval 1 vs 8, 5 vs 12 and 0 vs 7 all share byte-identical payloads — for 5 vs 12 the payload *sets* are equal |
| every field of every record keyed by a staff, against the full interval | **no exact candidate** |
| the same, against the octave count alone | **no exact candidate, and not one field that even separates** octave-transposing staves from the rest |

`staffSpec` also carries no `extra` block (0 bytes on all 204 records), so there is no undecoded
tail to hide in.

The `transposition` word at `staffSpec` +20 holds the **residue** and nothing else. Measured
directly:

| interval | adjust | stored word |
| --- | --- | --- |
| 0 | 0 | 0 |
| 7 | 0 | 0 |
| 1 | 2 | 66 |
| 8 | 2 | 66 |
| 5 | 3 | 3971 |
| 12 | 3 | 3971 |

Each pair differs by exactly seven diatonic steps — one octave — and stores the same word.

## 2. How Finale understands it anyway

**The octave is baked into `harm_lev`.**

Finale folds the octaves out of a transposition into a residue in −4..+2. It folds the same octaves
*into every note's `harm_lev`*. The two are a matched pair, and either pairing determines the same
written pitch.

Measured across 30,000+ notes on transposing staves, `.musx` `harm_lev` minus `.mus` `harm_lev`:

| interval | octaves folded out | measured delta |
| --- | --- | --- |
| 1 | 0 | **0** |
| 4 | 0 | **0** |
| 5 | 1 | **−7** |
| 7 | 1 | **−7** |
| 8 | 1 | **−7** |
| 12 | 2 | **−14** |

Exactly seven per octave, with no exceptions beyond two notes in the single document the entry-pool
sweep already pins as a revision difference.

So a `.mus` records the residue and an unshifted `harm_lev`; a `.musx` records the full interval and
a `harm_lev` shifted to match. **Neither needs an octave field, because each is internally
consistent.** Finale reading a `.mus` has everything it requires.

## 3. The fix

`etfspec.pdf` anchors `harm_lev` absolutely:

> "The harmonic value 0 will always be the tonic of the current key **in the octave from middle C to
> the C above**. For example, in G major, 0 is the G above middle C."

No transposition enters that rule. So `harm_lev` alone places the written octave, and a container
that stores it shifted needs the shift undone. `spell_note` adds
`written_octave_correction(interval)` — the folded octaves, returned — **for a downward
transposition**, one whose written pitch sits above concert.

An **upward** transposition shows no such fold. A xylophone sounds an octave above what it reads,
and correcting it moves the part an octave. That asymmetry rests on a single instrument — 600 notes
across three staves, with no paired `.mus` to check against — and is the weakest part of this.

## 4. How it was adjudicated

Not against Finale. Every `.musx` in this corpus was produced by Finale *from* the matching `.mus`,
so the two are not independent witnesses and agreement between them proves only consistency.

The interval values identify the instruments outright, and each has a **published written range** —
what a player reads, owing nothing to any file format. **Each instrument is measured against its
own range**; lumping the two interval-7 instruments under one compromise range is what hid the last
error.

| instrument | interval | published written range | before | after |
| --- | --- | --- | --- | --- |
| E♭ baritone sax | 12 | B♭3–F♯6 | 7.3% | **100.0%** |
| B♭ tenor sax | 8 | B♭3–F♯6 | 37.9% | **89.0%** |
| E♭ alto sax | 5 | B♭3–F♯6 | 87.0% | **98.8%** |
| Double bass | 7 | E2–G4 | 69.8% | **99.7%** |
| Classical guitar | 7 | E3–B5 | 82.1% | **99.7%** |
| Xylophone | −7 | F4–C7 | 100.0% | 100.0% (untouched) |
| B♭ trumpet | 1 | F♯3–D6 | 91.6% | 91.6% (no fold) |
| F horn | 4 | F3–C6 | 87.7% | 87.7% (no fold) |
| **all transposing notes** | | | **82.0%** | **94.4%** |

The saxophone family is the sharpest check: alto, tenor and baritone read one written range — that
is what the family is for — and before this they spelled an octave apart from each other.

## 5. What is lost: nothing

The `.mus`/`.musx` octave-only differences fall from **2,491 to 1**, and that one is not a
transposition fault at all: it sits on a concert staff where the two files disagree about the
music — a chord in the `.mus` against a single note in the `.musx` — and lands in the bucket only
because the comparison lines a D4 up against a D5.

So a `.mus` gives the same written pitch as its `.musx` on every transposing staff in the corpus.
The octave was never missing from it, and no `UNTRANSLATED` entry is needed for transposition.
