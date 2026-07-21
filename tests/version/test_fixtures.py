import tomllib
import zipfile
from pathlib import Path
from typing import cast

import pytest
from defusedxml.ElementTree import fromstring

from finale_file_parser import detect_version
from finale_file_parser.version.models import MusDetail

FIXTURES = Path(__file__).parent.parent / "fixtures" / "version"
MANIFEST = FIXTURES / "MANIFEST.toml"

# Complete allowlist: every element tag that legitimately appears in a
# scrubbed fixture's NotationMetadata.xml (the <metadata>/<fileInfo> wrapper
# plus the full <created>/<modified> subtrees). `maint` is optional -- some
# appVersion blocks omit it -- so fixtures are checked as a subset of this
# set, not an exact match, but ANY tag outside this set (a reintroduced
# title, subtitle, composer, arranger, lyricist, copyright, description, or
# any other unanticipated field) fails the test.
EXPECTED_METADATA_TAGS = {
    "metadata",
    "fileInfo",
    "created",
    "modified",
    "year",
    "month",
    "day",
    "modifiedBy",
    "application",
    "platform",
    "appVersion",
    "major",
    "maint",
    "devStatus",
    "build",
    "appRegion",
}


def _entries() -> list[dict[str, str]]:
    with MANIFEST.open("rb") as handle:
        return cast(list[dict[str, str]], tomllib.load(handle)["fixture"])


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["file"])
def test_fixture_detects_as_manifest_declares(entry: dict[str, str]) -> None:
    result = detect_version(FIXTURES / entry["file"])
    assert result.family.value == entry["expected_family"]
    assert result.label == entry["expected_label"]
    assert result.confidence.value == entry["expected_confidence"]


def test_every_fixture_file_has_a_manifest_entry() -> None:
    declared = {e["file"] for e in _entries()}
    on_disk = {p.name for p in FIXTURES.iterdir() if p.name != "MANIFEST.toml"}
    assert declared == on_disk


def test_no_fixture_contains_musical_content() -> None:
    examined = 0
    for path in FIXTURES.glob("*.musx"):
        examined += 1
        assert set(zipfile.ZipFile(path).namelist()) <= {"mimetype", "NotationMetadata.xml"}
    assert examined > 0, "no .musx fixtures were found to examine"


def test_no_fixture_metadata_contains_unexpected_fields() -> None:
    """NotationMetadata.xml carries title/composer/subtitle/arranger/lyricist/
    copyright/description/created/modified in the corpus, none of which
    (besides created/modified) version detection reads.
    build_version_fixtures.py rebuilds the metadata tree from scratch so only
    the allowed structure can appear; this guards against a future
    regeneration silently reintroducing any of it (e.g. if the scrub
    allowlist regresses) by failing on ANY tag not in EXPECTED_METADATA_TAGS,
    not just a fixed handful of known-bad names."""
    examined = 0
    for path in FIXTURES.glob("*.musx"):
        examined += 1
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("NotationMetadata.xml")
        root = fromstring(xml_bytes)
        tags = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
        unexpected = tags - EXPECTED_METADATA_TAGS
        assert not unexpected, f"{path.name} has unexpected metadata tags: {sorted(unexpected)}"
    assert examined > 0, "no .musx fixtures were found to examine"


def test_no_fixture_has_non_empty_modified_by() -> None:
    """modifiedBy can carry a real person's name/initials in the corpus.
    build_version_fixtures.py blanks it (keeping the element, dropping the
    text); this guards against a future regeneration leaking it again."""
    examined = 0
    for path in FIXTURES.glob("*.musx"):
        examined += 1
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("NotationMetadata.xml")
        root = fromstring(xml_bytes)
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == "modifiedBy":
                assert not element.text, f"{path.name} leaks modifiedBy text: {element.text!r}"
    assert examined > 0, "no .musx fixtures were found to examine"


def test_all_five_mus_versions_are_represented() -> None:
    labels = {e["expected_label"] for e in _entries()}
    for year in (2001, 2004, 2005, 2011, 2012):
        assert f"Finale {year}" in labels


def test_mus_fixture_banner_is_pinned_to_its_full_expected_text() -> None:
    """Pin a real fixture's *complete* banner text, not just its parsed year.

    HEADER_SIZE governs how many bytes ever reach mus.parse; if it were ever
    too small, the banner field would come back silently truncated while the
    year (the first four digits) could still happen to parse correctly and
    every other test above would keep passing. Hardcoding the vendor
    copyright string here (Finale's own text, not musical content) is the
    only thing that would catch that.
    """
    result = detect_version(FIXTURES / "mus-2011.bin")
    assert isinstance(result.detail, MusDetail)
    assert result.detail.banner == "Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc."


def test_musx_fixture_labels_are_pinned_independently_of_the_generator() -> None:
    """MANIFEST.toml's expected_label for .musx fixtures is computed by
    build_version_fixtures.py calling detect_version on the fixture it just
    wrote -- comparing test_fixture_detects_as_manifest_declares against the
    manifest is therefore comparing the code against a recording of itself.
    Hardcode the two known-good labels here so a label-formatting regression
    can't silently regenerate an equally-wrong expectation alongside it.
    """
    assert detect_version(FIXTURES / "musx-18-MAC.musx").label == "18 dev (build 3062)"
    assert detect_version(FIXTURES / "musx-18-WIN.musx").label == "18 dev (build 3163)"
