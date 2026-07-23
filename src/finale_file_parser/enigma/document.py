"""Parse decoded EnigmaXML into a navigable document model.

Models the format's uniform structure — seven pools of records, each record
recursive (tag, attributes, fields) — not any of its ~191 individual record
types, and not keyed lookup (no fixed key set uniquely identifies a record; see
the design spec). Every record is preserved in document order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from xml.etree.ElementTree import Element, ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from finale_file_parser.errors import FinaleFileError

_FINALE_ROOT = "finale"
_POOLS = ("header", "mappings", "options", "others", "details", "entries", "texts")


class MalformedEnigmaError(FinaleFileError):
    """The bytes are not parseable EnigmaXML, or the root is not <finale>."""


@dataclass(frozen=True)
class Record:
    """One record: its tag, all its attributes verbatim, its own text, and its fields.

    `text` is the element's own direct text, verbatim (e.g. `^fontMus(...)`
    markup is preserved as-is), or "" when it has none. Note: a child
    element's `tail` (text trailing it, before the next sibling) is
    intentionally not modelled — it is empty everywhere in the corpus.

    `fields` maps a child element's local name to its value — a str (scalar
    text) or a Record (nested), and a tuple of either when the tag repeats.
    Nothing is coerced; `attrs` designates no keys.
    """

    tag: str
    attrs: Mapping[str, str]
    text: str
    fields: Mapping[str, str | tuple[str, ...] | Record | tuple[Record, ...]]


@dataclass(frozen=True)
class Pool:
    """Every record of one top-level pool, in document order."""

    records: tuple[Record, ...]

    def of_tag(self, tag: str) -> tuple[Record, ...]:
        """All records with this tag, in document order (possibly none)."""
        return tuple(r for r in self.records if r.tag == tag)


class EnigmaDocument:
    """A parsed EnigmaXML document: its schema version and seven pools."""

    def __init__(self, version: str, pools: Mapping[str, Pool]) -> None:
        self.version = version
        self.header = pools["header"]
        self.mappings = pools["mappings"]
        self.options = pools["options"]
        self.others = pools["others"]
        self.details = pools["details"]
        self.entries = pools["entries"]
        self.texts = pools["texts"]


def _local(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _record_from_element(element: Element) -> Record:
    grouped: dict[str, list[str | Record]] = {}
    for child in element:
        # A child becomes a nested Record if it carries any structure of its
        # own — child elements *or* attributes — not just child elements.
        # A leaf like `<note id="1"/>` has no children but does have an
        # attribute; treating it as scalar text would silently drop `id`,
        # the same class of data loss the pool model as a whole guards
        # against.
        value: str | Record = (
            _record_from_element(child) if (len(child) or child.attrib) else (child.text or "")
        )
        grouped.setdefault(_local(child), []).append(value)
    fields: dict[str, str | tuple[str, ...] | Record | tuple[Record, ...]] = {
        name: (values[0] if len(values) == 1 else tuple(values))  # type: ignore[misc]
        for name, values in grouped.items()
    }
    return Record(
        tag=_local(element), attrs=dict(element.attrib), text=element.text or "", fields=fields
    )


def parse_enigma(xml: bytes) -> EnigmaDocument:
    """Parse decoded EnigmaXML into an EnigmaDocument.

    Raises:
        MalformedEnigmaError: the bytes are not parseable XML, or the root is
            not <finale>.
    """
    try:
        root = fromstring(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise MalformedEnigmaError(f"not parseable EnigmaXML: {exc}") from exc
    if _local(root) != _FINALE_ROOT:
        raise MalformedEnigmaError(f"root is <{_local(root)}>, expected <finale>")

    found: dict[str, list[Record]] = {name: [] for name in _POOLS}
    for pool_element in root:
        name = _local(pool_element)
        if name in found:
            found[name].extend(_record_from_element(r) for r in pool_element)
    pools = {name: Pool(tuple(records)) for name, records in found.items()}
    return EnigmaDocument(version=root.get("version", ""), pools=pools)
