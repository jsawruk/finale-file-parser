"""Hex-view renderer for the format specification document.

A field is described once, as a `Field`, and that same description drives both
the struct table and the byte highlighting -- so a table and its hex dump cannot
disagree about where a field sits.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from dataclasses import field as dc_field

BYTES_PER_ROW = 16

# Colours cycle per field within a structure. Chosen to stay legible in print:
# light enough for black text, distinct in greyscale.
PALETTE = [
    "#ffd9d9",
    "#d9ecff",
    "#dcffd9",
    "#fff3cc",
    "#e8d9ff",
    "#d9fbff",
    "#ffe0f0",
    "#eaeaea",
]


@dataclass(frozen=True)
class Field:
    """One field of a binary structure."""

    offset: int
    size: int
    name: str
    type_: str
    note: str = ""

    @property
    def end(self) -> int:
        return self.offset + self.size


@dataclass
class Struct:
    """A named binary layout, its fields, and one worth of example bytes."""

    name: str
    fields: list[Field]
    data: bytes
    caption: str = ""
    notes: list[str] = dc_field(default_factory=list)

    def field_at(self, index: int) -> tuple[int, Field] | None:
        for i, f in enumerate(self.fields):
            if f.offset <= index < f.end:
                return i, f
        return None


def _printable(b: int) -> str:
    return chr(b) if 32 <= b < 127 else "."


def render_hex(struct: Struct) -> str:
    """A hex dump of `struct.data` with each field's bytes tinted."""
    rows: list[str] = []
    data = struct.data
    for start in range(0, len(data), BYTES_PER_ROW):
        chunk = data[start : start + BYTES_PER_ROW]
        cells: list[str] = []
        chars: list[str] = []
        for i, byte in enumerate(chunk):
            index = start + i
            hit = struct.field_at(index)
            style = ""
            title = ""
            if hit is not None:
                fi, f = hit
                style = f' style="background:{PALETTE[fi % len(PALETTE)]}"'
                title = f' title="{html.escape(f.name)}"'
            cells.append(f"<span class=b{style}{title}>{byte:02x}</span>")
            chars.append(f"<span class=b{style}>{html.escape(_printable(byte))}</span>")
        # pad a short final row so the ASCII column stays aligned
        pad = BYTES_PER_ROW - len(chunk)
        cells.extend(["<span class=b>&#160;&#160;</span>"] * pad)
        rows.append(
            f"<div class=hexrow><span class=off>{start:04x}</span>"
            f"<span class=hex>{' '.join(cells)}</span>"
            f"<span class=asc>{''.join(chars)}</span></div>"
        )
    return f"<div class=hexdump>{''.join(rows)}</div>"


def render_struct_table(struct: Struct) -> str:
    """The field table, colour-keyed to the hex dump above it."""
    rows: list[str] = []
    for i, f in enumerate(struct.fields):
        swatch = f'<span class=swatch style="background:{PALETTE[i % len(PALETTE)]}"></span>'
        span = f"0x{f.offset:02x}" if f.size == 1 else f"0x{f.offset:02x}&#8211;0x{f.end - 1:02x}"
        rows.append(
            f"<tr><td class=sw>{swatch}</td><td class=off>{span}</td>"
            f"<td class=sz>{f.size}</td><td class=ty><code>{html.escape(f.type_)}</code></td>"
            f"<td class=nm><code>{html.escape(f.name)}</code></td>"
            f"<td class=nt>{html.escape(f.note)}</td></tr>"
        )
    return (
        "<table class=struct><thead><tr><th></th><th>offset</th><th>size</th>"
        "<th>type</th><th>field</th><th>meaning</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_c_struct(struct: Struct, byte_order: str = "") -> str:
    """A C-style declaration, in the manner of the Aseprite spec."""
    width = max((len(f.type_) for f in struct.fields), default=8) + 2
    lines = [f"struct {struct.name} {{"]
    for f in struct.fields:
        decl = f"    {f.type_.ljust(width)}{f.name};"
        # The table carries the full meaning; keep the inline comment short so
        # the declaration never wraps in print.
        note = f.note if len(f.note) <= 34 else f.note[:31].rstrip() + "..."
        note = re.sub(r"&[a-z]+;|<[^>]+>", "", note)
        lines.append(f"{decl.ljust(42)}// +0x{f.offset:<4x} {note}".rstrip())
    lines.append("};")
    head = f"// byte order: {byte_order}\n" if byte_order else ""
    return f"<pre class=cstruct>{html.escape(head + chr(10).join(lines))}</pre>"


def render_struct(struct: Struct, byte_order: str = "") -> str:
    """Heading, prose, C declaration, field table, and the tinted hex dump."""
    notes = "".join(f"<p class=note>{n}</p>" for n in struct.notes)
    caption = f"<p class=caption>{struct.caption}</p>" if struct.caption else ""
    return (
        f"<div class=structblock>{caption}"
        f"{render_c_struct(struct, byte_order)}"
        f"{render_struct_table(struct)}"
        f"<p class=hexcap>Example bytes ({len(struct.data)} shown), "
        f"tinted to match the table above.</p>"
        f"{render_hex(struct)}{notes}</div>"
    )
