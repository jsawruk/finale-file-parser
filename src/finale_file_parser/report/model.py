"""Building an `Inspection`: what the parser saw, and how far it got.

**This module reimplements nothing.** It calls the public readers and records
what each returned or raised. Parsing logic of its own would be a second
implementation that could disagree with the real one, and a diagnostic tool that
lies about the parser is worse than no tool.
"""

from __future__ import annotations

import base64
import json
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from defusedxml import ElementTree as DefusedET

from finale_file_parser.enigma.document import EnigmaDocument, Record, parse_enigma
from finale_file_parser.enigma.location import locate_entries
from finale_file_parser.enigma.mus_details import MusDetailRecord, read_mus_details
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.mus_others import OPTIONS_CMPER, MusOther, read_mus_others
from finale_file_parser.enigma.mus_payload import (
    MusPool,
    read_mus_pools,
    read_mus_streams,
)
from finale_file_parser.enigma.mus_rows import MusRowRecord, read_mus_rows
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.formats.layouts import Layout, layout_for
from finale_file_parser.formats.tags import name_for
from finale_file_parser.report.ladder import Ladder, Stage
from finale_file_parser.report.notation import Engraving, engrave
from finale_file_parser.report.summary import (
    DocumentSummary,
    MusicTree,
    ScoreSummary,
    music_tree,
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

MAX_JSON_BYTES = 16 * 1024 * 1024
"""Budget for the embedded JSON. The largest corpus payload is ~500 KB, so no
real document approaches this; it exists to stop a pathological file."""

_MUS_TEXT_STREAM = 3
"""Which payload stream holds the tagged text. See `enigma.mus_document`."""

MAX_FIELD_DEPTH = 8
"""A record's fields may contain records. Bound the walk."""


@dataclass
class Inspection:
    """Everything the report shows about one document."""

    file: dict[str, str]
    stages: list[Stage] = field(default_factory=list)
    stats: ScoreSummary | None = None
    music: MusicTree | None = None
    document: DocumentSummary | None = None
    """Record counts and the reader's own list of gaps.

    Populated for a caller holding an `Inspection`, but no longer embedded in
    the page. Its three parts had each stopped saying anything there: `version`
    is the family the ladder already reports, `pools` duplicates the counts the
    Records tree carries (identical in 40 of 40 `.musx` documents when that was
    measured), and `untranslated` is a module constant -- 941 words of the
    same text in every report, about the reader rather than about the file.
    """

    records: dict[str, object] = field(default_factory=dict)
    tags: dict[str, object] = field(default_factory=dict)
    """What each record tag present is called, and how strongly that is known.

    A tag on its own says nothing: `others / 176 / 1/0` names a record only to
    someone holding the catalogue. Every name carries the evidence behind it,
    because the catalogue's three tiers are not equally strong.
    """

    layouts: dict[str, object] = field(default_factory=dict)
    """The payload layout of each record tag present, where one is known.

    Held per tag rather than per record: every `measSpec` in a document has the
    same layout, and one corpus document carries thousands of them. Attaching
    the spans to each record would have repeated an identical list of five
    fields several thousand times, against a report budget this branch has
    already tripped once.
    """

    byte_order: str = ""
    """How to read a multi-byte field in this document's records.

    Not a constant: a `.mus` container states its own order, and the
    2001-2005 era does occur big-endian. Decoding a `measSpec` width the wrong
    way round gives a number, not an error, so the order has to travel with the
    layouts rather than be assumed by whatever reads them. Empty for a `.musx`,
    which has no bytes to read.
    """

    notation: Engraving | None = None
    """The score engraved as inline SVG pages, when Verovio could lay it out.

    Not in the JSON island with everything else: this is markup, it goes
    straight into the page, and putting half a megabyte of SVG through
    `json.dumps` only to have JavaScript write it back out would cost twice
    and gain nothing.
    """

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
    return {"name": path.name, "size": str(len(data))}


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
        # The same pool `_pools_detail` reports the order from, so the Debug tab
        # and the record pane's decoding cannot disagree about it.
        inspection.byte_order = pools[0].byte_order if pools else ""
        records = ladder.run(
            "read records",
            lambda: _mus_records(target),
            lambda r: {"pools": str(len(r))},
            halt=False,
        )
        if records is not None:
            inspection.records = records
            inspection.tags = _tag_names(records)
            inspection.layouts = _layouts_present(records)
    document = ladder.run("build document", lambda: read_mus_document(target))
    _finish(ladder, document, inspection)


def _musx_stages(ladder: Ladder, target: Path, inspection: Inspection) -> None:
    xml = ladder.run(
        "extract score.dat", lambda: score_xml(target), lambda b: {"bytes": str(len(b))}
    )
    document = ladder.run("parse EnigmaXML", lambda: parse_enigma(xml or b""))
    if document is not None:
        records = ladder.run(
            "read records",
            lambda: _musx_records(document, xml or b""),
            lambda r: {"pools": str(len(r))},
            halt=False,
        )
        if records is not None:
            inspection.records = records
    _finish(ladder, document, inspection)


def _record_entry(
    key: str, fields: object, length: int | None, options: bool = False
) -> dict[str, object]:
    """One record's report shape: identity, walked fields, and how many bytes it
    occupied when that is known.

    `options` marks a record carrying the `0xFFFE` sentinel instead of a key, so
    a renderer can group those together without parsing the key text back
    apart. It is set per record rather than per tag because 94 corpus tags hold
    both: a document-wide default alongside the numbered records it applies to.

    No byte offset. The design called for one, but no reader records where a
    record began -- `MusOther` and friends carry their decoded payload, not
    their position -- so every entry carried `"offset": null`, in every family,
    for every document. Reporting a field that is structurally always empty
    teaches a reader to distrust the rest, so it is gone until the readers can
    answer the question honestly.
    """
    entry: dict[str, object] = {"key": key, "fields": fields, "length": length}
    if options:
        entry["options"] = True
    return entry


def _key(*parts: tuple[str, object]) -> str:
    """A record's identity, spelled out rather than punctuated.

    `1/0` is unreadable without knowing the convention for this pool -- the
    slash means something different in `others` (cmper/part), in `details`
    (cmper1/cmper2/inci) and in a DCL row. Naming each number costs a little
    width and removes the need to know any of that.

    A part with no name renders as its value alone, for the component that is
    not a number at all -- see `_comparator`.
    """
    return "(" + ", ".join(f"{name} {value}".strip() for name, value in parts) + ")"


def _comparator(name: str, value: int) -> tuple[str, object]:
    """A record's leading comparator, or what it means when it is a sentinel.

    `0xFFFE` is not an address. It is what Enigma writes where a key would go
    on a record that has nothing to be keyed by -- a document-wide option (see
    `mus_others.OPTIONS_CMPER`). Every occurrence across the corpus is in this
    leading position: 3,771 in `others`, 828 in DCL rows, 180 in `details`
    under `cmper1`, and never in a `cmper2`, `part` or `inci`.

    Printing it as `cmper 65534` invites reading it as a very high measure or
    staff number. Worse, a document carries one such record under each of
    around 99 different tags, so a tree of them reads as the same row repeated
    when in fact each is a different record.
    """
    if value == OPTIONS_CMPER:
        return ("", "document options")
    return (name, value)


def _mus_other_entry(record: MusOther) -> dict[str, object]:
    # No cmper or part here: they are the key, stated once above. Repeating
    # them underneath said nothing a reader could not already see, and could
    # never differ from it.
    fields = walk_fields(
        {"payload": encode_raw(record.payload), "extra": encode_raw(record.extra)},
        depth=0,
    )
    return _record_entry(
        key=_key(_comparator("cmper", record.cmper), ("part", record.part)),
        fields=fields,
        length=len(record.payload) + len(record.extra),
        options=record.cmper == OPTIONS_CMPER,
    )


def _mus_detail_entry(record: MusDetailRecord) -> dict[str, object]:
    fields = walk_fields(
        {"payload": encode_raw(record.payload), "extra": encode_raw(record.extra)},
        depth=0,
    )
    return _record_entry(
        key=_key(
            _comparator("cmper1", record.cmper1),
            ("cmper2", record.cmper2),
            ("inci", record.inci),
        ),
        fields=fields,
        length=len(record.payload) + len(record.extra),
        options=record.cmper1 == OPTIONS_CMPER,
    )


def _mus_row_entry(record: MusRowRecord) -> dict[str, object]:
    # Nothing but the bytes. `incidences` -- how many 16-byte rows the reader
    # joined to make this payload -- is derivable from the payload itself, at
    # exactly `len(payload) / 12` for an `others` row and `/ 10` for a details
    # one, checked across 107,652 corpus records. A number the reader can work
    # out from what is already on screen is not worth a line of its own.
    fields = walk_fields({"payload": encode_raw(record.payload)}, depth=0)
    return _record_entry(
        key=_key(_comparator("cmper", record.cmper), ("cmper2", record.cmper2)),
        fields=fields,
        length=len(record.payload),
        options=record.cmper == OPTIONS_CMPER,
    )


def _group_by_tag(
    items: Iterable[tuple[str, dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    """Every record, grouped under its tag, in the order the reader returned them."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for tag, entry in items:
        grouped.setdefault(tag, []).append(entry)
    return grouped


def _mus_records(target: Path) -> dict[str, object]:
    """The `others`/`details` pools' own records, read raw rather than via the
    built `EnigmaDocument`.

    `mus_document` only translates the handful of tags it currently
    understands (see `UNTRANSLATED`); a tag it drops on the floor is exactly
    what a diagnostic report needs to still show, so this depth calls the raw
    pool readers directly instead of reusing the "build document" stage.

    Two eras, two readers (see `enigma.mus_rows`). Era detection lives here,
    not in the caller: the 2011-era readers are tried first, each on its own,
    since either can legitimately succeed while the other fails to recognise
    its pool. Only when *neither* does is `read_mus_rows` tried for the
    2001-2005 era, and only if that also raises does this function raise --
    deliberately left unguarded, so `_mus_stages` running it through
    `Ladder.run(..., halt=False)` is what turns a `FinaleFileError` into a
    REFUSED stage and anything else (a bug in the entry-building below, not
    just the reading) into a CRASHED one, without stopping the pipeline for
    either.
    """
    others: tuple[MusOther, ...] | None = None
    details: tuple[MusDetailRecord, ...] | None = None
    try:
        others = read_mus_others(target)
    except FinaleFileError:
        others = None
    try:
        details = read_mus_details(target)
    except FinaleFileError:
        details = None

    records: dict[str, object] = {}
    if others is not None:
        records["others"] = _group_by_tag((str(r.tag), _mus_other_entry(r)) for r in others)
    if details is not None:
        records["details"] = _group_by_tag((str(r.tag), _mus_detail_entry(r)) for r in details)
    if others is not None or details is not None:
        _add_texts(records, target)
        return records

    rows = read_mus_rows(target)  # a FinaleFileError here is left to propagate
    records["others"] = _group_by_tag((r.tag, _mus_row_entry(r)) for r in rows.others.values())
    records["details"] = _group_by_tag((r.tag, _mus_row_entry(r)) for r in rows.details.values())
    _add_texts(records, target)
    return records


def _add_texts(records: dict[str, object], target: Path) -> None:
    """The text stream, if this document has one. Never fatal: a document whose
    binary pools read perfectly must not lose them to a text stream that does
    not."""
    try:
        texts = _mus_texts(target)
    except (FinaleFileError, OSError, UnicodeError):
        return
    if texts:
        records["texts"] = texts


_TEXT_SECTION = re.compile(r"\^([A-Za-z]\w*)\((\d*)\)(.*?)\^end", re.DOTALL)
"""One tagged section of the `.mus` text stream: `^expression(3)...^end`.

Every marker, not the three `mus_document` translates. That reader takes
`verse`/`chorus`/`section` because they are the lyrics it can place in a score;
the stream also holds `^block` (staff names, titles), `^expression` (markings,
including dynamics) and `^smartshape` (glissandi, octave lines), none of which
reach a `Score` today. A diagnostic report showing only the translated three
said a document had one text record when it had several hundred.
"""


def _mus_texts(target: Path) -> dict[str, list[dict[str, object]]]:
    """The `.mus` text stream, section by section, grouped by marker.

    A `.mus` keeps this as ETF tagged text rather than as binary records, so it
    is read straight out of the stream and never appeared in the records tree at
    all -- the one major structure of the file the inspector could not see. It
    is where staff names live, and expression text, and the font each is set in.

    Text rather than bytes, so these entries carry `text` where a binary record
    carries `fields`. The markup is kept: `^font(Font0,8191)` is the half of an
    expression that says what its character means.
    """
    streams = read_mus_streams(target)
    if len(streams) <= _MUS_TEXT_STREAM:
        return {}
    body = streams[_MUS_TEXT_STREAM].decode("cp1252", errors="replace")
    grouped: dict[str, list[dict[str, object]]] = {}
    for match in _TEXT_SECTION.finditer(body):
        marker, number, section = match.group(1), match.group(2), match.group(0)
        grouped.setdefault(marker, []).append(
            {
                "key": _key(("number", number)) if number else "(unnumbered)",
                "text": section,
                "length": len(section),
            }
        )
    return grouped


def _layout_entry(layout: Layout) -> dict[str, object]:
    """One layout, flattened for the report.

    Offsets and sizes only -- no decoded values. The bytes are already in the
    record; a reader of this JSON holds both and can decode one from the other,
    whereas writing the values here would state the payload twice.
    """
    return {
        "record": layout.record,
        "struct": layout.name,
        "stride": layout.stride,
        "fields": [
            {
                "offset": f.offset,
                "size": f.size,
                "name": f.name,
                "type": f.type_,
                "note": f.note,
            }
            for f in layout.fields
        ],
    }


def _tag_names(records: dict[str, object]) -> dict[str, object]:
    """What each tag in `records` is called, where this project can say.

    Separate from the layouts: most named tags have no decoded payload, and a
    few decoded payloads sit under tags whose offsets the reader computes. The
    two questions -- what is this record, and what do its bytes mean -- have
    different answers and different evidence.
    """
    named: dict[str, object] = {}
    for pool, tags in records.items():
        if not isinstance(tags, dict):
            continue
        found: dict[str, object] = {}
        for tag in tags:
            entry = name_for(pool, str(tag))
            if entry is not None:
                found[str(tag)] = {
                    "name": entry.name,
                    "description": entry.description,
                    # How strongly the name is known. Not rendered as prose on
                    # every record -- the specification's tag tables state each
                    # tier in full -- but carried for anything reading the
                    # report as data, where a `matched` name must not be taken
                    # for a decoded one.
                    "tier": entry.tier,
                    # Where the record's name starts, for the tags that carry
                    # one. The renderer reads the NUL-terminated string off the
                    # bytes it already has rather than being handed a copy.
                    **({"textAt": entry.text_at} if entry.text_at is not None else {}),
                    **({"textStride": entry.text_stride} if entry.text_stride is not None else {}),
                }
        if found:
            named[pool] = found
    return named


def _layouts_present(records: dict[str, object]) -> dict[str, object]:
    """The layout of every tag in `records` that has one, by pool and tag.

    Two of the nine known layouts are left out, and the omission is the point.
    A `frameSpec` keeps its entry pair in its *last* 12-byte slot and a `gfhold`
    puts its frame slots at an era base of 4 or 6, so for both of them the
    reader works out where a field sits from the record in front of it. Laying
    the nominal offsets over those bytes would tint the wrong ones and decode
    numbers that look entirely reasonable -- the failure this format is most
    generous with. Showing plain, untinted hex says "not decoded", which is
    true; showing the wrong span says something false.
    """
    present: dict[str, object] = {}
    for pool, tags in records.items():
        if not isinstance(tags, dict):
            continue
        found: dict[str, object] = {}
        for tag in tags:
            layout = layout_for(pool, str(tag))
            if layout is not None and not layout.computed:
                found[str(tag)] = _layout_entry(layout)
        if found:
            present[pool] = found
    return present


_IDENTITY_ATTRS = ("cmper", "cmper1", "cmper2", "entnum", "number", "type", "inci", "part")
"""Every attribute that names *which* record this is, widest key first.

Not every record is keyed the same way. `measSpec` uses `cmper`; `gfhold` uses
`cmper1`/`cmper2` (staff and measure); a details record can hang off an
`entnum`; a text is numbered. `inci` and `part` qualify whichever of those came
before, so they sort last -- which makes a details key read `cmper1/cmper2/inci`,
the same shape `_mus_detail_entry` has always produced for the `.mus` path.

Ordered rather than taken from `record.attrs` so the key does not change when a
reader happens to emit attributes in a different order.
"""


def _musx_key(record: Record, index: int) -> str:
    """A record's identity for the report: every identity attribute it carries,
    falling back to its position when it carries none.

    The fallback is for genuinely anonymous records -- the singleton `header`
    and `mappings` pools. It used to catch far more than that: keying on only
    `cmper`/`inci`/`part` missed `cmper1`/`cmper2`/`entnum`/`number`/`type`
    entirely, so 2,263 of one corpus archive's 5,880 records were labelled by
    array position or, where an `inci` was present, by the `inci` alone.
    """
    parts = [(name, record.attrs[name]) for name in _IDENTITY_ATTRS if name in record.attrs]
    return _key(*parts) if parts else _key(("position", index))


def _musx_entry(record: Record, index: int, source: str = "") -> dict[str, object]:
    entry = _record_entry(
        key=_musx_key(record, index),
        fields=walk_fields(record.fields, depth=0),
        length=None,
    )
    # A .musx record has no undecoded bytes -- it arrived as XML -- so the
    # report shows the record's own XML where a .mus shows hex.
    if source:
        entry["xml"] = source
        # The XML *is* the record here, so the walked fields would restate it:
        # same names, same values, same nesting, one line apart on screen. On
        # the largest corpus document carrying both put the payload over the
        # report's budget, which dropped the records entirely -- so the pane
        # that gained the XML would have lost everything. A .mus keeps its
        # fields, because there they decode bytes that are otherwise opaque.
        entry.pop("fields", None)
    return entry


def _musx_records(document: EnigmaDocument, xml: bytes = b"") -> dict[str, object]:
    """Every record `EnigmaDocument` holds, one depth below the tag-and-count
    view `summarise_document` gives: the full, walked fields of each record.

    Nothing is reimplemented here -- these are the same `Record` objects
    `to_ir.build_score` consumes, just formatted for the report. Unlike the
    `.mus` family, there is no lower, un-translated layer to read instead:
    EnigmaXML's own `Record` model already preserves every record verbatim
    (see `enigma.document`), so this pool *is* the raw view.
    """
    source = _record_source(xml)
    records: dict[str, object] = {}
    for name in _MUSX_POOLS:
        pool_records = getattr(document, name).records
        fragments = source.get(name, [])
        records[name] = _group_by_tag(
            (
                record.tag,
                _musx_entry(record, index, fragments[index] if index < len(fragments) else ""),
            )
            for index, record in enumerate(pool_records)
        )
    return records


def _record_source(xml: bytes) -> dict[str, list[str]]:
    """Each record's own XML, per pool, in the order `parse_enigma` returns them.

    The report shows a `.musx` record's XML rather than a hex dump, because
    EnigmaXML arrives as XML and has no undecoded form. Re-serialising the
    parsed `Record` was not good enough: it is faithful in content but it is not
    the fragment the file holds. This serialises the source element itself.

    Parsed with the same defused parser the reader uses -- untrusted input gets
    no second, softer path -- and the namespace prefixes ElementTree reintroduces
    on output are stripped, since EnigmaXML declares one default namespace and
    `ns0:` on every tag is noise rather than information.

    The stripping happens **once, on the tree**, rather than per fragment. It
    used to run two regular expressions over every record's serialised text: on
    the largest documents that is upwards of seven thousand records each, and it
    made this function 58% of the cost of inspecting a `.musx`. Renaming the
    tags before serialising produces byte-identical output -- ElementTree only
    writes a prefix for a tag that still carries one -- and takes about a
    quarter off, for the corpus sweep and for anyone generating a report.
    """
    if not xml:
        return {}
    try:
        root = DefusedET.fromstring(xml)
    except Exception:  # pragma: no cover - parse_enigma already accepted this
        return {}
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[-1]
    out: dict[str, list[str]] = {}
    for pool in root:
        if pool.tag not in _MUSX_POOLS:
            continue
        out[pool.tag] = [_fragment(child) for child in pool]
    return out


def _fragment(element: ET.Element) -> str:
    """One record's XML, indented two spaces a level.

    The elements, attributes and values are the file's own -- this serialises
    the source element, it does not rebuild one from the parse. Only the
    whitespace between them is this report's, and it has to be: EnigmaXML is
    written both pretty-printed and compact, so left verbatim the same record
    would render as an indented block from one file and as a single unreadable
    line from another. Re-indenting makes the two look the same, which is what
    someone comparing them needs.

    `ET.indent` only touches elements that have children, so a record whose text
    is its content -- a text pool's markup, say -- keeps that text exactly.

    Indented per record rather than once over the whole tree: a record indented
    in place inherits its depth in the document, so every fragment would open
    three levels in. Each one has to start at column zero to be readable on its
    own.

    The namespace is already gone by here -- `_record_source` strips it from the
    tree before calling this.
    """
    ET.indent(element, space="  ")
    return ET.tostring(element, encoding="unicode").strip()


def encode_raw(data: bytes) -> str:
    """Base64, not hex: 4/3 of the payload rather than 2x, and the renderer
    converts to hex on demand for whichever region is in view -- one 4 KB page,
    which the reader moves through the pool with the report's own previous/next
    controls. The whole pool is embedded either way; only the size of the hex on
    screen at once is bounded."""
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
    """The size of everything the report embeds, not only the two depths
    `apply_budget` can drop: `file`, `stages` and `notes` are always small, but
    the budget is on the embedded JSON as a whole, so they count too."""
    return len(
        json.dumps(
            {
                "file": inspection.file,
                "stages": [asdict(s) for s in inspection.stages],
                "stats": inspection.stats,
                "music": inspection.music,
                "records": inspection.records,
                "tags": inspection.tags,
                "layouts": inspection.layouts,
                "byteOrder": inspection.byte_order,
                "notes": inspection.notes,
            }
        )
    )


def apply_budget(inspection: Inspection, limit: int = MAX_JSON_BYTES) -> None:
    """Drop `records` first, then the music tree, naming what went in `notes`.

    The stats and document summaries are never dropped: they are small, and they
    are the part a reader needs most. Of the two that can go, `records` goes
    first: it is the primary evidence, but it is also far the largest, and the
    music tree is the view a reader is most likely to have opened the report
    for.
    """
    if _weight(inspection) <= limit:
        return
    if inspection.records:
        inspection.records = {}
        # The names and layouts describe records that are no longer here, so
        # they go with them rather than being left behind describing nothing.
        inspection.tags = {}
        inspection.layouts = {}
        inspection.notes.append(f"records omitted: the report exceeded its {limit} byte budget")
    if _weight(inspection) <= limit:
        return
    if inspection.music:
        inspection.music = None
        inspection.notes.append(f"music tree omitted: the report exceeded its {limit} byte budget")


def _finish(ladder: Ladder, document: EnigmaDocument | None, inspection: Inspection) -> None:
    """Typed rather than ignored: a None document means the ladder already
    stopped, and `run` records the remaining rungs as skipped."""
    if document is None:
        ladder.run("build score", _unreachable)
        ladder.run("export MusicXML", _unreachable)
        ladder.run("engrave notation", _unreachable)
        return
    inspection.document = summarise_document(document)
    score = ladder.run("build score", lambda: build_score(document))
    if score is None:
        ladder.run("export MusicXML", _unreachable)
        ladder.run("engrave notation", _unreachable)
        return
    inspection.stats = summarise_score(score)
    inspection.music = music_tree(score, _mirrored_cells(document))
    ladder.run(
        "export MusicXML",
        lambda: to_musicxml(score),
        lambda data: {"bytes": str(len(data))},
    )
    # `halt=False`: engraving is the last rung and the one most likely to fail
    # on a document the rest of the pipeline handled, since it depends on a
    # third-party layout engine. A report whose notation could not be drawn
    # still has its music tree, its records and its ladder, and the stage says
    # which of those happened.
    engraving = ladder.run(
        "engrave notation",
        lambda: engrave(score),
        lambda e: {"pages": str(len(e.pages)), "of": str(e.total)},
        halt=False,
    )
    if engraving is not None:
        inspection.notation = engraving


def _mirrored_cells(document: EnigmaDocument) -> dict[tuple[int, int, int], list[int]]:
    """Which `(staff, measure, layer)` cells hold entries that sound elsewhere too.

    A Finale *mirror* is one staff displaying another's music: the file stores
    one entry span that two `gfhold` records both name, and marks neither as the
    copy. `locate_entries` returns the placements as peers, so a mirrored entry
    simply has more than one of them.

    Each cell maps to the *other* staves showing the same entries -- a plain
    statement of fact that names no original. Empty for the overwhelming
    majority of documents: one corpus document in 639 has a mirror that reaches
    a score.

    Never raises. `build_score` has already resolved this document by the time
    this runs, so a failure here would be a surprise, and a surprise in an
    annotation must not cost the report the score it already has.
    """
    try:
        located = locate_entries(document)
    except FinaleFileError:  # pragma: no cover - build_score resolved it moments ago
        return {}
    cells: dict[tuple[int, int, int], set[int]] = {}
    for places in located.values():
        if len(places) < 2:
            continue
        staves = {place.staff for place in places}
        for place in places:
            here = cells.setdefault((place.staff, place.measure, place.layer), set())
            here.update(staves - {place.staff})
    return {cell: sorted(others) for cell, others in cells.items()}


def _unreachable() -> None:
    """Never called: `Ladder.run` short-circuits once stopped, and records the
    stage as skipped without invoking it."""
    raise AssertionError("ladder should have stopped")
