"""Parse decoded EnigmaXML into a navigable document model.

Models the format's uniform structure — seven pools of records, each record
recursive (tag, attributes, fields) — not any of its ~191 individual record
types. Every record is preserved in document order, and five of the seven
pools (`options`, `others`, `details`, `entries`, `texts`) additionally offer
O(1) keyed lookup by each record's identity; see the design spec for the
per-pool identity table.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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

    @property
    def record(self) -> Record | None:
        """The single record of a singleton pool (header/mappings), or None."""
        return self.records[0] if self.records else None


def _key(value: int | str | None, default: str | None = None) -> str | None:
    """Normalize one identity component to `str`, matching stored-attribute vs.

    call-argument identity byte-for-byte. `default` is `"0"` for `inci`
    (absent inci means inci=0, Finale's default, verified across the
    corpus — absent-inci and inci="0" never coexist) and `None` for every
    other identity attribute (absent means "not this key", or "the score
    record" for `part`).
    """
    return default if value is None else str(value)


@dataclass(frozen=True)
class OptionsPool(Pool):
    """`options`: one record per option type, keyed by tag alone."""

    _by_tag: dict[str, Record] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_tag: dict[str, Record] = {}
        for r in self.records:
            if r.tag in by_tag:
                raise MalformedEnigmaError(f"duplicate options identity: tag={r.tag!r}")
            by_tag[r.tag] = r
        object.__setattr__(self, "_by_tag", by_tag)

    def get(self, tag: str) -> Record | None:
        """The record for this option type, or None."""
        return self._by_tag.get(tag)


@dataclass(frozen=True)
class OthersPool(Pool):
    """`others`: keyed by tag + cmper + inci (default 0) + part (default: score record)."""

    _by_id: dict[tuple[str, str | None, str | None, str | None], Record] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _by_cmper: dict[tuple[str, str | None], tuple[Record, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        by_id: dict[tuple[str, str | None, str | None, str | None], Record] = {}
        by_cmper: dict[tuple[str, str | None], list[Record]] = {}
        for r in self.records:
            cmper = _key(r.attrs.get("cmper"))
            inci = _key(r.attrs.get("inci"), "0")
            part = _key(r.attrs.get("part"))
            key = (r.tag, cmper, inci, part)
            if key in by_id:
                raise MalformedEnigmaError(f"duplicate others identity: {key}")
            by_id[key] = r
            by_cmper.setdefault((r.tag, cmper), []).append(r)
        object.__setattr__(self, "_by_id", by_id)
        object.__setattr__(self, "_by_cmper", {k: tuple(v) for k, v in by_cmper.items()})

    def get(
        self,
        tag: str,
        cmper: int | str,
        inci: int | str = 0,
        part: int | str | None = None,
    ) -> Record | None:
        """The one exact record for this identity, or None.

        Omitting `part` addresses the score record; passing it addresses a
        specific linked-part variant (Finale's `measSpec` case).
        """
        key = (tag, _key(cmper), _key(inci, "0"), _key(part))
        return self._by_id.get(key)

    def all_with(self, tag: str, cmper: int | str) -> tuple[Record, ...]:
        """Every record sharing this cmper — score plus all part variants — in document order."""
        return self._by_cmper.get((tag, _key(cmper)), ())


@dataclass(frozen=True)
class DetailsPool(Pool):
    """`details`: keyed by tag + (cmper1+cmper2 or entnum) + inci (default 0) + part."""

    _by_id: dict[tuple[str, str | None, str | None, str | None, str | None, str | None], Record] = (
        field(default_factory=dict, init=False, repr=False, compare=False)
    )
    _by_cmper_pair: dict[tuple[str, str | None, str | None], tuple[Record, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        by_id: dict[
            tuple[str, str | None, str | None, str | None, str | None, str | None], Record
        ] = {}
        by_pair: dict[tuple[str, str | None, str | None], list[Record]] = {}
        for r in self.records:
            cmper1 = _key(r.attrs.get("cmper1"))
            cmper2 = _key(r.attrs.get("cmper2"))
            entnum = _key(r.attrs.get("entnum"))
            inci = _key(r.attrs.get("inci"), "0")
            part = _key(r.attrs.get("part"))
            key = (r.tag, cmper1, cmper2, entnum, inci, part)
            if key in by_id:
                raise MalformedEnigmaError(f"duplicate details identity: {key}")
            by_id[key] = r
            by_pair.setdefault((r.tag, cmper1, cmper2), []).append(r)
        object.__setattr__(self, "_by_id", by_id)
        object.__setattr__(self, "_by_cmper_pair", {k: tuple(v) for k, v in by_pair.items()})

    def get(
        self,
        tag: str,
        cmper1: int | str,
        cmper2: int | str,
        inci: int | str = 0,
        part: int | str | None = None,
    ) -> Record | None:
        """The one exact record for this cmper-pair identity, or None."""
        key = (tag, _key(cmper1), _key(cmper2), None, _key(inci, "0"), _key(part))
        return self._by_id.get(key)

    def for_entry(
        self,
        tag: str,
        entnum: int | str,
        inci: int | str = 0,
        part: int | str | None = None,
    ) -> Record | None:
        """The one exact record for this entnum-keyed identity, or None (e.g. `perfData`)."""
        key = (tag, None, None, _key(entnum), _key(inci, "0"), _key(part))
        return self._by_id.get(key)

    def all_with(self, tag: str, cmper1: int | str, cmper2: int | str) -> tuple[Record, ...]:
        """Every record sharing this cmper pair — score plus all part variants — in order."""
        return self._by_cmper_pair.get((tag, _key(cmper1), _key(cmper2)), ())


@dataclass(frozen=True)
class EntriesPool(Pool):
    """`entries`: single tag `entry`, keyed by `entnum` alone."""

    _by_entnum: dict[str | None, Record] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        by_entnum: dict[str | None, Record] = {}
        for r in self.records:
            entnum = _key(r.attrs.get("entnum"))
            if entnum in by_entnum:
                raise MalformedEnigmaError(f"duplicate entries identity: entnum={entnum!r}")
            by_entnum[entnum] = r
        object.__setattr__(self, "_by_entnum", by_entnum)

    def get(self, entnum: int | str) -> Record | None:
        """The entry with this entnum, or None."""
        return self._by_entnum.get(_key(entnum))


@dataclass(frozen=True)
class TextsPool(Pool):
    """`texts`: keyed by tag + number xor type."""

    _by_id: dict[tuple[str, str | None, str | None], Record] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        by_id: dict[tuple[str, str | None, str | None], Record] = {}
        for r in self.records:
            number = _key(r.attrs.get("number"))
            type_ = _key(r.attrs.get("type"))
            key = (r.tag, number, type_)
            if key in by_id:
                raise MalformedEnigmaError(f"duplicate texts identity: {key}")
            by_id[key] = r
        object.__setattr__(self, "_by_id", by_id)

    def get(
        self, tag: str, number: int | str | None = None, type: int | str | None = None
    ) -> Record | None:
        """The one exact record for this tag + number-or-type identity, or None."""
        key = (tag, _key(number), _key(type))
        return self._by_id.get(key)


class EnigmaDocument:
    """A parsed EnigmaXML document: its schema version and seven pools."""

    def __init__(
        self,
        version: str,
        header: Pool,
        mappings: Pool,
        options: OptionsPool,
        others: OthersPool,
        details: DetailsPool,
        entries: EntriesPool,
        texts: TextsPool,
    ) -> None:
        self.version = version
        self.header = header
        self.mappings = mappings
        self.options = options
        self.others = others
        self.details = details
        self.entries = entries
        self.texts = texts


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

    return EnigmaDocument(
        version=root.get("version", ""),
        header=Pool(tuple(found["header"])),
        mappings=Pool(tuple(found["mappings"])),
        options=OptionsPool(tuple(found["options"])),
        others=OthersPool(tuple(found["others"])),
        details=DetailsPool(tuple(found["details"])),
        entries=EntriesPool(tuple(found["entries"])),
        texts=TextsPool(tuple(found["texts"])),
    )
