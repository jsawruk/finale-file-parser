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
test derives that relationship instead of restating it, with the four approved
Enigma-only exports excluded because they intentionally do not belong at the
package root.
"""

from __future__ import annotations

import finale_file_parser
from finale_file_parser import container, enigma
from finale_file_parser.version import models as version_models

EXPECTED_PUBLIC_NAMES = {
    "ARTICULATION_CHARACTERS",
    "BeamedNote",
    "MAX_INFLATED",
    "MAX_MUS_PAYLOAD",
    "UNTRANSLATED",
    "TAG_FRAME_SPEC",
    "TAG_GFHOLD",
    "TAG_MEAS_SPEC",
    "MusOther",
    "MusPool",
    "MusRowRecord",
    "MusRows",
    "AppVersion",
    "Confidence",
    "ContainerEntry",
    "CorruptContainerError",
    "CorruptDclStreamError",
    "CorruptScoreError",
    "DetailsPool",
    "Duration",
    "EnigmaDocument",
    "EntriesPool",
    "Entry",
    "EntryLocation",
    "Family",
    "FileVersion",
    "FinaleFileError",
    "KeySignature",
    "Lyric",
    "LyricKind",
    "MeasureRepeats",
    "Repeats",
    "StaffGroup",
    "MalformedEnigmaError",
    "MalformedEntryError",
    "MalformedScoreError",
    "Mode",
    "MusDetail",
    "MusDetailRecord",
    "MusxContainer",
    "MusxDetail",
    "Note",
    "NoteValue",
    "NotFinaleFileError",
    "OptionsPool",
    "OthersPool",
    "Pool",
    "ProvenanceStamp",
    "Record",
    "SpelledNote",
    "Syllabic",
    "SpelledPitch",
    "StaffTransposition",
    "TextsPool",
    "UnsupportedKeyError",
    "EntryChain",
    "Tuplet",
    "entry_chain",
    "read_tuplet",
    "sounded_durations",
    "tuplets_by_entry",
    "TimeSignature",
    "display_time_signature",
    "read_time_signature",
    "time_signatures",
    "Clef",
    "ClefSign",
    "clef_definitions",
    "clefs_by_measure",
    "default_clefs",
    "MUSICXML_VERSION",
    "ExportError",
    "build_score",
    "to_musicxml",
    "StaffNames",
    "file_info",
    "plain_text",
    "staff_names",
    "text_block",
    "decode_key",
    "harm_lev_octave_shift",
    "articulations_by_entry",
    "barline_styles",
    "beams_for",
    "blast_decompress",
    "read_mus_document",
    "read_mus_details",
    "read_mus_entries",
    "read_mus_entry_records",
    "read_mus_others",
    "read_mus_streams",
    "read_mus_pools",
    "read_mus_rows",
    "duration_from_edu",
    "decrypt",
    "detect_version",
    "effective_keys",
    "fingerings_by_entry",
    "jumps_by_measure",
    "locate_entries",
    "lyrics_by_entry",
    "open_musx",
    "parse_enigma",
    "read_entry",
    "read_document",
    "read_score",
    "repeats_for",
    "staff_groups",
    "staff_order",
    "read_mus_payload",
    "read_transposition",
    "verse_syllables",
    "score_xml",
    "spell_note",
    "spell_pitch",
    "transpose_key",
    "transpose_pitch",
    "transposition_residue",
    "written_octave_correction",
}

ENIGMA_ONLY_EXPORTS = {
    "MalformedPercussionError",
    "PercussionAppearance",
    "PercussionNote",
    "percussion_notes",
}


def test_all_exports_are_reachable_at_package_root() -> None:
    for name in finale_file_parser.__all__:
        assert hasattr(finale_file_parser, name), f"{name!r} in __all__ but not importable"


def test_all_declares_the_expected_public_names() -> None:
    assert set(finale_file_parser.__all__) == EXPECTED_PUBLIC_NAMES


def test_every_non_exempt_subpackage_export_reaches_the_package_root() -> None:
    """Derived, not restated, except for the approved Enigma-only boundary."""
    root = set(finale_file_parser.__all__)
    missing = set(container.__all__) - root
    assert not missing, f"exported by finale_file_parser.container but not at the root: {missing}"
    missing_enigma = set(enigma.__all__) - root
    assert missing_enigma == ENIGMA_ONLY_EXPORTS, (
        "unexpected Enigma exports missing from the package root: "
        f"{missing_enigma - ENIGMA_ONLY_EXPORTS}"
    )
    version_public = (
        {name for name in version_models.__all__ if not name.startswith("_")}
        if hasattr(version_models, "__all__")
        else set()
    )
    assert not (version_public - root), (
        f"exported by version.models but not at the root: {version_public - root}"
    )
