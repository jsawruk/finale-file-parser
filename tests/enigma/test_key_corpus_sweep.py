"""Sweep the full local corpus through decode_key, checking every distinct raw

`keySig.key` integer decodes cleanly and that the observed set of raw values
matches the pinned survey result exactly.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is copyrighted third-party
material and is gitignored; these assertions are the only check against real archives.

The core assertion is that every distinct raw key value decodes via decode_key
without raising -- the survey found all 13 corpus values are standard, so any
UnsupportedKeyError here is a real finding, not a reason to loosen an assertion.

Report counts and the key integers only -- never a corpus filename, title, lyric,
composer, or other record value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.document import Record, parse_enigma
from finale_file_parser.enigma.key import decode_key
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.score import score_xml

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_ARCHIVES = 401

# Pinned by the 2026-07-24 survey. A corpus change (new archives, edited
# archives) must force a deliberate update here, not a silent pass.
EXPECTED_RAW_KEY_VALUES = {1, 2, 3, 251, 252, 253, 254, 255, 256, 257, 507, 510, 511}


def _archives() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".musx"]


def test_every_corpus_key_signature_decodes() -> None:
    paths = _archives()
    assert len(paths) == EXPECTED_ARCHIVES

    observed_raw_values: set[int] = set()
    archives_read = 0
    sampled_locate_compositions = 0

    for path in paths:
        doc = parse_enigma(score_xml(path))
        archives_read += 1

        meas_specs = [r for r in doc.others.of_tag("measSpec") if "part" not in r.attrs]
        for record in meas_specs:
            key_sig = record.fields.get("keySig")
            if not isinstance(key_sig, Record):
                continue
            key_value = key_sig.fields.get("key")
            if not isinstance(key_value, str):
                continue
            observed_raw_values.add(int(key_value))

        if sampled_locate_compositions < 5:
            locations = locate_entries(doc)
            for location in list(locations.values())[:5]:
                decode_key(location.key_signature)
                sampled_locate_compositions += 1

    assert archives_read == EXPECTED_ARCHIVES

    # Every distinct raw value must decode without raising. If this fails, that
    # is a real finding (a raw key value outside the reverse-engineered
    # standard model) -- report it, do not loosen this assertion.
    for raw in sorted(observed_raw_values):
        decode_key(raw)

    # Report the observed set, not just assert it, so a mismatch is visible
    # (structural counts and integers only -- no record content).
    sorted_values = sorted(observed_raw_values)
    print(f"observed {len(observed_raw_values)} distinct raw key values: {sorted_values}")

    # If the observed set disagrees with the pinned survey result, that is a
    # real finding to report -- do not adjust this constant to match.
    assert observed_raw_values == EXPECTED_RAW_KEY_VALUES

    assert sampled_locate_compositions > 0, "decode_key never composed with locate_entries"
