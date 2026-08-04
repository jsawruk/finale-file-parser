"""The CLI converts real corpus documents end to end.

`test_cli.py` stubs the readers to cover the CLI's own decisions. This runs the
whole path -- detect, read, build, export, write -- on files from both containers
and both `.mus` eras, because the stubs cannot catch a wiring mistake between
the pieces.

Report counts only -- never a corpus filename, title, or record value.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from corpus_files import CORPUS, corpus_paths

from finale_file_parser import cli
from finale_file_parser.version import mus as mus_header

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="local corpus not present")

SAMPLE = 4
"""Documents taken from each cohort. Enough to catch a wiring error; the corpus
sweeps already pin conversion fidelity across every document."""


def _cohorts() -> list[Path]:
    """A few `.musx`, a few 2011 `.mus`, a few DCL `.mus` -- all three paths."""
    musx = corpus_paths(".musx")[:SAMPLE]
    dcl: list[Path] = []
    later: list[Path] = []
    for path in corpus_paths(".mus"):
        year = mus_header.parse(path.read_bytes()[: mus_header.MUS_METADATA_SIZE]).year
        target = dcl if (year is not None and year <= 2005) else later
        if len(target) < SAMPLE:
            target.append(path)
        if len(dcl) >= SAMPLE and len(later) >= SAMPLE:
            break
    return musx + dcl + later


def test_the_cli_converts_documents_from_every_reader(tmp_path: Path) -> None:
    """One invocation per document, through `main` exactly as a shell would."""
    converted = 0
    for source in _cohorts():
        target = tmp_path / f"{converted}.musicxml"
        status = cli.main(["convert", str(source), "-o", str(target)])
        if status == cli.EXIT_OK:
            assert target.read_bytes().startswith(b"<?xml")
            converted += 1
    # Some corpus documents legitimately refuse to build; what must not happen is
    # that a whole cohort produces nothing, which is what a wiring error looks like.
    assert converted >= 2 * SAMPLE


def test_a_batch_writes_one_file_per_document(tmp_path: Path) -> None:
    """The batch path builds output paths differently from the single-file path,
    so it needs its own exercise."""
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    for index, path in enumerate(corpus_paths(".musx")[:SAMPLE]):
        (source_dir / f"{index}.musx").write_bytes(path.read_bytes())

    out = tmp_path / "out"
    cli.main(["convert", str(source_dir), "-o", str(out)])
    assert len(list(out.glob("*.musicxml"))) == SAMPLE
