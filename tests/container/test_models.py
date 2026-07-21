import pytest

from finale_file_parser.container.models import ContainerEntry, CorruptContainerError
from finale_file_parser.version.models import FinaleFileError


def test_entry_is_frozen() -> None:
    entry = ContainerEntry(name="score.dat", size=96427, compressed_size=96000, compress_type=8)
    with pytest.raises(AttributeError):
        entry.size = 1  # type: ignore[misc]


def test_corrupt_container_error_is_a_finale_file_error() -> None:
    assert issubclass(CorruptContainerError, FinaleFileError)
