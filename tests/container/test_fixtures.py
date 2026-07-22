import tomllib
import zipfile
from pathlib import Path
from typing import cast

import build_container_fixtures
import pytest

from finale_file_parser.container.musx import open_musx

FIXTURES = Path(__file__).parent.parent / "fixtures" / "container"
PROFILES = FIXTURES / "PROFILES.toml"
FILLER = b"FINALE-FIXTURE-SYNTHETIC-PAYLOAD-DO-NOT-INTERPRET-"
MIMETYPE_VALUE = b"application/vnd.makemusic.notation"
CORPUS = Path(__file__).parent.parent.parent / "corpus"


def _profiles() -> list[dict[str, object]]:
    with PROFILES.open("rb") as handle:
        data = tomllib.load(handle)
    return cast(list[dict[str, object]], data["profile"])


def test_all_twenty_two_profiles_are_present() -> None:
    assert len(_profiles()) == 22
    on_disk = {p.name for p in FIXTURES.glob("*.musx")}
    assert on_disk == {str(profile["file"]) for profile in _profiles()}


def test_every_profile_declares_a_source_count() -> None:
    for profile in _profiles():
        source_count = profile["source_count"]
        assert isinstance(source_count, int)
        assert source_count >= 1


def test_source_counts_sum_to_the_full_corpus() -> None:
    # The 22 name-shape groups partition every archive that was harvested;
    # their source_count values must add back up to that same total.
    total = 0
    for profile in _profiles():
        source_count = profile["source_count"]
        assert isinstance(source_count, int)
        total += source_count
    assert total == 401


@pytest.mark.parametrize("profile", _profiles(), ids=lambda p: str(p["file"]))
def test_fixture_enumerates_exactly_its_declared_structure(profile: dict[str, object]) -> None:
    members = profile["members"]
    assert isinstance(members, list)
    with open_musx(FIXTURES / str(profile["file"])) as container:
        actual = [(e.name, e.size, e.compress_type) for e in container.entries]
    expected = [(m["name"], m["size"], m["compress_type"]) for m in members]
    assert actual == expected


@pytest.mark.parametrize("profile", _profiles(), ids=lambda p: str(p["file"]))
def test_fixture_yields_a_score_stream_of_declared_length(profile: dict[str, object]) -> None:
    members = profile["members"]
    assert isinstance(members, list)
    declared = next(m["size"] for m in members if m["name"] == "score.dat")
    with open_musx(FIXTURES / str(profile["file"])) as container:
        assert len(container.score_stream()) == declared


def test_mimetype_is_first_and_stored_in_every_fixture() -> None:
    fixtures = sorted(FIXTURES.glob("*.musx"))
    assert fixtures, "no fixtures found"
    for path in fixtures:
        with open_musx(path) as container:
            first = container.entries[0]
        assert first.name == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED


def test_exactly_two_profiles_carry_method_varied() -> None:
    # Corrected profile format: grouping by ordered member names means some
    # groups mix compression methods for the same member position across
    # their source archives. That fact is recorded per profile, not silently
    # resolved away, via a `method_varied = true` marker.
    varied = [p for p in _profiles() if p.get("method_varied") is True]
    assert len(varied) == 2
    for profile in _profiles():
        if profile.get("method_varied") is not True:
            assert "method_varied" not in profile


def test_no_fixture_contains_a_non_synthetic_payload() -> None:
    # Direct inspection of the committed bytes, independent of the generator:
    # every member's payload must be either the synthetic filler pattern, or
    # -- for `mimetype` only -- the fixed protocol constant the reader
    # requires, which is a literal in our own source (container/musx.py), not
    # a byte ever read out of a corpus archive.
    fixtures = sorted(FIXTURES.glob("*.musx"))
    assert fixtures, "no fixtures found"
    for path in fixtures:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                data = archive.read(name)
                if not data:
                    continue
                if name == "mimetype":
                    expected = (MIMETYPE_VALUE * (len(data) // len(MIMETYPE_VALUE) + 1))[
                        : len(data)
                    ]
                else:
                    expected = (FILLER * (len(data) // len(FILLER) + 1))[: len(data)]
                assert data == expected, f"{path.name}:{name} is not synthetic filler"


def test_allowlist_refuses_a_member_name_with_a_trailing_newline(tmp_path: Path) -> None:
    # `re.match(..., "$")` matches BEFORE a trailing newline, so a member
    # literally named "score.dat\n" would sail through a `.match`-based
    # allowlist. `_harvest` must use `fullmatch` and refuse it outright: this
    # allowlist is the generator's last line of defence against a member
    # named after a musical work riding along into a committed fixture.
    assert build_container_fixtures.ALLOWED_NAME.fullmatch("score.dat") is not None
    assert build_container_fixtures.ALLOWED_NAME.fullmatch("score.dat\n") is None

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    with zipfile.ZipFile(corpus / "smuggled.musx", "w") as archive:
        archive.writestr("mimetype", MIMETYPE_VALUE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat\n", b"x")

    original_corpus = build_container_fixtures.CORPUS
    build_container_fixtures.CORPUS = corpus
    try:
        with pytest.raises(SystemExit):
            build_container_fixtures._harvest()
    finally:
        build_container_fixtures.CORPUS = original_corpus


# These two totals come from a one-time survey of the corpus (401 archives
# folding into the 22 committed profiles; see
# docs/superpowers/specs/2026-07-21-musx-container-design.md). They are NOT
# derived from whatever the generator emits today: if a future regeneration
# changes either number, that is a signal to re-derive these constants from
# the corpus and confirm the change is expected, not to edit them to match
# the new output.
EXPECTED_TOTAL_DECLARED_SIZE = 2939506
EXPECTED_TOTAL_MEMBER_COUNT = 155


def test_total_declared_size_and_member_count_are_pinned() -> None:
    total_size = 0
    total_members = 0
    for profile in _profiles():
        members = profile["members"]
        assert isinstance(members, list)
        for member in members:
            assert isinstance(member["size"], int)
            total_size += member["size"]
            total_members += 1
    assert total_size == EXPECTED_TOTAL_DECLARED_SIZE
    assert total_members == EXPECTED_TOTAL_MEMBER_COUNT


@pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")
def test_profiles_toml_matches_a_fresh_derivation_from_the_corpus() -> None:
    # Independent of the fixtures on disk: re-runs the generator's own
    # harvesting/grouping logic (imported, not reimplemented, so this can't
    # drift from the real rule) directly against corpus/, and checks the
    # committed PROFILES.toml still matches. This is the test that catches a
    # stale commit after the corpus changed underneath it.
    fresh_profiles = build_container_fixtures._profiles()
    fresh_entries = [
        {
            "file": f"variant-{index:02d}.musx",
            "source_count": profile.source_count,
            "method_varied": profile.method_varied,
            "members": [
                {"name": m.name, "size": m.size, "compress_type": m.compress_type}
                for m in profile.members
            ],
        }
        for index, profile in enumerate(fresh_profiles, start=1)
    ]

    committed_entries = [
        {
            "file": profile["file"],
            "source_count": profile["source_count"],
            "method_varied": profile.get("method_varied", False),
            "members": profile["members"],
        }
        for profile in _profiles()
    ]

    assert fresh_entries == committed_entries
