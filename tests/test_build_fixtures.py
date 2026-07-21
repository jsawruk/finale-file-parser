"""Direct unit tests for scripts/build_version_fixtures.py's metadata scrubber.

This script is the privacy-critical step that turns corpus NotationMetadata.xml
into committed fixtures. Before this file existed, its only coverage was
assertions on its own already-committed output (tests/version/test_fixtures.py)
-- a scrub regression would be invisible until someone regenerated the
fixtures. These tests feed `_scrub_notation_metadata` synthetic metadata built
here, never anything from corpus/, and check its output directly.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

import pytest
from build_version_fixtures import _scrub_notation_metadata
from defusedxml.ElementTree import fromstring

NS = "http://www.makemusic.com/2012/NotationMetadata"

# A synthetic document exercising everything the scrubber must remove:
# root-level siblings of <fileInfo> (title/subtitle/composer/arranger/
# lyricist/copyright), a non-"version" root attribute, attributes on
# <created>/<modified> themselves, and a populated <modifiedBy>.
SYNTHETIC_METADATA = f"""<?xml version="1.0" encoding="UTF-8"?>
<metadata version="18.0" revision="leak-me-not" xmlns="{NS}">
  <title>Synthetic Title</title>
  <subtitle>Synthetic Subtitle</subtitle>
  <composer>Synthetic Composer</composer>
  <arranger>Synthetic Arranger</arranger>
  <lyricist>Synthetic Lyricist</lyricist>
  <copyright>Synthetic Copyright Notice</copyright>
  <fileInfo>
    <created author="Jane Doe">
      <platform>MAC</platform>
      <appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>
    </created>
    <modified editor="Jane Doe">
      <platform>WIN</platform>
      <appVersion>
        <major>18</major><maint>5</maint><devStatus>dev</devStatus><build>7098</build>
      </appVersion>
      <modifiedBy>Jane Doe</modifiedBy>
    </modified>
  </fileInfo>
</metadata>
"""


def _local_names(root: Element) -> set[str]:
    return {element.tag.rsplit("}", 1)[-1] for element in root.iter()}


def _find(root: Element, local_name: str) -> Element:
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == local_name:
            return element
    raise AssertionError(f"no <{local_name}> found in output")


def test_removes_root_level_siblings_of_file_info() -> None:
    output = _scrub_notation_metadata(SYNTHETIC_METADATA.encode("utf-8"), "synthetic")
    tags = _local_names(fromstring(output))
    for leaked in ("title", "subtitle", "composer", "arranger", "lyricist", "copyright"):
        assert leaked not in tags


def test_removes_unexpected_root_attributes_but_keeps_version() -> None:
    output = _scrub_notation_metadata(SYNTHETIC_METADATA.encode("utf-8"), "synthetic")
    root = fromstring(output)
    assert "revision" not in root.attrib
    assert root.get("version") == "18.0"


def test_strips_attributes_on_created_and_modified_elements() -> None:
    output = _scrub_notation_metadata(SYNTHETIC_METADATA.encode("utf-8"), "synthetic")
    root = fromstring(output)
    created = _find(root, "created")
    modified = _find(root, "modified")
    assert created.attrib == {}
    assert modified.attrib == {}


def test_blanks_non_empty_modified_by() -> None:
    # `_blank_modified_by` sets .text = "", but a self-closing element
    # serializes with no text at all, so a fresh parse sees None rather than
    # "" -- both mean the name did not survive, which is what matters here.
    output = _scrub_notation_metadata(SYNTHETIC_METADATA.encode("utf-8"), "synthetic")
    root = fromstring(output)
    modified_by = _find(root, "modifiedBy")
    assert not modified_by.text


def test_keeps_the_created_and_modified_structure_version_detection_reads() -> None:
    output = _scrub_notation_metadata(SYNTHETIC_METADATA.encode("utf-8"), "synthetic")
    root = fromstring(output)
    created = _find(root, "created")
    modified = _find(root, "modified")
    assert _find(created, "platform").text == "MAC"
    assert _find(modified, "platform").text == "WIN"
    assert _find(modified, "major").text == "18"


def test_raises_system_exit_when_root_is_not_metadata() -> None:
    document = f'<notMetadata xmlns="{NS}"><fileInfo/></notMetadata>'
    with pytest.raises(SystemExit):
        _scrub_notation_metadata(document.encode("utf-8"), "synthetic")


def test_raises_system_exit_when_file_info_is_missing() -> None:
    document = f'<metadata version="18.0" xmlns="{NS}"><title>x</title></metadata>'
    with pytest.raises(SystemExit):
        _scrub_notation_metadata(document.encode("utf-8"), "synthetic")
