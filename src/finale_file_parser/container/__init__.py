"""Public interface for the `.musx` container reader.

`open_musx` is the entry point: it opens a `.musx` archive, validates its
structure, and returns a `MusxContainer` for enumerating entries and reading
member bytes. See `container.musx` for the full contract and
`docs/ARCHITECTURE.md` / the design spec for the layer's shape.
"""

from __future__ import annotations

from finale_file_parser.container.models import ContainerEntry, CorruptContainerError
from finale_file_parser.container.musx import MusxContainer, open_musx

__all__ = [
    "ContainerEntry",
    "CorruptContainerError",
    "MusxContainer",
    "open_musx",
]
