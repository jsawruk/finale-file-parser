"""Verify the package's public exports are actually reachable at the root.

`finale_file_parser/__init__.py` declares `__all__`, but the rest of the test
suite imports most of those names from the submodule
`finale_file_parser.version.models` instead of the package root. This test
closes that gap by asserting every name in `__all__` resolves as an attribute
of the top-level package.
"""

from __future__ import annotations

import finale_file_parser


def test_all_exports_are_reachable_at_package_root() -> None:
    for name in finale_file_parser.__all__:
        assert hasattr(finale_file_parser, name), f"{name!r} in __all__ but not importable"
