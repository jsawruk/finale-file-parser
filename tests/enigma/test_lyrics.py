"""Unit tests for lyric resolution.

The syllable text and the assignment live apart -- a verse is one hyphenated
blob in the texts pool, an entry detail indexes into it -- so these tests build
both halves and check the join. Most of the attention goes to `syllabic`, which
Enigma does not store: it has to be inferred from the hyphens, and getting it
wrong produces output that looks plausible and sings wrong.
"""

from __future__ import annotations

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
from finale_file_parser.enigma.lyrics import (
    LyricKind,
    Syllabic,
    lyrics_by_entry,
    verse_syllables,
)

EMPTY: tuple[Record, ...] = ()


def document(
    *, verses: dict[int, str] | None = None, details: tuple[Record, ...] = ()
) -> EnigmaDocument:
    texts = tuple(
        Record(tag="verse", attrs={"number": str(number)}, text=text, fields={})
        for number, text in (verses or {}).items()
    )
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=EMPTY),
        details=DetailsPool(records=details),
        entries=EntriesPool(records=EMPTY),
        texts=TextsPool(records=texts),
    )


def assignment(entnum: int, number: int, syll: int, *, inci: int = 0, wext: bool = False) -> Record:
    fields: dict[str, str] = {"lyricNumber": str(number), "syll": str(syll)}
    if wext:
        fields["wext"] = ""
    return Record(
        tag="lyrDataVerse",
        attrs={"entnum": str(entnum), "inci": str(inci)},
        text="",
        fields=fields,
    )


def test_a_verse_splits_into_syllables() -> None:
    doc = document(verses={1: "An-gels we have heard on high"})
    assert verse_syllables(doc, LyricKind.VERSE, 1) == (
        "An",
        "gels",
        "we",
        "have",
        "heard",
        "on",
        "high",
    )


def test_markup_is_stripped_before_splitting() -> None:
    doc = document(verses={1: "^fontid(9)^size(13)O ho-ly night!"})
    assert verse_syllables(doc, LyricKind.VERSE, 1) == ("O", "ho", "ly", "night!")


@pytest.mark.parametrize(
    ("index", "text", "syllabic"),
    [
        (1, "O", Syllabic.SINGLE),
        (2, "ho", Syllabic.BEGIN),
        (3, "ly", Syllabic.END),
        (4, "night!", Syllabic.SINGLE),
    ],
)
def test_syllabic_comes_from_the_hyphens(index: int, text: str, syllabic: Syllabic) -> None:
    """Enigma stores only hyphens; MusicXML needs begin/middle/end/single."""
    doc = document(verses={1: "O ho-ly night!"}, details=(assignment(7, 1, index),))
    lyric = lyrics_by_entry(doc)[7][0]
    assert (lyric.text, lyric.syllabic) == (text, syllabic)


def test_a_three_syllable_word_has_a_middle() -> None:
    doc = document(
        verses={1: "glo-ri-a"},
        details=(assignment(1, 1, 1), assignment(2, 1, 2), assignment(3, 1, 3)),
    )
    found = lyrics_by_entry(doc)
    assert [found[n][0].syllabic for n in (1, 2, 3)] == [
        Syllabic.BEGIN,
        Syllabic.MIDDLE,
        Syllabic.END,
    ]


def test_a_trailing_hyphen_marks_continuation_without_adding_a_syllable() -> None:
    """ "shin-" splits to ("shin", ""); the empty tail is the continuation mark,
    not a syllable, and counting it would shift every later index by one."""
    doc = document(verses={1: "shin- ing"})
    assert verse_syllables(doc, LyricKind.VERSE, 1) == ("shin", "ing")


def test_a_word_extension_is_carried_through() -> None:
    doc = document(verses={1: "ah"}, details=(assignment(4, 1, 1, wext=True),))
    assert lyrics_by_entry(doc)[4][0].extend is True


def test_several_verses_land_on_one_entry() -> None:
    doc = document(
        verses={1: "one", 2: "two"},
        details=(assignment(9, 1, 1), assignment(9, 2, 1, inci=1)),
    )
    assert {(item.number, item.text) for item in lyrics_by_entry(doc)[9]} == {
        (1, "one"),
        (2, "two"),
    }


def test_a_syllable_index_past_the_end_is_dropped() -> None:
    """A verse shortened after the notes were entered leaves the index
    dangling. Dropping beats inventing a syllable or raising."""
    doc = document(verses={1: "one two"}, details=(assignment(3, 1, 9),))
    assert lyrics_by_entry(doc) == {}


def test_a_detail_without_an_assignment_is_ignored() -> None:
    """Positioning-only lyric details are real in the corpus."""
    positioning = Record(
        tag="lyrDataVerse", attrs={"entnum": "5", "inci": "0"}, text="", fields={"horzOff": "12"}
    )
    doc = document(verses={1: "one"}, details=(positioning,))
    assert lyrics_by_entry(doc) == {}


def test_an_assignment_with_no_verse_text_is_dropped() -> None:
    doc = document(details=(assignment(2, 1, 1),))
    assert lyrics_by_entry(doc) == {}
