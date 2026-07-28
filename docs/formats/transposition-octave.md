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

## 3. What that means for this project

Our `spell_pitch` takes the written octave from `harm_lev` and the written key's tonic, and never
consults the transposition's octave count. That is correct for a `.mus`, where the count is zero by
construction, and off by exactly the count for a `.musx`.

Undoing the fold on the `.musx` side — spelling from `harm_lev − harm_lev_octave_shift(interval)` —
reconciles the two containers almost completely:

| | identical | octave-only difference | other |
| --- | --- | --- | --- |
| current model | 27,931 | **2,493** | 2 |
| with the fold undone | **30,423** | **1** | 2 |

## 4. What is still unresolved

Reconciling the containers does not by itself say **which frame is the true written pitch**, and
this is why no code changes here.

The obvious external check is where notes land on the staff. It has a validated baseline:
non-transposing staves sit at a median +2 to +3 semitones from the middle line, with only 4–7% more
than an octave off-staff, using the same clefs (plain treble and bass — no transposing staff in the
corpus uses an octave clef).

Against that baseline, four candidate models were tried: the current one, the fold undone, spelling
anchored on the concert key's tonic, and both. **None wins.** The fold-undone model fits intervals
−7, 5 and 7; the current model fits 4 and 8; the concert-anchored model fits 1 and 12.

And the baseline cannot settle it, because a transposing instrument has its own tessitura — a horn
in F genuinely sits low in the treble staff — so "distance from the middle line" is not a fair
comparison for exactly the staves in question.

## What would settle it

A score whose correct written pitches are known independently: a public-domain edition of a
transposing part, entered in Finale and saved in both formats. The corpus cannot supply it, because
every `.musx` here was produced by Finale from the matching `.mus`, so the two are not independent
witnesses.

Until then the reconciliation above is a strong result about the **relationship** between the
containers and a conjecture about the absolute answer.
