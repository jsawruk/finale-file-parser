# Entry facts in the report: design

**Goal:** select an entry in the report's Records tree and see two things the
document does not state directly — what points at that entry, and what it
decodes to.

**Status:** design approved 2026-08-19. Implementation not started.

## The problem

The reader walks one direction. `gfhold` names a frame, `frameSpec` names an
entry range, and an entry sounds at a (staff, measure, layer); details such as
`articAssign` and `lyrDataVerse` hang off an `entnum`. Every consumer follows
that direction, and `locate_entries` is the code that does it.

Reading a report, the question is the other one. A note is wrong, or a record
looks odd, and what a reader wants is: *what put this entry here, what else
refers to it, and what does it actually decode to?* Nothing answers that today.
The Records tree shows a record's own bytes and fields and stops there.

The second half is worse than missing. An entry's fields include `harmLev` and
`harmAlt`, which are a diatonic step count and an alteration **relative to the
key in force**. Read alone they do not name a pitch, so the tree shows numbers
that cannot be checked against the engraving above them without doing the
decode by hand.

## Scope

**Direct pointers only.** A reference counts when it names this entry: the
placement chain that reaches it, and the details records that hold its
`entnum`. Records that merely apply to the same measure — `measSpec`,
`measExprAssign`, the clef in force — are deliberately excluded. They are
useful context, but calling them "pointers" would turn *points at this entry*
into *is near this entry*, and a wrong dynamic would then read as though it
were attached to this note.

**Both containers, one input.** `_finish` already receives an `EnigmaDocument`,
and `.mus` and `.musx` both produce one, so the walk has a single input and no
container-specific paths. **Depends on PR #122.** `.mus` entry records reach the
Records tree only once the entries pool -- which the container labels 17 -- is
collected there; until that merges, the `.mus` half of this feature has nothing
to click. The `.musx` half is unaffected.

**Not in this design:** clicking a note in the engraving. Verovio's SVG carries
its own element ids and nothing maps them back to entry numbers; that bridge is
a separate piece of work, and everything here is reachable from the tree
without it.

## What is built

A new depth on `Inspection`, keyed by entry number:

    entry_index: dict[str, EntryFacts]

    EntryFacts
      placements:  tuple[Placement, ...]    one usually; a mirror has two
      named_by:    tuple[Reference, ...]    details holding this entnum
      decode:      EntryDecode | None
      unresolved:  tuple[str, ...]          which links failed, in words

    Placement   staff, measure, layer, gfhold_key, frame   (any may be None)
    Reference   pool, tag, key
    EntryDecode duration_edu, duration_name, notes
                  Note  harm_lev, harm_alt, spelled | None, why_not | None

`unresolved` is prose rather than an enumeration. It is read by someone staring
at a file that does not work, and the failure modes are open-ended enough that a
code would either lose information or grow one member per message.

## The tolerant walk

The walk mirrors `locate_entries` and **never raises**. Where that function
refuses a document, this one records which link broke and keeps going:

    entry 9
      placed by  gfhold (staff 1, measure 3) layer 1
                 frameSpec 12 — not found
      named by   details / articAssign (9, 0)
      unresolved frameSpec 12 not found

This is a second walker of a join the reader already walks, and that is a real
cost, accepted deliberately: the report exists for documents that do not work,
and `locate_entries` raises `MalformedScoreError` on exactly those. A report
that loses its back-references precisely when a file is broken would be missing
the case it was built for.

`named_by` needs only the `entnum`, so it resolves independently and survives a
broken chain entirely.

**The drift is contained by a sweep, not by hope.** For every corpus document
where `locate_entries` succeeds, the walk must produce exactly its placements —
same entnums, same (staff, measure, layer), same count. Where `locate_entries`
raises there is no oracle, and the sweep asserts only that the walk returns and
does not raise.

## The decode

`read_entry` gives the duration and each note's raw values, and depends on
nothing but the entry, so it is always available.

Spelling calls `spell_note` with the effective key (`effective_keys`) and the
staff transposition (`read_transposition`). Both come from the placement, so
both can be missing. When either is, `spelled` is `None` and `why_not` names the
absent input.

Raw and spelled are shown together, never one without the other:

    entry 9  dura 1024 -> quarter
      note 1  harmLev 4  harmAlt 0  ->  F#4
      note 2  harmLev 0  harmAlt 0  ->  D4
      with key 2 (D major), staff transposition 0

A wrong pitch then says immediately whether the fault is in the stored number or
in the key applied to it. There is no C-major default: a missing key produces no
spelling, not a guess.

**The report must not develop its own opinion of a pitch.** A test asserts that
the spelled pitch equals what `build_score` puts in the IR for the same entry.

## Where it appears

In the existing record detail pane, under the fields already shown, as two
blocks: *Decodes as* and *Pointed to by*. A `Pointed to by` row is clickable and
selects that record, so the reverse join is navigable rather than only readable.

The JavaScript renders `entry_index[entnum]` and does nothing else — no
decoding, no joining. That line is what keeps a second decoder out of the page,
and it is why the index is built in Python even though the pools it draws on are
already embedded.

## Cost

Measured over 16 sampled `.musx` documents: 126 entries at the minimum, 352 at
the median, 1,080 at the largest. At roughly 160 bytes per entry that is 55 KB
for a median document and 169 KB for the largest, against reports that already
run from 617 KB to 7.6 MB. The index is built for every entry because the report
is a static file with no server: nothing can be computed after it is written.

The agreement sweep walks the corpus and so joins the 35 corpus sweeps in
`make check-full`. Its cost is to be measured and reported rather than assumed.

## Testing

**Unit, no corpus.** Synthetic documents for each failure mode: a clean entry, a
missing `frameSpec`, a `gfhold` naming an absent frame, an entry no frame
reaches, an entry with no key in force. Each asserts both what resolved and what
`unresolved` says. The tolerant behaviour is pinned here, where CI can run it —
`corpus/` is gitignored and CI never has one.

**Agreement with `locate_entries`,** over the corpus, as above.

**Agreement with the IR,** for the spelled pitch, as above.

## Module

The walk and the decode go in `report/entry_facts.py`, with `report/model.py`
calling into it. `model.py` is already about 880 lines; this would add roughly
150 more to the largest file in the package, and the new logic is separately
testable.
