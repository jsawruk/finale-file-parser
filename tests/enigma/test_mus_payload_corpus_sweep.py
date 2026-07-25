"""Sweep every local .mus file through the payload decoder.

Skipped wherever corpus/ is absent (e.g. CI). The corpus is third-party material
and is gitignored; these assertions are the only check against real files.
Expected values come from docs/formats/mus-binary-notes.md.

Report counts and sizes only -- never a corpus filename, title, or payload.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finale_file_parser.enigma.mus_payload import read_mus_payload
from finale_file_parser.version import mus as mus_header

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

EXPECTED_FILES = 238
EXPECTED_DCL_ERA = 139
"""Banner year <= 2005: PKWARE DCL. Observed 102 (2001) + 1 (2004) + 36 (2005)."""
EXPECTED_ZLIB_ERA = 99
"""Banner year >= 2011: chain of zlib streams. Observed 89 (2011) + 10 (2012)."""

LAST_DCL_YEAR = 2005
MIN_RATIO, MAX_RATIO = 0.8, 9.0
"""Observed inflation over the whole corpus: DCL 0.82x-2.75x (median 2.35x),
zlib chain 5.87x-8.63x (median 6.07x). The zlib figure is for the CONCATENATED
chain; a single stream is only ~3.2x-3.5x."""


def _mus_files() -> list[Path]:
    return [p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".mus"]


def test_corpus_has_the_expected_shape() -> None:
    """Guards the sweep below: a shrunken corpus must not silently pass.

    Note `.mus` and `.MUS` both occur -- a case-sensitive glob drops the entire
    Windows cohort.
    """
    assert len(_mus_files()) == EXPECTED_FILES


def test_every_mus_file_decodes() -> None:
    files = _mus_files()
    failures: list[str] = []
    dcl_era = zlib_era = 0
    for path in files:
        year = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE]).year
        try:
            payload = read_mus_payload(path)
        except Exception as exc:  # noqa: BLE001 - collecting, not suppressing
            failures.append(f"{type(exc).__name__} (banner {year})")
            continue
        assert payload, "decoded an empty payload"
        ratio = len(payload) / path.stat().st_size
        assert MIN_RATIO <= ratio <= MAX_RATIO, f"inflation {ratio:.2f}x outside expected range"
        if year is not None and year <= LAST_DCL_YEAR:
            dcl_era += 1
        else:
            zlib_era += 1
    assert not failures, f"{len(failures)} of {len(files)} failed: {failures[:5]}"
    assert dcl_era == EXPECTED_DCL_ERA
    assert zlib_era == EXPECTED_ZLIB_ERA


def test_decoded_payloads_are_structured_not_random() -> None:
    """A wrong-but-successful decode would look like noise.

    Real decoded payloads carry runs of printable ASCII (instrument, font and
    category names); random bytes essentially never do at this rate.
    """
    import re

    sampled = 0
    for path in sorted(_mus_files())[::40]:
        payload = read_mus_payload(path)
        runs = [m.group() for m in re.finditer(rb"[\x20-\x7e]{6,}", payload)]
        assert len(runs) >= 20, f"only {len(runs)} printable runs in a decoded payload"
        sampled += 1
    assert sampled >= 5
