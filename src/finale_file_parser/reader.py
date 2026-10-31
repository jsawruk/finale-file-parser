"""Stable, format-neutral entry points for reading Finale files."""

from __future__ import annotations

import os

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.ir import Score
from finale_file_parser.version.detect import detect_version
from finale_file_parser.version.models import Family

__all__ = ["read_document", "read_score"]


def read_document(path: str | os.PathLike[str]) -> EnigmaDocument:
    """Read a Finale file into the shared document model.

    The container family is detected from the file itself; the filename suffix
    is ignored. Existing reader exceptions propagate unchanged.
    """
    if detect_version(path).family is Family.MUSX:
        return parse_enigma(score_xml(path))
    return read_mus_document(path)


def read_score(path: str | os.PathLike[str], *, skip_unplaced: bool = False) -> Score:
    """Read a Finale file into the format-neutral score model.

    This is the ordinary application-facing entry point. Use
    :func:`read_document` when record-level access is needed.
    `skip_unplaced` leaves out entries the music never reaches -- typically
    deleted passages -- rather than refusing the file; see `locate_entries`.
    """
    return build_score(read_document(path), skip_unplaced=skip_unplaced)
