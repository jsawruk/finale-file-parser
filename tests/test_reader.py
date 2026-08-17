"""Tests for the stable, format-neutral reader facade."""

from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

import pytest

import finale_file_parser
from finale_file_parser import EnigmaDocument
from finale_file_parser import reader as reader_module
from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.document import parse_enigma
from finale_file_parser.ir import Score

MIMETYPE = b"application/vnd.makemusic.notation"
MUS_MAGIC = b"ENIGMA BINARY FILE"
SAMPLE_XML = b'<finale version="18.0"><entries/></finale>'


def write_musx(path: Path) -> None:
    """Write the smallest valid score archive needed by the facade tests."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("score.dat", decrypt(gzip.compress(SAMPLE_XML)))


def test_read_document_is_available_at_the_package_root() -> None:
    """Callers should not need to know which parser module owns their file."""
    assert callable(getattr(finale_file_parser, "read_document", None))


def test_read_score_is_available_at_the_package_root() -> None:
    """The ordinary use case should require one package-root function."""
    assert callable(getattr(finale_file_parser, "read_score", None))


def test_read_document_detects_musx_from_contents(tmp_path: Path) -> None:
    """A misleading legacy suffix must not send a ZIP container to the `.mus` reader."""
    path = tmp_path / "mislabelled.mus"
    write_musx(path)

    assert isinstance(finale_file_parser.read_document(path), EnigmaDocument)


def test_read_document_detects_mus_from_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misleading ZIP suffix must not send a legacy container to the MUSX reader."""
    path = tmp_path / "mislabelled.musx"
    path.write_bytes(MUS_MAGIC + bytes(0xA0 - len(MUS_MAGIC)))
    expected = parse_enigma(SAMPLE_XML)
    monkeypatch.setattr(reader_module, "read_mus_document", lambda _path: expected, raising=False)

    assert finale_file_parser.read_document(path) is expected


def test_read_score_builds_the_format_neutral_model(tmp_path: Path) -> None:
    path = tmp_path / "score.musx"
    write_musx(path)

    assert isinstance(finale_file_parser.read_score(path), Score)
