from collections.abc import Callable

import pytest

from finale_file_parser.version.family import HEADER_SIZE, classify
from finale_file_parser.version.models import Family, NotFinaleFileError
from finale_file_parser.version.mus import BANNER_FIELD_SIZE, BANNER_OFFSET


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


def test_header_size_covers_the_full_banner_field() -> None:
    # HEADER_SIZE is how many bytes detect_version reads off disk before
    # handing them to mus.parse, which then slices out the banner field at
    # [BANNER_OFFSET : BANNER_OFFSET + BANNER_FIELD_SIZE]. Comparing
    # HEADER_SIZE to a literal (above) only pins family.py's own constant; it
    # proves nothing about whether that many bytes actually cover mus.py's
    # banner field. If HEADER_SIZE were ever smaller than this sum, every
    # read would hand mus.parse a truncated field and silently shorten (or
    # blank) the parsed banner/year.
    assert HEADER_SIZE == BANNER_OFFSET + BANNER_FIELD_SIZE
