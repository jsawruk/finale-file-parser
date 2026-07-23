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

The hardcoded set is a change-detector: it catches those four names regressing,
but not the general shape of the bug. A subpackage that adds a name to its own
`__all__` and forgets to re-export it at the root would still pass. The third
test derives that relationship instead of restating it, so any subpackage
export that never reaches the root fails without anyone remembering to update
a list here.
"""

from __future__ import annotations

import finale_file_parser
from finale_file_parser import container, enigma
from finale_file_parser.version import models as version_models

EXPECTED_PUBLIC_NAMES = {
    "MAX_INFLATED",
    "AppVersion",
    "Confidence",
    "ContainerEntry",
    "CorruptContainerError",
    "CorruptScoreError",
    "Family",
    "FileVersion",
    "FinaleFileError",
    "MusDetail",
    "MusxContainer",
    "MusxDetail",
    "NotFinaleFileError",
    "ProvenanceStamp",
    "decrypt",
    "detect_version",
    "open_musx",
    "score_xml",
}


def test_all_exports_are_reachable_at_package_root() -> None:
    for name in finale_file_parser.__all__:
        assert hasattr(finale_file_parser, name), f"{name!r} in __all__ but not importable"


def test_all_declares_the_expected_public_names() -> None:
    assert set(finale_file_parser.__all__) == EXPECTED_PUBLIC_NAMES


def test_every_subpackage_export_reaches_the_package_root() -> None:
    """Derived, not restated: a subpackage that exports a name the root never
    re-exports fails here without anyone remembering to update a hardcoded
    list. This is the general shape of the bug that shipped once already."""
    root = set(finale_file_parser.__all__)
    missing = set(container.__all__) - root
    assert not missing, f"exported by finale_file_parser.container but not at the root: {missing}"
    missing_enigma = set(enigma.__all__) - root
    assert not missing_enigma, (
        f"exported by finale_file_parser.enigma but not at the root: {missing_enigma}"
    )
    version_public = (
        {name for name in version_models.__all__ if not name.startswith("_")}
        if hasattr(version_models, "__all__")
        else set()
    )
    assert not (version_public - root), (
        f"exported by version.models but not at the root: {version_public - root}"
    )
