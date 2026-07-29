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

`spell_pitch` took the written octave from `harm_lev` and the written key's tonic and never
consulted the transposition. `spell_note` now adds `written_octave_correction(interval)` first —
the octaves Finale folded into `harm_lev`, undone — **but only where the transposition has a
non-octave residue.**

That gate is the whole finding. The two cases are stored differently:

* **A transposition with a residue** (every ordinary transposing instrument) keeps the residue in
  the staff record and the octaves in `harm_lev`. Undoing the fold gives the pitch the player reads.
* **A whole-octave transposition** leaves the residue at zero and the key unchanged, so the staff is
  recorded as though it did not transpose at all, with `harm_lev` already at the written octave.
  There is nothing to undo, and undoing it moves the part an octave.

## 4. How it was adjudicated

Not against Finale. The `.musx` in this corpus were produced by Finale *from* the matching `.mus`,
so the two are not independent witnesses and agreement between them proves only consistency.

The interval values identify the instruments outright, and every one has a **published written
range** — what a player reads, owing nothing to any file format:

| interval | adjust | instrument | published written range |
| --- | --- | --- | --- |
| −7 | 0 | Xylophone | F4–C7 |
| 1 | 2 | B♭ Trumpet | F♯3–D6 |
| 4 | 1 | F Horn / English Horn | F3–C6 |
| 5 | 3 | E♭ Alto Sax | B♭3–F♯6 |
| 7 | 0 | Double Bass / Guitar | E2–B4 |
| 8 | 2 | B♭ Tenor Sax / Bass Clarinet | B♭3–F♯6 |
| 12 | 3 | E♭ Baritone Sax | B♭3–F♯6 |

Share of notes falling inside the instrument's published range, over 45,000 corpus notes on
transposing staves:

| instrument | residue | before | after |
| --- | --- | --- | --- |
| E♭ baritone sax | 2 | **7.3%** | **100.0%** |
| B♭ tenor sax | −1 | 37.9% | **89.0%** |
| E♭ alto sax | 2 | 87.0% | **98.8%** |
| double bass / guitar | **0** | 87.3% | 87.3% (untouched) |
| xylophone | **0** | 100.0% | 100.0% (untouched) |
| B♭ trumpet | −1 | 91.6% | 91.6% (no octave folded) |
| F horn | −4 | 87.7% | 87.7% (no octave folded) |
| **all transposing notes** | | **82.0%** | **91.6%** |

Every instrument either improves or is untouched. The saxophone family is the sharpest check: alto,
tenor and baritone all read the same written range — that is what the family is for — and before the
fix they spelled an octave apart from each other.

## 5. What is still lost

The `.mus`/`.musx` octave-only differences fall from **2,491 to 845**, and **every one that remains
sits on a whole-octave transposition** (interval 7 — double basses and guitars).

Those are the one case a `.mus` genuinely cannot recover, and now for a precise reason: a
whole-octave transposition leaves the residue at zero and the key unchanged, so the staff is
recorded as though it did not transpose at all. Nothing in the file distinguishes a double bass
written at sounding pitch from a non-transposing staff. That the remainder is exactly the residue-0
set is the check that the correction is the right shape rather than a fitted constant.
