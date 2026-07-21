from collections.abc import Callable

from finale_file_parser.version.mus import parse


def test_parses_year_from_banner(mus_header: Callable[..., bytes]) -> None:
    detail = parse(mus_header(b"Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc."))
    assert detail.year == 2011
    assert detail.banner == "Finale(R) 2011 Copyright (c) 1987-2010 MakeMusic Inc."


def test_parses_coda_era_banner(mus_header: Callable[..., bytes]) -> None:
    detail = parse(mus_header(b"Finale(R) 2001 Copyright (c) 1987-2000 Coda Music Technology"))
    assert detail.year == 2001


def test_parses_makemusic_bang_banner(mus_header: Callable[..., bytes]) -> None:
    # Finale 2005 spells the vendor "MakeMusic!" — do not pattern-match vendor names.
    detail = parse(mus_header(b"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc."))
    assert detail.year == 2005


def test_stops_at_first_nul_ignoring_previous_writer_residue(
    mus_header: Callable[..., bytes],
) -> None:
    # Real corpus case: shorter 2005 banner overwrote the longer 2004 Coda banner.
    field = b"Finale(R) 2005 Copyright (c) 1987-2004 MakeMusic! Inc.\x00\x00\x00logy"
    detail = parse(mus_header(field))
    assert detail.banner.endswith("MakeMusic! Inc.")
    assert "logy" not in detail.banner


def test_unparseable_banner_yields_none_year_but_keeps_text(
    mus_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_header(b"Some Future Banner Format"))
    assert detail.year is None
    assert detail.banner == "Some Future Banner Format"


def test_empty_banner_field_yields_empty_string_and_none_year(
    mus_header: Callable[..., bytes],
) -> None:
    detail = parse(mus_header())
    assert detail.banner == ""
    assert detail.year is None


def test_short_header_does_not_raise() -> None:
    detail = parse(b"ENIGMA BINARY FILE")
    assert detail.year is None
