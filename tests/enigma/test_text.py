"""Tests for resolving staff names and file info."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
)
from finale_file_parser.enigma.text import (
    StaffNames,
    file_info,
    plain_text,
    staff_names,
    text_block,
)


def _document(*, others: Sequence[Record] = (), texts: Sequence[Record] = ()) -> EnigmaDocument:
    return EnigmaDocument(
        version="18.0",
        header=Pool(records=()),
        mappings=Pool(records=()),
        options=OptionsPool(records=()),
        others=OthersPool(records=tuple(others)),
        details=DetailsPool(records=()),
        entries=EntriesPool(records=()),
        texts=TextsPool(records=tuple(texts)),
    )


def _text_block(cmper: int, text_id: int) -> Record:
    return Record(
        tag="textBlock", attrs={"cmper": str(cmper)}, text="", fields={"textID": str(text_id)}
    )


def _block_text(number: int, text: str) -> Record:
    return Record(tag="blockText", attrs={"number": str(number)}, text=text, fields={})


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("^fontid(9)^size(12)^nfx(0)Voice", "Voice"),
        ("Flute", "Flute"),
        ("^fontid(9)^title()", ""),
        ("^size(12)Alto ^nfx(0)Sax", "Alto Sax"),
        ("", ""),
    ],
)
def test_plain_text_strips_commands_and_inserts(markup: str, expected: str) -> None:
    """Inserts like `^title()` are commands, not content.

    A block that is only inserts has no literal text of its own, so the empty
    result is the right answer rather than a failure.
    """
    assert plain_text(markup) == expected


def test_text_block_follows_both_hops() -> None:
    """fullName -> textBlock[cmper] -> textID -> blockText[number].

    Going straight from the number to `blockText` resolves nothing: all 24 named
    staves in the sampled corpus fail that way, because the two numbers live in
    different spaces.
    """
    document = _document(
        others=[_text_block(cmper=2, text_id=30)],
        texts=[_block_text(2, "WRONG"), _block_text(30, "^size(12)Voice")],
    )
    assert text_block(document, 2) == "^size(12)Voice"


@pytest.mark.parametrize("missing", ["textBlock", "blockText"])
def test_text_block_returns_none_when_a_hop_is_missing(missing: str) -> None:
    others = [] if missing == "textBlock" else [_text_block(cmper=2, text_id=30)]
    texts = [] if missing == "blockText" else [_block_text(30, "Voice")]
    assert text_block(_document(others=others, texts=texts), 2) is None


def test_staff_names_resolves_full_and_abbreviated() -> None:
    staff = Record(
        tag="staffSpec",
        attrs={"cmper": "1"},
        text="",
        fields={"fullName": "2", "abbrvName": "3"},
    )
    document = _document(
        others=[staff, _text_block(2, 30), _text_block(3, 31)],
        texts=[_block_text(30, "^size(12)Clarinet"), _block_text(31, "Cl.")],
    )
    assert staff_names(document) == {1: StaffNames(full="Clarinet", abbreviated="Cl.")}


def test_unnamed_staves_are_absent_rather_than_blank() -> None:
    """Most staves have no name -- 60 of 84 in the sampled corpus.

    Returning a blank entry would hide the difference between "unnamed" and
    "named blank", and the caller is better placed to pick a fallback.
    """
    staff = Record(tag="staffSpec", attrs={"cmper": "1"}, text="", fields={"staffLines": "5"})
    assert staff_names(_document(others=[staff])) == {}


def test_part_records_are_ignored() -> None:
    """A linked-part staffSpec would otherwise overwrite the score's name."""
    staff = Record(
        tag="staffSpec", attrs={"cmper": "1", "part": "1"}, text="", fields={"fullName": "2"}
    )
    document = _document(others=[staff, _text_block(2, 30)], texts=[_block_text(30, "Part")])
    assert staff_names(document) == {}


def test_file_info_is_keyed_by_type_and_returned_verbatim() -> None:
    """File info is literal text, not markup, so it is not stripped."""
    texts = [
        Record(tag="fileInfo", attrs={"type": "title"}, text="Ode to Joy", fields={}),
        Record(tag="fileInfo", attrs={"type": "composer"}, text="Beethoven", fields={}),
    ]
    assert file_info(_document(texts=texts)) == {
        "title": "Ode to Joy",
        "composer": "Beethoven",
    }


def test_binary_markup_is_stripped_when_decoded_as_cp1252() -> None:
    """The opcode is a byte above 0x7F, and what it decodes *to* depends on the
    encoding. cp1252 maps 0x84, 0x85 and 0x86 to U+201E, U+2026 and U+2020, all
    outside Latin-1 -- so a pattern written for `\u0080-\u00ff` leaves the
    markup in the text. A `.mus` staff name came back with its opcodes attached
    rather than as "Score".
    """
    raw = "^\u2026\x01\x01\x01\n^\u2020\x01\x01\x01\r^\u201e\x01\x01\x01\x01Score"
    assert plain_text(raw) == "Score"


def test_the_latin_1_form_of_the_same_markup_still_strips() -> None:
    """The other decoding of the same bytes, which already worked."""
    assert plain_text("^\x85\x01\x01\x02\x08Voice") == "Voice"


def test_a_caret_in_real_text_survives() -> None:
    """The pattern must stay narrow: five characters of opcode, not any caret."""
    assert plain_text("2^3 and up") == "2^3 and up"
