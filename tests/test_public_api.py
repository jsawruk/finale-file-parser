"""Verify the package's public exports are actually reachable at the root.

`finale_file_parser/__init__.py` declares `__all__`, but the rest of the test
suite imports most of those names from the submodule
`finale_file_parser.version.models` instead of the package root. This test
closes that gap by asserting every name in `__all__` resolves as an attribute
of the top-level package.

That reachability check alone cannot catch a name missing from `__all__`
altogether — it would pass just as happily whether or not `open_musx` and
friends were ever listed there, which is exactly the bug that shipped:
`container/__init__.py` was empty and the four container names were absent
from `__all__`, so this test passed while the public API was unreachable
without digging into `finale_file_parser.container.musx`. The second test
below pins a hardcoded set of names that must appear in `__all__`, so an
omission fails instead of passing silently.
"""

from __future__ import annotations

import finale_file_parser

EXPECTED_PUBLIC_NAMES = {
    "AppVersion",
    "Confidence",
    "ContainerEntry",
    "CorruptContainerError",
    "Family",
    "FileVersion",
    "FinaleFileError",
    "MusDetail",
    "MusxContainer",
    "MusxDetail",
    "NotFinaleFileError",
    "detect_version",
    "open_musx",
}


def test_all_exports_are_reachable_at_package_root() -> None:
    for name in finale_file_parser.__all__:
        assert hasattr(finale_file_parser, name), f"{name!r} in __all__ but not importable"


def test_all_declares_the_expected_public_names() -> None:
    assert set(finale_file_parser.__all__) == EXPECTED_PUBLIC_NAMES
