"""Smoke test: proves the package imports and the toolchain (pytest + mypy) works end to end."""

from finale_file_parser import greet


def test_greet() -> None:
    assert greet("world").startswith("Hello, world!")
