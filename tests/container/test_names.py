import pytest

from finale_file_parser.container.names import is_safe_name

SAFE = [
    "mimetype",
    "META-INF/container.xml",
    "NotationMetadata.xml",
    "score.dat",
    "presets/10002.preset",
    "graphics/1.jpg",
    "some/future/member.bin",  # unknown but harmless — must be allowed
    "weird name with spaces.dat",
]

UNSAFE = [
    "",
    "/etc/passwd",
    "../escape.dat",
    "presets/../../escape.dat",
    "..",
    "dir\\file.dat",
    "C:/windows/system32",
    "bad\x00name",
    "bad\nname",
    "bad\x7fname",  # DEL
    "bad\x85name",  # C1 control (NEL)
    "bad‮name",  # U+202E right-to-left override (bidi spoofing)
    "presets/C:foo",  # mid-path colon (not just a drive-letter prefix)
    "output.txt:hidden:$DATA",  # NTFS alternate-data-stream form
]


@pytest.mark.parametrize("name", SAFE)
def test_safe_names_are_allowed(name: str) -> None:
    assert is_safe_name(name) is True


@pytest.mark.parametrize("name", UNSAFE)
def test_unsafe_names_are_rejected(name: str) -> None:
    assert is_safe_name(name) is False


def test_a_dotdot_inside_a_filename_is_not_a_traversal() -> None:
    # "..." and "a..b" contain dots but no ".." *segment*.
    assert is_safe_name("presets/a..b.preset") is True
    assert is_safe_name("...dat") is True
