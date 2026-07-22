"""Tests for provenance-stamp parsing in legacy .mus headers."""

from collections.abc import Callable

from finale_file_parser.version.mus import parse


def test_parses_both_stamps(mus_metadata_header: Callable[..., bytes]) -> None:
    detail = parse(mus_metadata_header())
    assert detail.created is not None and detail.modified is not None
    assert (detail.created.year, detail.created.month, detail.created.day) == (2011, 10, 23)
    assert (detail.modified.year, detail.modified.month, detail.modified.day) == (2012, 4, 1)
    assert detail.created.application == "FIN"
    assert detail.created.platform == "MAC"


def test_banner_and_year_are_unaffected_by_stamps(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_metadata_header())
    assert detail.year == 2011
    assert detail.banner.startswith("Finale(R) 2011")


def test_windows_platform_tag(mus_metadata_header: Callable[..., bytes]) -> None:
    created = parse(mus_metadata_header(platform=b"WIN")).created
    assert created is not None
    assert created.platform == "WIN"


def test_implausible_month_yields_none_for_that_stamp_only(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_metadata_header(created=(111, 13, 1)))
    assert detail.created is None
    assert detail.modified is not None


def test_implausible_year_yields_none(mus_metadata_header: Callable[..., bytes]) -> None:
    assert parse(mus_metadata_header(created=(10, 6, 1))).created is None  # 1910
    assert parse(mus_metadata_header(created=(200, 6, 1))).created is None  # 2100


def test_implausible_day_yields_none(mus_metadata_header: Callable[..., bytes]) -> None:
    assert parse(mus_metadata_header(created=(111, 6, 0))).created is None
    assert parse(mus_metadata_header(created=(111, 6, 32))).created is None


def test_missing_application_tag_yields_none(mus_metadata_header: Callable[..., bytes]) -> None:
    assert parse(mus_metadata_header(app=b"")).created is None


def test_stamp_is_all_or_nothing_never_partial(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    # A bad date must not leave a stamp carrying only the tags.
    assert parse(mus_metadata_header(created=(0, 0, 0))).created is None


def test_truncated_header_yields_no_stamps_and_does_not_raise(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_metadata_header(size=0x60))
    assert detail.created is None
    assert detail.modified is None
    assert detail.year == 2011


def test_empty_header_does_not_raise() -> None:
    detail = parse(b"")
    assert detail.created is None and detail.modified is None and detail.year is None


def test_unterminated_application_tag_stops_at_the_field_boundary(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    """An application tag with no NUL must not absorb the platform bytes.

    The application and platform fields are four bytes apart, so a four-byte
    unterminated tag runs straight into the platform tag unless the read is
    bounded by the field width.
    """
    header = mus_metadata_header(app=b"WXYZ", platform=b"MAC")
    created = parse(header).created
    assert created is not None
    assert created.application == "WXYZ"
    assert created.platform == "MAC"


def test_unterminated_platform_tag_stops_at_the_field_boundary(
    mus_metadata_header: Callable[..., bytes],
) -> None:
    """A platform tag with no NUL must not absorb bytes beyond the field boundary.

    Mirrors the application-tag bleed test above, for the platform tag: the
    created stamp's platform field is at offset 0x74, `_TAG_FIELD_SIZE` (4)
    bytes wide. A four-byte, non-NUL-terminated platform value has nothing to
    stop it at the right byte except that fixed field width, so a marker is
    planted immediately past the field to prove the read does not run on.
    """
    CREATED_PLAT = 0x74
    header = bytearray(mus_metadata_header(platform=b"MACX"))
    header[CREATED_PLAT + 4 : CREATED_PLAT + 8] = b"BAD!"
    created = parse(bytes(header)).created
    assert created is not None
    assert created.platform == "MACX"
