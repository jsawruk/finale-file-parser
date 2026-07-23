from pathlib import Path

import pytest
from defusedxml.ElementTree import fromstring

from finale_file_parser.enigma.document import Record, parse_enigma

FIXTURES = Path(__file__).parent.parent / "fixtures" / "enigma"


def _fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*.xml"))


def test_there_are_fixtures() -> None:
    assert _fixtures(), "no EnigmaXML fixtures found"


@pytest.mark.parametrize("path", _fixtures(), ids=lambda p: p.name)
def test_fixture_parses(path: Path) -> None:
    assert parse_enigma(path.read_bytes()).version


def test_no_fixture_carries_bibliographic_text() -> None:
    """Decoded EnigmaXML's texts pool holds title/composer/copyright in real
    files; committed fixtures are synthetic and carry none of it."""
    for path in _fixtures():
        locals_ = [e.tag.rsplit("}", 1)[-1] for e in fromstring(path.read_bytes()).iter()]
        assert "fileInfo" not in locals_, f"{path.name} contains a fileInfo record"


def test_nested_fixture_reaches_four_deep() -> None:
    doc = parse_enigma((FIXTURES / "nested.xml").read_bytes())
    widget = doc.others.of_tag("widget")[0]
    layer_two = widget.fields["layerTwo"]
    assert isinstance(layer_two, Record)
    layer_three = layer_two.fields["layerThree"]
    assert isinstance(layer_three, Record)
    # The specific 4-deep leaf: widget -> layerTwo -> layerThree -> leafValue.
    assert layer_three.fields["leafValue"] == "NESTED-PLACEHOLDER-DEPTH-4"


def test_nested_fixture_repeats_a_nested_field() -> None:
    doc = parse_enigma((FIXTURES / "nested.xml").read_bytes())
    entry = doc.entries.of_tag("entry")[0]
    notes = entry.fields["note"]
    assert isinstance(notes, tuple) and len(notes) == 3
    assert all(isinstance(n, Record) for n in notes)
