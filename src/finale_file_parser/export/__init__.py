"""Exporters: they consume the IR and never a reader's types.

See `docs/DECISIONS.md` (2026-07-20) for why the dependency runs one way.
"""

from __future__ import annotations

from finale_file_parser.export.musicxml import MUSICXML_VERSION, ExportError, to_musicxml

__all__ = ["MUSICXML_VERSION", "ExportError", "to_musicxml"]
