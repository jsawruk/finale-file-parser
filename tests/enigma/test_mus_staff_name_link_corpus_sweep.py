"""What is established about the `.mus` staff-name link, pinned.

`docs/formats/mus-staff-names.md` records that a `.mus` names its staves and that
one link is missing: how `staffSpec` +30's id reaches a text block. The reason the
arithmetic route was written off there was **wrong**, and it was wrong in a way
worth guarding against a second time: it rested on a single document, because the
harness was pairing each `.mus` with a `.musx` chosen by directory-walk order and
the documents that could test it were being dropped.

Five can test it now, and all five agree. These assertions hold the facts that
survived re-derivation, so the next attempt starts from them rather than from the
retracted conclusion.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import re

import pytest
from corpus_files import CORPUS, oracle_pairs

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.mus_others import TAG_STAFF_SPEC, read_mus_others
from finale_file_parser.enigma.mus_payload import read_mus_streams
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.text import plain_text, staff_names
from finale_file_parser.errors import FinaleFileError

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

NAME_ID = 30
"""`staffSpec` offset holding the id that selects a staff's full name."""

TEXT_STREAM = 3
_BLOCK = re.compile(rb"\^block\((\d+)\)(.*?)\^end", re.S)

ANCHORED_DOCUMENTS = 5
"""Documents that can test the id-to-block relation at all.

A document tests it only if two or more of its staves carry a name id, which is
what makes the relation falsifiable rather than vacuous. **This number was 1** when
`mus-staff-names.md` concluded the relation "is not arithmetic" -- not because the
corpus lacked the documents, but because oracle pairing discarded them. It is the
count to watch: if it falls, the harness has started hiding evidence again.
"""

ID_SPACES_AGREE = 25
TOTAL_NAMED_STAVES = 83
"""How often the two containers use the *same* id for a staff's name: 25 of 83.

They are separate id spaces. Where a `.musx` was re-saved it renumbered its text
blocks, so it says `fullName` 2 where the `.mus` says 93. Pinned because a figure
in `mus-staff-names.md` -- "the delta ranges 63-87 across documents" -- was
computed across both spaces at once and therefore measured nothing. A cross-
container delta is only meaningful for these 25.
"""


def _blocks(path: object) -> dict[int, str]:
    streams = read_mus_streams(path)  # type: ignore[arg-type]
    if len(streams) <= TEXT_STREAM:
        return {}
    out: dict[int, str] = {}
    for match in _BLOCK.finditer(streams[TEXT_STREAM]):
        try:
            body = match.group(2).decode("cp1252")
        except UnicodeDecodeError:
            continue
        out[int(match.group(1))] = plain_text(body).strip()
    return out


def _name_ids(path: object) -> dict[int, int]:
    return {
        record.cmper: int.from_bytes(record.payload[NAME_ID : NAME_ID + 2], "little")
        for record in read_mus_others(path)  # type: ignore[arg-type]
        if record.tag == TAG_STAFF_SPEC and record.part == 0 and len(record.payload) >= NAME_ID + 2
    }


def _anchors() -> list[tuple[dict[int, int], dict[int, str]]]:
    """Per document: name id -> block number, for staves whose id both containers
    agree on, plus that document's blocks."""
    out = []
    for mus_path, musx_path in oracle_pairs():
        try:
            musx = parse_enigma(score_xml(musx_path))
            ids = _name_ids(mus_path)
        except CorruptScoreError:
            continue
        text_id: dict[str, int] = {}
        for block in musx.others.of_tag("textBlock"):
            value = block.fields.get("textID")
            if "part" not in block.attrs and isinstance(value, str):
                text_id[block.attrs["cmper"]] = int(value)
        found: dict[int, int] = {}
        for record in musx.others.of_tag("staffSpec"):
            if "part" in record.attrs:
                continue
            name_id = ids.get(int(record.attrs["cmper"]))
            if name_id and str(name_id) in text_id:
                found[name_id] = text_id[str(name_id)]
        if found:
            out.append((found, _blocks(mus_path)))
    return out


def test_the_two_containers_mostly_do_not_share_a_name_id_space() -> None:
    """See `ID_SPACES_AGREE`: the reason a cross-container delta measured nothing."""
    agree = total = 0
    for mus_path, musx_path in oracle_pairs():
        try:
            musx = parse_enigma(score_xml(musx_path))
            ids = _name_ids(mus_path)
        except CorruptScoreError:
            continue
        for record in musx.others.of_tag("staffSpec"):
            if "part" in record.attrs:
                continue
            full = record.fields.get("fullName")
            got = ids.get(int(record.attrs["cmper"]))
            if not isinstance(full, str) or not full or not got:
                continue
            total += 1
            agree += got == int(full)
    assert total == TOTAL_NAMED_STAVES
    assert agree == ID_SPACES_AGREE


def test_the_id_to_block_delta_is_constant_within_a_document() -> None:
    """The retracted claim, re-derived.

    `mus-staff-names.md` said the relation is not arithmetic because the one
    document resolving two names had a varying delta. Five documents resolve two
    or three, and the delta is constant in every one -- so the arithmetic route is
    open, and what is missing is only the per-document base.
    """
    testable = constant = 0
    for anchors, _ in _anchors():
        if len(anchors) < 2:
            continue
        testable += 1
        constant += len({name_id - block for name_id, block in anchors.items()}) == 1
    assert testable == ANCHORED_DOCUMENTS
    assert constant == ANCHORED_DOCUMENTS


def test_every_anchored_block_holds_a_name() -> None:
    """That the blocks named are the *right* ones, not merely arithmetic.

    Each resolved block carries a real instrument or voice name -- and in the
    documents with three, three different ones. A relation that happened to fit
    the numbers would land on empty or duplicate blocks.
    """
    resolved = 0
    for anchors, blocks in _anchors():
        texts = [blocks.get(block, "") for block in anchors.values()]
        assert all(texts), "an anchored block holds no text"
        if len(anchors) >= 2:
            assert len(set(texts)) == len(texts), "two staves resolved to one name"
        resolved += len(texts)
    assert resolved == ID_SPACES_AGREE


def test_ids_and_blocks_advance_in_lockstep() -> None:
    """**Why** the delta is constant, rather than just that it is.

    A staff has a full name and an abbreviated one, at `staffSpec` +30 and +32,
    and they are consecutive ids. The blocks they select are consecutive too, so
    each named staff consumes two of each and the two sequences advance together
    -- which is what pins `id - block` within a document. Observing the
    constancy came first; this is the reason for it, and it says the remaining
    unknown is only where the two sequences *start*.
    """
    checked = 0
    for anchors, _ in _anchors():
        if len(anchors) < 2:
            continue
        checked += 1
        ordered = sorted(anchors.items())
        id_steps = {b[0] - a[0] for a, b in zip(ordered, ordered[1:], strict=False)}
        block_steps = {b[1] - a[1] for a, b in zip(ordered, ordered[1:], strict=False)}
        assert id_steps == {2}, "name ids do not advance by two"
        assert block_steps == {2}, "text blocks do not advance by two"
    assert checked == ANCHORED_DOCUMENTS


DISTINCT_NAME_IDS = 9
INDEPENDENT_DOCUMENTS_FOR_ID_TWO = 10
"""Documents mapping name id 2 to text block 30, all of them different music.

Ten distinct pieces with ten distinct entry counts. This is the evidence that the
id-to-block mapping does not vary by document, and it is worth pinning the
*independence* rather than the count: three of the other repeats are variants of
one arrangement, and reading those as corroboration is how this corpus has misled
this project before.
"""


def test_no_name_id_maps_to_two_different_blocks() -> None:
    """**The mapping is document-independent**, and this is what says so.

    `mus-staff-names.md` long described the unknown as a *per-document base*.
    That was wrong: the delta appeared to vary between documents only because
    different documents use different ids. Across every anchor the corpus yields,
    an id selects one block and always the same one -- so what is missing is a
    fixed table, not a per-document computation.
    """
    blocks_for: dict[int, set[int]] = {}
    for anchors, _ in _anchors():
        for name_id, block in anchors.items():
            blocks_for.setdefault(name_id, set()).add(block)
    assert len(blocks_for) == DISTINCT_NAME_IDS
    for name_id, blocks in blocks_for.items():
        assert len(blocks) == 1, f"id {name_id} selects more than one block: {sorted(blocks)}"


def test_one_id_is_evidenced_by_ten_independent_documents() -> None:
    """Guards the claim above against the near-duplicate trap.

    Entry count stands in for "different music" here: it is the same filter the
    oracle pairing uses, and ten distinct counts cannot be one arrangement
    counted ten times.
    """
    from finale_file_parser.enigma.mus_entries import read_mus_entries

    sizes: set[int] = set()
    for mus_path, musx_path in oracle_pairs():
        try:
            musx = parse_enigma(score_xml(musx_path))
            ids = _name_ids(mus_path)
        except CorruptScoreError:
            continue
        text_id: dict[str, int] = {}
        for block in musx.others.of_tag("textBlock"):
            value = block.fields.get("textID")
            if "part" not in block.attrs and isinstance(value, str):
                text_id[block.attrs["cmper"]] = int(value)
        if any(name_id == 2 and text_id.get("2") == 30 for name_id in ids.values()):
            sizes.add(len(read_mus_entries(mus_path)))
    assert len(sizes) == INDEPENDENT_DOCUMENTS_FOR_ID_TWO


ANCHOR_VALIDITY = {"valid": 25, "block absent": 116, "wrong text": 3}
"""Why only 25 of 144 candidate anchors can test the id-to-block relation.

A candidate is a `.mus` name id paired with the block number the `.musx` reaches
through `staffSpec.fullName -> textBlock -> textID`. There are 144 of those, and
it is tempting to treat them all as evidence -- I did, and briefly concluded from
them that the id-to-block map is per-document after all. It is not; the anchors
were junk.

**A candidate is only an anchor if the block exists in the `.mus` and holds that
staff's name.** Measured:

* **116 name a block absent from the `.mus` stream.** The `.musx` was re-saved
  and renumbered its text blocks, so its `textID` points at a block this `.mus`
  does not have. Of those 116, the name text appears in *no* block at all in 65
  cases -- the `.mus` genuinely does not carry that name.
* **3 land on a block that exists but holds different text.**
* **25 are valid**, which is the figure §3d rests on and the same number reached
  by a completely different route.

Pinned because inflating this set is the specific mistake available here, and it
produces a confident wrong answer rather than a visible failure.
"""

RECOVERY_DELTAS = 10
"""Distinct `textID - block` deltas among candidates recovered by name text.

The obvious way to rescue the 116 is to find the staff's name among the blocks and
take the difference as a renumbering offset. 47 resolve to exactly one block that
way, and their deltas are 1, 2, 21, 16, 20, 22, 17, 3, 5, 23 -- ten values with no
rule, and only 37 of 42 documents are even self-consistent. Worse, the method is
the palette trap: a staff called `Flute` matches the template's `Flute` block
rather than its own. Recorded so the route is not tried a fourth time.
"""

LOOKUP_BEST = 0.20
"""Best score for any record acting as the id-to-block lookup: 19.4%.

Searched two ways over the 144 candidates, both failing:

* a record keyed at the name id holding the block at any even offset -- best
  tag 183 at `+0`, 28 of 144;
* the `(id, block)` pair written adjacently as two `uint16`s **anywhere** in any
  `others` payload, any `details` payload, or any stream -- absent in 129 of 144,
  and the 15 hits are spread across four unrelated tags.

The pair is not stored. That is now a measured negative rather than a failed
search.
"""


def test_only_a_quarter_of_the_candidate_anchors_are_real() -> None:
    """The validity criterion, asserted rather than assumed.

    See `ANCHOR_VALIDITY`. This is the guard against the mistake of counting all
    144: it fails if the valid set is ever reported as larger than it is.
    """
    valid = 0
    absent = 0
    wrong = 0
    for mus_path, musx_path in oracle_pairs():
        try:
            blocks = _blocks(mus_path)
            musx = parse_enigma(score_xml(musx_path))
        except (CorruptScoreError, FinaleFileError, OSError, ValueError):
            continue
        if not blocks:
            continue
        text_id: dict[str, int] = {}
        for text_block in musx.others.of_tag("textBlock"):
            value = text_block.fields.get("textID")
            if "part" not in text_block.attrs and isinstance(value, str) and value.isdigit():
                text_id[str(text_block.attrs["cmper"])] = int(value)
        spec = {
            int(str(r.attrs["cmper"])): r
            for r in musx.others.records
            if r.tag == "staffSpec"
            and "part" not in r.attrs
            and str(r.attrs.get("cmper", "")).isdigit()
        }
        names = staff_names(musx)
        for staff, ids in _name_id_pairs(mus_path).items():
            reference = spec.get(staff)
            if reference is None or staff not in names:
                continue
            for name_id, field, wanted in (
                (ids[0], "fullName", names[staff].full),
                (ids[1], "abbrvName", names[staff].abbreviated),
            ):
                value = reference.fields.get(field)
                block = text_id.get(str(value)) if value is not None else None
                if not name_id or block is None or not wanted:
                    continue
                if block not in blocks:
                    absent += 1
                elif _same(blocks[block], wanted):
                    valid += 1
                else:
                    wrong += 1
    assert valid == ANCHOR_VALIDITY["valid"], f"{valid} valid anchors, not 25"
    assert absent == ANCHOR_VALIDITY["block absent"]
    assert wrong == ANCHOR_VALIDITY["wrong text"]
    assert valid + absent + wrong == 144


def _name_id_pairs(path: object) -> dict[int, tuple[int, int]]:
    """staff -> (full name id, abbreviated name id), from `staffSpec` +30 and +32.

    Distinct from `_name_ids`, which returns the full-name id alone and is what
    the older tests here read.
    """
    out: dict[int, tuple[int, int]] = {}
    for record in read_mus_others(path):  # type: ignore[arg-type]
        if record.tag != TAG_STAFF_SPEC or record.part or len(record.payload) < 34:
            continue
        out[record.cmper] = (
            int.from_bytes(record.payload[30:32], "little"),
            int.from_bytes(record.payload[32:34], "little"),
        )
    return out


def _same(found: str, wanted: str) -> bool:
    return (
        re.sub(r"\s+", " ", found).strip().casefold()
        == re.sub(r"\s+", " ", wanted).strip().casefold()
    )
