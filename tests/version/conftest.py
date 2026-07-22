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


@pytest.fixture
def write_mus(tmp_path: Path, mus_header: Callable[..., bytes]) -> Callable[..., Path]:
    """Write a synthetic .mus file (header plus filler body) and return its path."""

    def build(banner: bytes = b"", *, name: str = "sample.mus") -> Path:
        path = tmp_path / name
        path.write_bytes(mus_header(banner) + b"\xde\xad\xbe\xef" * 64)
        return path

    return build


MIMETYPE = b"application/vnd.makemusic.notation"

SAMPLE_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<metadata version="18.0" xmlns="http://www.makemusic.com/2012/NotationMetadata">
  <fileInfo>
    <created>
      <year>2010</year><month>9</month><day>14</day>
      <platform>MAC</platform>
      <application>FIN</application>
      <appVersion><major>16</major><devStatus>release</devStatus><build>2</build></appVersion>
    </created>
    <modified>
      <year>2015</year><month>11</month><day>23</day>
      <platform>WIN</platform>
      <application>FIN</application>
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


CREATED_DATE, CREATED_APP, CREATED_PLAT = 0x66, 0x70, 0x74
MODIFIED_DATE, MODIFIED_APP, MODIFIED_PLAT = 0x8C, 0x96, 0x9A
METADATA_BYTES = 0xA0


@pytest.fixture
def mus_metadata_header() -> Callable[..., bytes]:
    """Build a .mus header carrying banner plus both provenance stamps."""

    def build(
        banner: bytes = b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc.",
        *,
        created: tuple[int, int, int] | None = (111, 10, 23),  # 2011-10-23
        modified: tuple[int, int, int] | None = (112, 4, 1),  # 2012-04-01
        app: bytes = b"FIN",
        platform: bytes = b"MAC",
        size: int = METADATA_BYTES,
    ) -> bytes:
        buf = bytearray(b"\x00" * size)
        buf[0 : len(MUS_MAGIC)] = MUS_MAGIC
        buf[BANNER_OFFSET : BANNER_OFFSET + len(banner)] = banner
        for date, date_off, app_off, plat_off in (
            (created, CREATED_DATE, CREATED_APP, CREATED_PLAT),
            (modified, MODIFIED_DATE, MODIFIED_APP, MODIFIED_PLAT),
        ):
            if date is None:
                continue
            buf[date_off : date_off + 3] = bytes(date)
            buf[app_off : app_off + len(app)] = app
            buf[plat_off : plat_off + len(platform)] = platform
        return bytes(buf)

    return build
