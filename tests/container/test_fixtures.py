import tomllib
import zipfile
from pathlib import Path
from typing import cast

import pytest

from finale_file_parser.container.musx import open_musx

FIXTURES = Path(__file__).parent.parent / "fixtures" / "container"
PROFILES = FIXTURES / "PROFILES.toml"
FILLER = b"FINALE-FIXTURE-SYNTHETIC-PAYLOAD-DO-NOT-INTERPRET-"
MIMETYPE_VALUE = b"application/vnd.makemusic.notation"


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
