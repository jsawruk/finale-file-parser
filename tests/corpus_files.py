"""Finding corpus documents on disk.

One definition, shared, because the alternative is what this module exists to
fix: every sweep spelled its own corpus walk, `rglob("*.mus")` was wrong in six
of them, and each copy failed silently and separately.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

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
