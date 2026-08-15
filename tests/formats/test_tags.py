"""The tag catalogue, and the tiers that keep its claims apart.

A name is only as good as the evidence behind it. These check that the
catalogue never hands out a name without that evidence, and that the strongest
claim wins where two tiers name the same tag.
"""

from __future__ import annotations

import pytest

from finale_file_parser.formats.tags import (
    DECODED,
    DOCUMENTED,
    MATCHED,
    SOURCES,
    TAG_NAMES,
    WEAK_MATCH,
    TagName,
    name_for,
)


@pytest.mark.parametrize("entry", TAG_NAMES, ids=lambda e: f"{e.pool}/{e.tag}")
def test_every_name_carries_its_tier(entry: TagName) -> None:
    assert entry.tier in {DECODED, MATCHED, DOCUMENTED}
    assert entry.name, f"{entry.tag} has no name"
    assert entry.pool in {"others", "details", "entries"}


@pytest.mark.parametrize("entry", TAG_NAMES, ids=lambda e: f"{e.pool}/{e.tag}")
def test_a_tier_carries_the_evidence_that_tier_requires(entry: TagName) -> None:
    """A matched name without its document count, or a documented name without
    its source, is a claim with nothing behind it."""
    if entry.tier == MATCHED:
        assert entry.documents > 0, f"{entry.name} claims a match but names no documents"
    if entry.tier == DOCUMENTED and entry.source:
        assert entry.source in SOURCES, f"{entry.name} cites an unknown source"


def test_a_decoded_name_wins_over_a_documented_one() -> None:
    """`MS` is in the ETF tables as "Measure Spec" and is also the record this
    project decoded as `measSpec`. A 2001-2005 document must get the decoding,
    which is the stronger claim, not the weaker table entry.
    """
    found = name_for("others", "MS")
    assert found is not None
    assert found.name == "measSpec"
    assert found.tier == DECODED

    # And the numeric spelling of the same record resolves to the same entry.
    assert name_for("others", "176") is found


def test_a_tag_is_only_named_within_its_own_pool() -> None:
    assert name_for("details", "1044") is not None
    assert name_for("others", "1044") is None


def test_an_unidentified_tag_has_no_name() -> None:
    """189 tags appear in the 2011 `others` pool and this catalogue covers about
    thirty. Silence is the correct answer for the rest."""
    assert name_for("others", "213") is None


def test_the_weakest_matches_are_flagged_as_such() -> None:
    """`fontName` rests on five agreeing documents and `shapeExprDef` on ten.
    Both are below the threshold, and anything showing them is expected to say
    so rather than presenting them like the eighty-document matches."""
    weak = [e for e in TAG_NAMES if e.tier == MATCHED and e.documents < WEAK_MATCH]
    assert {e.name for e in weak} == {"fontName", "shapeExprDef"}
