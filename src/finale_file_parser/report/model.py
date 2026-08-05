"""Building an `Inspection`: what the parser saw, and how far it got.

**This module reimplements nothing.** It calls the public readers and records
what each returned or raised. Parsing logic of its own would be a second
implementation that could disagree with the real one, and a diagnostic tool that
lies about the parser is worse than no tool.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_payload import MusPool, read_mus_pools
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.report.ladder import Ladder, Stage
from finale_file_parser.report.summary import summarise_document, summarise_score
from finale_file_parser.version.detect import detect_version

__all__ = ["MAX_FIELD_DEPTH", "MAX_JSON_BYTES", "Inspection", "inspect_document"]

MAX_JSON_BYTES = 16 * 1024 * 1024
"""Budget for the embedded JSON. The largest corpus payload is ~500 KB, so no
real document approaches this; it exists to stop a pathological file."""

MAX_FIELD_DEPTH = 8
"""A record's fields may contain records. Bound the walk."""


@dataclass
class Inspection:
    """Everything the report shows about one document."""

    file: dict[str, str]
    stages: list[Stage] = field(default_factory=list)
    score: dict[str, object] | None = None
    document: dict[str, object] | None = None
    records: dict[str, object] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    """Anything the report had to leave out, and why."""


def _identity(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    return {
        "name": path.name,
        "size": str(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _no_paths(text: str, path: Path) -> str:
    """Reader messages embed the path. A report is meant to be sendable."""
    return text.replace(str(path), path.name).replace(str(path.parent) + os.sep, "")


def _pools_detail(pools: tuple[MusPool, ...]) -> dict[str, str]:
    """Cannot raise, unlike indexing `pools[0]` directly.

    A ladder stage's `detail` callable is not guarded by `Ladder.run` the way
    `call` is (see `Ladder.run`'s docstring) — only the call it wraps is inside
    the try/except. A decode that legitimately returns zero pools would make
    `pools[0]` raise `IndexError` *outside* that guard, which would break
    "report generation never fails". So this checks before indexing instead.
    """
    order = pools[0].byte_order if pools else "unknown"
    return {"pools": str(len(pools)), "byte order": order}


def inspect_document(path: str | os.PathLike[str]) -> Inspection:
    """Run the pipeline for `path`, recording how far it got."""
    target = Path(path)
    inspection = Inspection(file=_identity(target))
    ladder = Ladder()

    version = ladder.run(
        "detect version",
        lambda: detect_version(target),
        lambda v: {"family": str(v.family.value), "label": v.label},
    )
    family = str(version.family.value) if version is not None else ""

    if family == "musx":
        _musx_stages(ladder, target, inspection)
    else:
        _mus_stages(ladder, target, inspection)

    inspection.stages = [
        Stage(s.name, s.status, s.detail, _no_paths(s.error, target) if s.error else None)
        for s in ladder.stages
    ]
    return inspection


def _mus_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    ladder.run("decode payload", lambda: read_mus_pools(target), _pools_detail)
    document = ladder.run("build document", lambda: read_mus_document(target))
    _finish(ladder, document, inspection)


def _musx_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    xml = ladder.run(
        "extract score.dat", lambda: score_xml(target), lambda b: {"bytes": str(len(b))}
    )
    document = ladder.run("parse EnigmaXML", lambda: parse_enigma(xml or b""))
    _finish(ladder, document, inspection)


def _finish(ladder: Ladder, document: EnigmaDocument | None, inspection: Inspection) -> None:
    """Typed rather than ignored: a None document means the ladder already
    stopped, and `run` records the remaining rungs as skipped."""
    if document is None:
        ladder.run("build score", _unreachable)
        ladder.run("export MusicXML", _unreachable)
        return
    # `summarise_document` returns the narrower `DocumentSummary` TypedDict;
    # `Inspection.document` is the untyped `dict[str, object]` the renderer
    # consumes, so this is a widening cast rather than an unsafe one.
    inspection.document = cast(dict[str, object], summarise_document(document))
    score = ladder.run("build score", lambda: build_score(document))
    if score is None:
        ladder.run("export MusicXML", _unreachable)
        return
    inspection.score = summarise_score(score)
    ladder.run(
        "export MusicXML",
        lambda: to_musicxml(score),
        lambda data: {"bytes": str(len(data))},
    )


def _unreachable() -> None:
    """Never called: `Ladder.run` short-circuits once stopped, and records the
    stage as skipped without invoking it."""
    raise AssertionError("ladder should have stopped")
