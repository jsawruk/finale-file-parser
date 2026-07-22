"""Shared fixtures for container tests.

Every archive here is constructed in-test. Nothing is derived from `corpus/`.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

MIMETYPE = b"application/vnd.makemusic.notation"

DEFAULT_MEMBERS: tuple[tuple[str, bytes], ...] = (
    ("mimetype", MIMETYPE),
    ("META-INF/container.xml", b"<container/>"),
    ("NotationMetadata.xml", b"<metadata/>"),
    ("presets/1.preset", b"preset-bytes"),
    ("score.dat", b"synthetic-score-payload"),
)


@pytest.fixture
def make_archive(tmp_path: Path) -> Callable[..., Path]:
    """Write a zip archive from (name, payload) pairs and return its path."""

    def build(
        members: Sequence[tuple[str, bytes]] = DEFAULT_MEMBERS,
        *,
        name: str = "sample.musx",
        allow_duplicates: bool = False,
    ) -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            for member_name, payload in members:
                # mimetype is stored uncompressed and first, matching all 401
                # corpus archives.
                method = zipfile.ZIP_STORED if member_name == "mimetype" else zipfile.ZIP_DEFLATED
                if allow_duplicates:
                    info = zipfile.ZipInfo(member_name)
                    info.compress_type = method
                    archive.writestr(info, payload)
                else:
                    archive.writestr(member_name, payload, compress_type=method)
        return path

    return build
