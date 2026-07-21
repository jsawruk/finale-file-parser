from collections.abc import Callable

import pytest

from finale_file_parser.version.family import HEADER_SIZE, classify
from finale_file_parser.version.models import Family, NotFinaleFileError


def test_classifies_mus_by_magic(mus_header: Callable[..., bytes]) -> None:
    assert classify(mus_header(b"Finale(R) 2011")) is Family.MUS


def test_classifies_any_zip_as_musx() -> None:
    assert classify(b"PK\x03\x04" + b"\x00" * 60) is Family.MUSX


def test_rejects_unrelated_bytes() -> None:
    with pytest.raises(NotFinaleFileError):
        classify(b"%PDF-1.4" + b"\x00" * 60)


def test_rejects_empty_input() -> None:
    with pytest.raises(NotFinaleFileError):
        classify(b"")


def test_rejects_truncated_magic() -> None:
    with pytest.raises(NotFinaleFileError):
        classify(b"ENIGMA BIN")


def test_header_size_is_96_bytes() -> None:
    assert HEADER_SIZE == 0x60
