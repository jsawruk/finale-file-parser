"""Export the local corpus to MusicXML and check the result.

Skipped wherever corpus/ is absent (e.g. CI).

Two layers of checking:

* **Always** -- structural invariants computed from the output itself.
* **When a schema is available** -- validation against the official W3C MusicXML
  schema, which is the only genuinely external oracle here. It is opt-in via
  ``MUSICXML_XSD`` rather than vendored, because `docs/REFERENCES.md` flags the
  schema's licence terms as needing a decision before reuse. To run it:

      git clone https://github.com/w3c/musicxml
      # point the imports in schema/musicxml.xsd at the sibling xml.xsd/xlink.xsd
      MUSICXML_XSD=/path/to/musicxml/schema/musicxml.xsd uv run pytest

  This is how the grace-note bug was found: the exporter wrote duration 0, which
  the schema rejects.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from defusedxml import ElementTree as DET

from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.export.musicxml import to_musicxml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

SAMPLE = 25
SCHEMA_ENV = "MUSICXML_XSD"


def _archives() -> list[Path]:
    return [p for p in sorted(CORPUS.rglob("*")) if p.is_file() and p.suffix.lower() == ".musx"][
        :SAMPLE
    ]


def _export(path: Path) -> bytes:
    return to_musicxml(build_score(parse_enigma(score_xml(path))))


def test_every_score_exports_and_is_well_formed() -> None:
    exported = 0
    for path in _archives():
        document = DET.fromstring(_export(path).decode())
        assert document.tag == "score-partwise"
        assert document.findall("./part-list/score-part"), "no parts declared"
        assert len(document.findall("./part")) == len(document.findall("./part-list/score-part")), (
            "part count does not match the part list"
        )
        exported += 1
    assert exported == SAMPLE


def test_every_note_has_a_type_and_a_duration_unless_it_is_a_grace_note() -> None:
    """The grace-note rule, asserted on real output rather than a constructed case."""
    notes = grace = 0
    for path in _archives():
        document = DET.fromstring(_export(path).decode())
        for note in document.iter("note"):
            notes += 1
            assert note.findtext("type"), "note without a type"
            if note.find("grace") is not None:
                grace += 1
                assert note.find("duration") is None, "grace note carries a duration"
            else:
                duration = note.findtext("duration")
                assert duration is not None and int(duration) > 0, "duration must be positive"
    assert notes > 1000
    assert grace > 0, "no grace note in the sample; that path is untested here"


@pytest.mark.skipif(shutil.which("xmllint") is None, reason="xmllint not available")
@pytest.mark.skipif(not os.environ.get(SCHEMA_ENV), reason=f"{SCHEMA_ENV} not set")
def test_output_validates_against_the_official_schema(tmp_path: Path) -> None:
    schema = os.environ[SCHEMA_ENV]
    failures: list[str] = []
    for index, path in enumerate(_archives()):
        target = tmp_path / f"{index:03d}.musicxml"
        target.write_bytes(_export(path))
        result = subprocess.run(
            ["xmllint", "--noout", "--nonet", "--schema", schema, str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            failures.append(result.stderr.strip().splitlines()[-1] if result.stderr else "failed")
    assert not failures, f"{len(failures)} of {SAMPLE} failed schema validation: {failures[:3]}"
