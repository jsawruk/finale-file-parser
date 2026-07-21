"""Shared fixtures for version detection tests."""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

MUS_MAGIC = b"ENIGMA BINARY FILE"
BANNER_OFFSET = 0x20
HEADER_BYTES = 0x60
"""Held literal here on purpose: the fixtures must not depend on production
constants, so a wrong value in `family.py` cannot make these tests agree with it."""


@pytest.fixture
def mus_header() -> Callable[..., bytes]:
    """Build a synthetic .mus header carrying `banner` at offset 0x20."""

    def build(banner: bytes = b"", *, magic: bytes = MUS_MAGIC) -> bytes:
        header = bytearray(b"\x00" * HEADER_BYTES)
        header[0 : len(magic)] = magic
        header[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
        return bytes(header)

    return build


MIMETYPE = b"application/vnd.makemusic.notation"

SAMPLE_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">
  <fileInfo>
    <created>
      <platform>MAC</platform>
      <appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>
    </created>
    <modified>
      <platform>WIN</platform>
      <appVersion><major>18</major><maint>5</maint><devStatus>dev</devStatus><build>7098</build></appVersion>
    </modified>
  </fileInfo>
</metadata>
"""


@pytest.fixture
def make_musx(tmp_path: Path) -> Callable[..., Path]:
    """Write a .musx-shaped archive into tmp_path and return its path."""

    def build(
        *,
        mimetype: bytes = MIMETYPE,
        metadata: str | None = SAMPLE_METADATA,
        name: str = "sample.musx",
    ) -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", mimetype)
            if metadata is not None:
                archive.writestr("NotationMetadata.xml", metadata)
        return path

    return build
