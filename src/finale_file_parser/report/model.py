"""Building an `Inspection`: what the parser saw, and how far it got.

**This module reimplements nothing.** It calls the public readers and records
what each returned or raised. Parsing logic of its own would be a second
implementation that could disagree with the real one, and a diagnostic tool that
lies about the parser is worse than no tool.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from finale_file_parser.enigma.document import EnigmaDocument, Record, parse_enigma
from finale_file_parser.enigma.mus_details import MusDetailRecord, read_mus_details
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_others import MusOther, read_mus_others
from finale_file_parser.enigma.mus_payload import (
    POOL_DETAILS,
    POOL_ENTRIES,
    POOL_OTHERS,
    POOL_TEXT,
    MusPool,
    read_mus_pools,
)
from finale_file_parser.enigma.mus_rows import MusRowRecord, read_mus_rows
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.report.ladder import Ladder, Stage
from finale_file_parser.report.summary import (
    DocumentSummary,
    ScoreSummary,
    summarise_document,
    summarise_score,
)
from finale_file_parser.version.detect import detect_version

__all__ = [
    "MAX_FIELD_DEPTH",
    "MAX_JSON_BYTES",
    "Inspection",
    "apply_budget",
    "encode_raw",
    "inspect_document",
    "walk_fields",
]

_MUSX_POOLS = ("header", "mappings", "options", "others", "details", "entries", "texts")
"""`EnigmaDocument`'s seven pools, in report order. Kept local rather than
imported from `report.summary`: that module's `_POOLS` is a private detail of
the count-only summary, not a shared constant."""

_MUS_POOL_NAMES = ("others", "details", "entries", "text")
"""The roles a `.mus` container's four pools play, in the order it writes them
-- `enigma.mus_payload`'s own docstring: kind 15/16/17/18 for a labelled DCL
container, and the same order by structure alone for an unlabelled zlib one."""

_MUS_POOL_KINDS = {
    POOL_OTHERS: "others",
    POOL_DETAILS: "details",
    POOL_ENTRIES: "entries",
    POOL_TEXT: "text",
}

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
    score: ScoreSummary | None = None
    document: DocumentSummary | None = None
    records: dict[str, object] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    """Anything the report had to leave out, and why."""


def _identity(path: Path) -> dict[str, str]:
    """The ladder's first rung: `path.read_bytes()` is the one call every later
    stage depends on. A directory, a missing file, or a permission error is
    not a reader bug -- it is the input declining to be read at all, which is
    exactly what `FinaleFileError` means here, and what lets the ladder stop
    cleanly instead of this raising past every guard the rest of the pipeline
    gets (see `inspect_document`)."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise FinaleFileError(f"cannot read {path}: {error}") from error
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

    `Ladder.run` now catches a raising `detail` on the caller's behalf, so this
    would no longer escape and break "report generation never fails" even
    without the check. It stays anyway: a decode that legitimately returns
    zero pools is the one case here known to hit this, and a real byte order
    is a better answer than the ladder's generic "detail unavailable".
    """
    order = pools[0].byte_order if pools else "unknown"
    return {"pools": str(len(pools)), "byte order": order}


def inspect_document(path: str | os.PathLike[str]) -> Inspection:
    """Run the pipeline for `path`, recording how far it got.

    File identity is read as the ladder's own first rung rather than before
    the ladder exists: a directory, a missing path, or a permission error must
    become a stopped-and-recorded ladder, not a raised exception that answers
    "report generation never fails" with no.
    """
    target = Path(path)
    inspection = Inspection(file={"name": target.name})
    ladder = Ladder()

    identity = ladder.run("read file", lambda: _identity(target), lambda d: d)
    if identity is not None:
        inspection.file = identity

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
    apply_budget(inspection)
    return inspection


def _mus_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    pools = ladder.run("decode payload", lambda: read_mus_pools(target), _pools_detail)
    if pools is not None:
        _fill_mus_raw(pools, inspection)
        _fill_mus_records(target, inspection)
    document = ladder.run("build document", lambda: read_mus_document(target))
    _finish(ladder, document, inspection)


def _musx_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    xml = ladder.run(
        "extract score.dat", lambda: score_xml(target), lambda b: {"bytes": str(len(b))}
    )
    document = ladder.run("parse EnigmaXML", lambda: parse_enigma(xml or b""))
    if document is not None:
        inspection.records = _musx_records(document)
    _finish(ladder, document, inspection)


def _safe_read[T](reader: Callable[[], T], inspection: Inspection, label: str) -> T | None:
    """One optional report depth. `FinaleFileError` means this file's era does
    not carry it -- absent, not a failure, so it is dropped without comment.
    Anything else is a genuine reader bug: it must not escape (report
    generation never fails) but is worth naming so it stays visible instead of
    vanishing silently, which is what would turn this into the very kind of
    bug it exists to surface.
    """
    try:
        return reader()
    except FinaleFileError:
        return None
    except Exception as error:  # noqa: BLE001 - a depth reader must not crash the report
        inspection.notes.append(f"{label} unavailable: {type(error).__name__}: {error}")
        return None


def _pool_name(pool: MusPool, index: int) -> str:
    """A DCL container labels its pools by kind; a zlib one does not, so fall
    back to the fixed order `enigma.mus_payload` documents its four streams
    playing by structure alone."""
    if pool.kind is not None and pool.kind in _MUS_POOL_KINDS:
        return _MUS_POOL_KINDS[pool.kind]
    return _MUS_POOL_NAMES[index] if index < len(_MUS_POOL_NAMES) else f"pool{index}"


def _fill_mus_raw(pools: tuple[MusPool, ...], inspection: Inspection) -> None:
    """Every decoded pool, base64, keyed by the role it plays.

    Independent of whether the pools below decode into records: a payload that
    fails every record walk is still worth looking at as bytes.
    """
    inspection.raw = {
        _pool_name(pool, index): encode_raw(pool.data) for index, pool in enumerate(pools)
    }


def _record_entry(
    key: str, fields: object, offset: int | None, length: int | None
) -> dict[str, object]:
    """One record's report shape: identity, walked fields, and where it sat in
    the file when that is known."""
    return {"key": key, "fields": fields, "offset": offset, "length": length}


def _mus_other_entry(record: MusOther) -> dict[str, object]:
    fields = walk_fields(
        {
            "cmper": record.cmper,
            "part": record.part,
            "payload": encode_raw(record.payload),
            "extra": encode_raw(record.extra),
        },
        depth=0,
    )
    return _record_entry(
        key=f"{record.cmper}/{record.part}",
        fields=fields,
        offset=None,
        length=len(record.payload) + len(record.extra),
    )


def _mus_detail_entry(record: MusDetailRecord) -> dict[str, object]:
    fields = walk_fields(
        {
            "cmper1": record.cmper1,
            "cmper2": record.cmper2,
            "inci": record.inci,
            "payload": encode_raw(record.payload),
            "extra": encode_raw(record.extra),
        },
        depth=0,
    )
    return _record_entry(
        key=f"{record.cmper1}/{record.cmper2}/{record.inci}",
        fields=fields,
        offset=None,
        length=len(record.payload) + len(record.extra),
    )


def _mus_row_entry(record: MusRowRecord) -> dict[str, object]:
    fields = walk_fields(
        {
            "cmper": record.cmper,
            "cmper2": record.cmper2,
            "incidences": record.incidences,
            "payload": encode_raw(record.payload),
        },
        depth=0,
    )
    return _record_entry(
        key=f"{record.cmper}/{record.cmper2}",
        fields=fields,
        offset=None,
        length=len(record.payload),
    )


def _group_by_tag(
    items: Iterable[tuple[str, dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    """Every record, grouped under its tag, in the order the reader returned them."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for tag, entry in items:
        grouped.setdefault(tag, []).append(entry)
    return grouped


def _fill_mus_records(target: Path, inspection: Inspection) -> None:
    """The `others`/`details` pools' own records, read raw rather than via the
    built `EnigmaDocument`.

    `mus_document` only translates the handful of tags it currently
    understands (see `UNTRANSLATED`); a tag it drops on the floor is exactly
    what a diagnostic report needs to still show, so this depth calls the raw
    pool readers directly instead of reusing the "build document" stage.

    Two eras, two readers (see `enigma.mus_rows`): whichever era the file is
    not written in fails with `FinaleFileError`, which `_safe_read` turns into
    "simply absent" rather than a stopped report.
    """
    records: dict[str, object] = {}
    others = _safe_read(lambda: read_mus_others(target), inspection, "others records")
    details = _safe_read(lambda: read_mus_details(target), inspection, "details records")
    if others is not None:
        records["others"] = _group_by_tag((str(r.tag), _mus_other_entry(r)) for r in others)
    if details is not None:
        records["details"] = _group_by_tag((str(r.tag), _mus_detail_entry(r)) for r in details)
    if others is None and details is None:
        rows = _safe_read(lambda: read_mus_rows(target), inspection, "row records")
        if rows is not None:
            records["others"] = _group_by_tag(
                (r.tag, _mus_row_entry(r)) for r in rows.others.values()
            )
            records["details"] = _group_by_tag(
                (r.tag, _mus_row_entry(r)) for r in rows.details.values()
            )
    if records:
        inspection.records = records


def _musx_key(record: Record, index: int) -> str:
    """A record's identity for the report: its own identity attributes where
    it carries any, falling back to its position for the singleton pools
    (`header`, `mappings`) that carry none."""
    parts = [record.attrs[name] for name in ("cmper", "inci", "part") if name in record.attrs]
    return "/".join(parts) if parts else str(index)


def _musx_entry(record: Record, index: int) -> dict[str, object]:
    return _record_entry(
        key=_musx_key(record, index),
        fields=walk_fields(record.fields, depth=0),
        offset=None,
        length=None,
    )


def _musx_records(document: EnigmaDocument) -> dict[str, object]:
    """Every record `EnigmaDocument` holds, one depth below the tag-and-count
    view `summarise_document` gives: the full, walked fields of each record.

    Nothing is reimplemented here -- these are the same `Record` objects
    `to_ir.build_score` consumes, just formatted for the report. Unlike the
    `.mus` family, there is no lower, un-translated layer to read instead:
    EnigmaXML's own `Record` model already preserves every record verbatim
    (see `enigma.document`), so this pool *is* the raw view.
    """
    records: dict[str, object] = {}
    for name in _MUSX_POOLS:
        pool_records = getattr(document, name).records
        records[name] = _group_by_tag(
            (record.tag, _musx_entry(record, index)) for index, record in enumerate(pool_records)
        )
    return records


def encode_raw(data: bytes) -> str:
    """Base64, not hex: 4/3 of the payload rather than 2x, and the renderer
    converts to hex on demand for whichever region is in view."""
    return base64.b64encode(data).decode("ascii")


def walk_fields(fields: object, depth: int) -> object:
    """A record's fields, flattened for JSON, bounded at `MAX_FIELD_DEPTH`."""
    if depth >= MAX_FIELD_DEPTH:
        return "<nesting cap reached>"
    if isinstance(fields, Record):
        return walk_fields(fields.fields, depth + 1)
    if isinstance(fields, dict):
        return {str(k): walk_fields(v, depth + 1) for k, v in fields.items()}
    if isinstance(fields, tuple):
        return [walk_fields(item, depth + 1) for item in fields]
    return str(fields)


def _weight(inspection: Inspection) -> int:
    return len(
        json.dumps(
            {
                "score": inspection.score,
                "document": inspection.document,
                "records": inspection.records,
                "raw": inspection.raw,
            }
        )
    )


def apply_budget(inspection: Inspection, limit: int = MAX_JSON_BYTES) -> None:
    """Drop `raw` first, then `records`, naming what went in `notes`.

    Score and document summaries are never dropped: they are small, and they
    are the part a reader needs most.
    """
    if _weight(inspection) <= limit:
        return
    if inspection.raw:
        inspection.raw = {}
        inspection.notes.append(f"raw bytes omitted: the report exceeded its {limit} byte budget")
    if _weight(inspection) <= limit:
        return
    if inspection.records:
        inspection.records = {}
        inspection.notes.append(f"records omitted: the report exceeded its {limit} byte budget")


def _finish(ladder: Ladder, document: EnigmaDocument | None, inspection: Inspection) -> None:
    """Typed rather than ignored: a None document means the ladder already
    stopped, and `run` records the remaining rungs as skipped."""
    if document is None:
        ladder.run("build score", _unreachable)
        ladder.run("export MusicXML", _unreachable)
        return
    inspection.document = summarise_document(document)
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
