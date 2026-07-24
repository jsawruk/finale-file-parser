"""Verify the new pitch-spelling names are exported from the package root and
`finale_file_parser.enigma`, mirroring the reachability checks in
test_public_api.py but scoped to the names this task adds."""

from __future__ import annotations

import finale_file_parser
from finale_file_parser import enigma


def test_pitch_names_exported_from_package_root() -> None:
    for name in (
        "SpelledPitch",
        "SpelledNote",
        "StaffTransposition",
        "spell_pitch",
        "transpose_key",
        "transpose_pitch",
        "spell_note",
        "read_transposition",
    ):
        assert hasattr(finale_file_parser, name), name
        assert hasattr(enigma, name), name
