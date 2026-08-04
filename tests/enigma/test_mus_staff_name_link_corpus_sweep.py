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
from finale_file_parser.enigma.text import plain_text

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
