"""Resolve the human-readable text a score carries: staff names and file info.

Enigma does not store a staff's name on the staff. `staffSpec.fullName` holds a
number, and reaching the string takes two hops:

    staffSpec.fullName  ->  others.textBlock[cmper]  ->  textID
                        ->  texts.blockText[number]  ->  the text itself

Going straight from `fullName` to `blockText` finds nothing -- all 24 named staves
in the sampled corpus fail that way, because the numbers belong to different
spaces.

The text itself is Enigma's tagged markup (`^fontid(9)^size(12)^nfx(0)Voice`),
which also carries *inserts* -- `^title()`, `^partname()` -- that are placeholders
resolved at render time rather than literal text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from finale_file_parser.enigma.document import EnigmaDocument

__all__ = ["StaffNames", "file_info", "plain_text", "staff_names", "text_block"]

_MARKUP = re.compile(r"\^[A-Za-z]+\([^)]*\)")
"""An Enigma text command as EnigmaXML writes it: a caret, a name, and
parenthesised arguments."""

_BINARY_MARKUP = re.compile(r"\^[\u0080-\u00ff].{4}", re.DOTALL)
"""The same command in the dialect a `.mus` text stream uses: a caret, a
high-byte opcode, and four argument bytes.

A `.mus` writes `^\x85\x01\x01\x02\x08` where a `.musx` writes `^size(13)`.
Both are commands rather than content, so both are stripped. The pattern is
deliberately narrow -- caret, one byte in 0x80-0xFF, then exactly four -- so a
caret in real lyric or title text is left alone.
"""

_TEXT_BLOCK = "textBlock"
_BLOCK_TEXT = "blockText"
_FILE_INFO = "fileInfo"
_STAFF_SPEC = "staffSpec"


@dataclass(frozen=True)
class StaffNames:
    """A staff's names, as far as the document supplies them."""

    full: str = ""
    abbreviated: str = ""


def plain_text(markup: str) -> str:
    """Strip Enigma's text commands, leaving the literal text.

    Inserts such as `^title()` disappear along with formatting commands, since
    both are commands rather than content. A block that is *only* inserts
    therefore yields an empty string -- which is the correct answer: it has no
    literal text of its own.

    Handles both dialects: EnigmaXML's `^name(args)` and the binary
    `^<opcode><4 bytes>` a `.mus` text stream uses.
    """
    return _BINARY_MARKUP.sub("", _MARKUP.sub("", markup)).strip()


def text_block(document: EnigmaDocument, number: int) -> str | None:
    """Follow a text-block number to its text, or None if it does not resolve."""
    block = document.others.get(_TEXT_BLOCK, number)
    if block is None:
        return None
    text_id = block.fields.get("textID")
    if not isinstance(text_id, str):
        return None
    for record in document.texts.of_tag(_BLOCK_TEXT):
        if record.attrs.get("number") == text_id:
            return record.text
    return None


def _named(document: EnigmaDocument, record_field: object) -> str:
    if not isinstance(record_field, str):
        return ""
    try:
        number = int(record_field)
    except ValueError:
        return ""
    return plain_text(text_block(document, number) or "")


def staff_names(document: EnigmaDocument) -> dict[int, StaffNames]:
    """Each staff's names, keyed by staff number.

    Staves without a name are absent rather than given a placeholder: inventing
    one here would hide the distinction between "unnamed" and "named blank", and
    the caller is better placed to choose a fallback. In the sampled corpus only
    24 of 84 staves carry a name at all.
    """
    out: dict[int, StaffNames] = {}
    for record in document.others.of_tag(_STAFF_SPEC):
        if "part" in record.attrs:
            continue
        names = StaffNames(
            full=_named(document, record.fields.get("fullName")),
            abbreviated=_named(document, record.fields.get("abbrvName")),
        )
        if names.full or names.abbreviated:
            out[int(record.attrs["cmper"])] = names
    return out


def file_info(document: EnigmaDocument) -> dict[str, str]:
    """Title, composer, copyright and so on, keyed by their `type` attribute.

    These are literal strings in the texts pool rather than pointers, so no
    indirection applies. Values are returned verbatim -- they are content, not
    markup.
    """
    out: dict[str, str] = {}
    for record in document.texts.of_tag(_FILE_INFO):
        kind = record.attrs.get("type")
        if kind and record.text:
            out[kind] = record.text
    return out
