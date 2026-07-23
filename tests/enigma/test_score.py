import gzip
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from finale_file_parser.container.models import CorruptContainerError
from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.score import MAX_INFLATED, score_xml
from finale_file_parser.version.models import NotFinaleFileError

MIMETYPE = b"application/vnd.makemusic.notation"
SAMPLE_XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<finale version="18.0"><entries/></finale>'


@pytest.fixture
def make_score(tmp_path: Path) -> Callable[..., Path]:
    """Build a .musx whose score.dat encrypts to the given payload.

    Everything here is constructed in-test — no corpus bytes.
    """

    def build(
        *,
        xml: bytes = SAMPLE_XML,
        raw_plaintext: bytes | None = None,
        include_score: bool = True,
        name: str = "sample.musx",
    ) -> Path:
        plaintext = raw_plaintext if raw_plaintext is not None else gzip.compress(xml)
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
            archive.writestr("NotationMetadata.xml", "<metadata/>")
            if include_score:
                archive.writestr("score.dat", decrypt(plaintext))
        return path

    return build


def test_round_trips_our_own_xml(make_score: Callable[..., Path]) -> None:
    assert score_xml(make_score()) == SAMPLE_XML


def test_accepts_a_str_path(make_score: Callable[..., Path]) -> None:
    assert score_xml(str(make_score())) == SAMPLE_XML


def test_handles_a_payload_spanning_the_keystream_reset(
    make_score: Callable[..., Path],
) -> None:
    """Exercises the reset end to end, not just in the cipher unit tests."""
    big = b'<finale version="18.0">' + b"<t>x</t>" * 40000 + b"</finale>"
    assert score_xml(make_score(xml=big)) == big


def test_rejects_a_stream_that_is_not_gzip(make_score: Callable[..., Path]) -> None:
    with pytest.raises(CorruptScoreError, match="not a gzip stream"):
        score_xml(make_score(raw_plaintext=b"this is not gzip at all"))


def test_rejects_truncated_gzip(make_score: Callable[..., Path]) -> None:
    truncated = gzip.compress(SAMPLE_XML)[:-8]
    with pytest.raises(CorruptScoreError):
        score_xml(make_score(raw_plaintext=truncated))


def test_rejects_output_over_the_inflation_cap(make_score: Callable[..., Path]) -> None:
    """A decompression bomb: tiny compressed, enormous inflated."""
    bomb = gzip.compress(b"\x00" * (MAX_INFLATED + 1024))
    assert len(bomb) < 1_000_000, "bomb should be small on disk"
    with pytest.raises(CorruptScoreError, match="exceeds"):
        score_xml(make_score(raw_plaintext=bomb))


def test_archive_without_score_dat_raises(make_score: Callable[..., Path]) -> None:
    with pytest.raises(CorruptContainerError):
        score_xml(make_score(include_score=False))


def test_non_finale_zip_raises(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "not a score")
    with pytest.raises(NotFinaleFileError):
        score_xml(path)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        score_xml(tmp_path / "nope.musx")


def test_corrupt_score_error_is_a_finale_file_error() -> None:
    from finale_file_parser.errors import FinaleFileError

    assert issubclass(CorruptScoreError, FinaleFileError)
