"""Resolve a document's lyrics: which syllable each entry sings.

Enigma splits a lyric in two. The **text** is one blob per verse in the `texts`
pool, syllabified with hyphens (`An-gels we have heard on high`). The
**assignment** is an entry detail carrying a verse number and a 1-based index
into that verse's syllables. Nothing stores the syllables themselves, so the
join is: tokenise the verse, then index it.

    lyrDataVerse(entnum) -> lyricNumber, syll  ->  verse(number) syllable syll

Verified against the corpus: the syllables of "O Holy Night" verse 1 land on
consecutive entries in playing order, exactly as sung.

**`syllabic` is derived, not stored.** MusicXML needs to know whether a syllable
begins, continues or ends a word, and Enigma records only the hyphens. A hyphen
after a syllable means the word continues; one before means it was continued
into. That derivation is the part of this module most likely to be subtly wrong,
so it is what the tests concentrate on.

Both containers reach here through the same `EnigmaDocument`, so this module
knows nothing about either.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from finale_file_parser.enigma.document import EnigmaDocument, Record, field_int
from finale_file_parser.enigma.text import plain_text

__all__ = ["Lyric", "LyricKind", "Syllabic", "lyrics_by_entry", "verse_syllables"]

_LYRIC_DETAILS = {
    "lyrDataVerse": "verse",
    "lyrDataChorus": "chorus",
    "lyrDataSection": "section",
}
"""Each entry-detail tag and the texts-pool tag it indexes into.

`lyrDataChorus` is included for symmetry with Enigma's own vocabulary; no corpus
document uses one, so that path is exercised only by unit tests.
"""

_HYPHEN = "-"


class LyricKind(Enum):
    """Which of Enigma's three parallel lyric tracks a syllable belongs to."""

    VERSE = "verse"
    CHORUS = "chorus"
    SECTION = "section"


class Syllabic(Enum):
    """Where a syllable sits within its word, in MusicXML's vocabulary."""

    SINGLE = "single"
    BEGIN = "begin"
    MIDDLE = "middle"
    END = "end"


@dataclass(frozen=True)
class Lyric:
    """One syllable sung by one entry, in one verse."""

    kind: LyricKind
    number: int
    """Verse number, as Enigma's `lyricNumber`. MusicXML's `<lyric number=...>`."""

    text: str
    syllabic: Syllabic
    extend: bool
    """A word extension -- the line drawn under a held syllable (a melisma)."""


def verse_syllables(document: EnigmaDocument, kind: LyricKind, number: int) -> tuple[str, ...]:
    """The syllables of one verse, in order, ready to index by `syll`.

    Words split on whitespace, then each word on hyphens. An empty result means
    the verse is absent or holds no text.
    """
    return tuple(text for text, _ in _tokenise(document, kind, number))


def lyrics_by_entry(document: EnigmaDocument) -> dict[int, tuple[Lyric, ...]]:
    """Every syllable assignment, grouped by the entry that sings it.

    An entry can carry several: one per verse, and a document may use verse,
    chorus and section tracks at once. Assignments whose syllable index falls
    outside its verse are dropped rather than guessed at -- a verse can be
    shortened after the notes are entered, which leaves the index dangling.
    """
    cache: dict[tuple[LyricKind, int], tuple[tuple[str, bool], ...]] = {}
    out: dict[int, list[Lyric]] = {}
    for tag, kind_name in _LYRIC_DETAILS.items():
        kind = LyricKind(kind_name)
        for record in document.details.of_tag(tag):
            resolved = _resolve(document, record, kind, cache)
            if resolved is None:
                continue
            entnum, lyric = resolved
            out.setdefault(entnum, []).append(lyric)
    return {entnum: tuple(items) for entnum, items in out.items()}


def _resolve(
    document: EnigmaDocument,
    record: Record,
    kind: LyricKind,
    cache: dict[tuple[LyricKind, int], tuple[tuple[str, bool], ...]],
) -> tuple[int, Lyric] | None:
    number = field_int(record.fields.get("lyricNumber"))
    index = field_int(record.fields.get("syll"))
    entnum = field_int(record.attrs.get("entnum"))
    if number is None or index is None or entnum is None:
        # A detail carrying only positioning: real in the corpus, and not a
        # syllable assignment.
        return None
    key = (kind, number)
    if key not in cache:
        cache[key] = _tokenise(document, kind, number)
    syllables = cache[key]
    if not 1 <= index <= len(syllables):
        return None
    text, continues = syllables[index - 1]
    previous_continues = index >= 2 and syllables[index - 2][1]
    return entnum, Lyric(
        kind=kind,
        number=number,
        text=text,
        syllabic=_syllabic(previous_continues, continues),
        extend="wext" in record.fields,
    )


def _syllabic(after_hyphen: bool, before_hyphen: bool) -> Syllabic:
    if after_hyphen and before_hyphen:
        return Syllabic.MIDDLE
    if after_hyphen:
        return Syllabic.END
    if before_hyphen:
        return Syllabic.BEGIN
    return Syllabic.SINGLE


def _tokenise(
    document: EnigmaDocument, kind: LyricKind, number: int
) -> tuple[tuple[str, bool], ...]:
    """(syllable, does a hyphen follow) for one verse, in order.

    The hyphen is the only thing marking a word as continuing, so it is carried
    alongside each syllable rather than left in the text.
    """
    record = document.texts.get(kind.value, number)
    if record is None:
        return ()
    out: list[tuple[str, bool]] = []
    for word in plain_text(record.text).split():
        parts = word.split(_HYPHEN)
        # A trailing hyphen ("shin-") splits to ("shin", ""); the empty tail is
        # the mark that the word continues, not a syllable of its own.
        if parts and not parts[-1]:
            parts = parts[:-1]
            trailing = True
        else:
            trailing = False
        for position, part in enumerate(parts):
            last = position == len(parts) - 1
            out.append((part, trailing if last else True))
    return tuple(out)
