"""Shared fixtures for version detection tests."""

from __future__ import annotations

from collections.abc import Callable

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
