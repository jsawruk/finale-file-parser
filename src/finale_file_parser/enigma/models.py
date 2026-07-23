"""Types for the EnigmaXML decoder."""

from __future__ import annotations

from finale_file_parser.errors import FinaleFileError


class CorruptScoreError(FinaleFileError):
    """The score stream could not be decoded into EnigmaXML.

    Raised when the decrypted bytes are not a gzip stream, fail to inflate, or
    would inflate past the cap. Unlike the version modules, which degrade to
    "unknown" so unfamiliar variants stay inspectable, this raises: a caller
    asking for the score asked for a specific thing, and half a score is not
    useful.
    """
