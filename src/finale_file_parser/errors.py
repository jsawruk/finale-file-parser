"""Shared exception base types.

`container` is the lower architectural layer; `version` is built on top of it
and consumes it (see `docs/ARCHITECTURE.md`). Both layers need to raise a
common `FinaleFileError` family, so that family lives here, in a module
neither layer owns, rather than in `version.models` — the arrangement that
previously forced `container` to import from `version` to get an exception
type, inverting the intended dependency direction.

`finale_file_parser.version.models` re-exports both names so nothing that
already imports them from there needs to change.
"""

from __future__ import annotations


class FinaleFileError(Exception):
    """Base class for every error this package raises."""


class NotFinaleFileError(FinaleFileError):
    """The file is not a Finale file at all — no recognised container or magic."""
