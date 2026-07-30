"""Finding corpus documents on disk.

One definition, shared, because the alternative is what this module exists to
fix: every sweep spelled its own corpus walk, `rglob("*.mus")` was wrong in six
of them, and each copy failed silently and separately.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

CORPUS = Path(__file__).parent.parent / "corpus"


def corpus_paths(suffix: str) -> list[Path]:
    """Every corpus file with `suffix`, matched **case insensitively**.

    `rglob("*.mus")` is case sensitive on a POSIX path, and 101 of the corpus's
    238 legacy documents are named `.MUS` -- the Windows cohort. Globbing the
    lowercase spelling walked 137 of them and reported success on whatever it
    found, so that cohort sat outside the export audit, and four `.mus`/`.musx`
    oracle pairs sat outside every paired sweep, without one test failing.

    Comparing the suffix rather than pattern-matching the name is the fix, and
    the reason it lives here rather than in each sweep is that six copies of the
    walk is how the bug spread.

    **Not for building `.mus`/`.musx` oracle pairs.** Those pair on bare stem,
    and 401 corpus `.musx` files share only 123 stems, so `{p.stem: p}` keeps
    whichever the walk happened to yield last. This function also *sorts*, and
    swapping an arbitrary order for a sorted one changes which oracle a document
    is checked against -- observed to move one paired sweep from 91 agreeing
    documents to 84, with nothing actually broken. Pairing wants a rule that
    names one document; until it has one, `conftest.stem_pairs` stays on the old
    walk on purpose.
    """
    wanted = suffix.lower()
    return sorted(p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == wanted)


@cache
def _musx_entry_count(path: Path) -> int | None:
    """Entries in a `.musx`, or None if it does not decode."""
    from finale_file_parser.enigma.document import parse_enigma
    from finale_file_parser.enigma.models import CorruptScoreError
    from finale_file_parser.enigma.score import score_xml

    try:
        return len(parse_enigma(score_xml(path)).entries.records)
    except CorruptScoreError:
        return None


@cache
def _mus_entry_count(path: Path) -> int | None:
    """Entries in a `.mus`, or None if it does not decode."""
    from finale_file_parser.enigma.models import CorruptScoreError
    from finale_file_parser.enigma.mus_entries import read_mus_entries

    try:
        return len(read_mus_entries(path))
    except CorruptScoreError:
        return None


def oracle_pairs() -> list[tuple[Path, Path]]:
    """Each `.mus` with the `.musx` holding the same music, in stem order.

    **A shared filename stem is not enough**, and never was: the corpus keeps
    solo parts and full scores under one name, so 9 stems have `.musx` candidates
    that differ by as much as 1 part against 5. Every sweep therefore checks that
    the two hold the same number of entries before comparing them, and that check
    is what has kept the comparisons honest.

    What it could not do is choose. 401 `.musx` files share 123 stems, so
    `{p.stem: p}` kept whichever the directory walk yielded last, and a stem
    whose arbitrary winner failed the entry-count check was dropped **even when a
    sibling would have matched**. Five oracle pairs were being lost that way, and
    which five depended on walk order -- reordering the walk moved one sweep's
    agreement from 91 documents to 84 with nothing broken and nothing to find.

    So the entry count selects rather than merely rejects: candidates are tried
    in sorted order and the first whose entry count matches wins. Deterministic,
    and strictly better than any single guess. A `.mus` no candidate matches has
    no oracle and is absent here, which is the honest answer -- pairing it with a
    document holding different music would be worse than not pairing it.
    """
    musx_by_stem: dict[str, list[Path]] = {}
    for path in corpus_paths(".musx"):
        musx_by_stem.setdefault(path.stem, []).append(path)

    out: list[tuple[Path, Path]] = []
    for mus_path in corpus_paths(".mus"):
        entries = _mus_entry_count(mus_path)
        if entries is None:
            continue
        for candidate in musx_by_stem.get(mus_path.stem, ()):
            if _musx_entry_count(candidate) == entries:
                out.append((mus_path, candidate))
                break
    return sorted(out, key=lambda pair: pair[0].stem)
