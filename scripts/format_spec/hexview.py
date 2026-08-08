"""Hex-view renderer for the format specification document.

A field is described once, as a `Field`, and that same description drives both
the struct table and the byte highlighting -- so a table and its hex dump cannot
disagree about where a field sits.
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from dataclasses import field as dc_field

BYTES_PER_ROW = 16

# Colors cycle per field within a structure. Chosen to stay legible in print:
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
    """The field table, color-keyed to the hex dump above it."""
    rows: list[str] = []
    for i, f in enumerate(struct.fields):
        swatch = f'<span class=swatch style="background:{PALETTE[i % len(PALETTE)]}"></span>'
        span = f"0x{f.offset:02x}" if f.size == 1 else f"0x{f.offset:02x}&#8211;0x{f.end - 1:02x}"
        rows.append(
            f"<tr><td class=sw>{swatch}</td><td class=off>{span}</td>"
            f"<td class=sz>{f.size}</td><td class=ty><code>{html.escape(f.type_)}</code></td>"
            f"<td class=nm><code>{html.escape(f.name)}</code></td>"
            f"<td class=nt>{html.escape(html.unescape(f.note))}</td></tr>"
        )
    return (
        "<table class=struct><thead><tr><th></th><th>offset</th><th>size</th>"
        "<th>type</th><th>field</th><th>meaning</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_c_struct(struct: Struct) -> str:
    """A C-style declaration, in the manner of the Aseprite spec."""
    width = max((len(f.type_) for f in struct.fields), default=8) + 2
    lines = [f"struct {struct.name} {{"]
    for f in struct.fields:
        decl = f"    {f.type_.ljust(width)}{f.name};"
        # The table carries the full meaning; keep the inline comment short so
        # the declaration never wraps in print.
        note = re.sub(r"<[^>]+>", "", html.unescape(f.note))
        note = note if len(note) <= 34 else note[:31].rstrip() + "..."
        lines.append(f"{decl.ljust(42)}// +0x{f.offset:<4x} {note}".rstrip())
    lines.append("};")
    return f"<pre class=cstruct>{html.escape(chr(10).join(lines))}</pre>"


def render_struct(struct: Struct) -> str:
    """Heading, prose, C declaration, field table, and the tinted hex dump."""
    notes = "".join(f"<p class=note>{n}</p>" for n in struct.notes)
    caption = f"<p class=caption>{struct.caption}</p>" if struct.caption else ""
    return (
        f"<div class=structblock>{caption}"
        f"{render_c_struct(struct)}"
        f"{render_struct_table(struct)}"
        f"<p class=hexcap>Example bytes ({len(struct.data)} shown), "
        f"tinted to match the table above.</p>"
        f"{render_hex(struct)}{notes}</div>"
    )


def render_pie(slices: list[tuple[str, int, str]], size: int = 190) -> str:
    """A pie chart as inline SVG, with a legend.

    No charting dependency: this project takes none, and a pie is four lines of
    trigonometry. `slices` is (label, value, color).
    """
    total = sum(v for _, v, _ in slices)
    if total <= 0:
        return ""
    r = size / 2
    paths: list[str] = []
    legend: list[str] = []
    angle = -math.pi / 2  # start at twelve o'clock
    for label, value, color in slices:
        sweep = 2 * math.pi * value / total
        x1, y1 = r + r * math.cos(angle), r + r * math.sin(angle)
        angle += sweep
        x2, y2 = r + r * math.cos(angle), r + r * math.sin(angle)
        large = 1 if sweep > math.pi else 0
        paths.append(
            f'<path d="M{r:.1f},{r:.1f} L{x1:.1f},{y1:.1f} '
            f'A{r:.1f},{r:.1f} 0 {large},1 {x2:.1f},{y2:.1f} Z" '
            f'fill="{color}" stroke="#fff" stroke-width="1.5"/>'
        )
        pct = 100.0 * value / total
        legend.append(
            f'<li><span class=swatch style="background:{color}"></span>'
            f"{html.escape(html.unescape(label))} &mdash; "
            f"<strong>{value:,}</strong> ({pct:.1f}%)</li>"
        )
    return (
        f'<div class=chart><svg viewBox="0 0 {size} {size}" width="{size}" '
        f'height="{size}" role="img">{"".join(paths)}</svg>'
        f"<ul class=chartkey>{''.join(legend)}</ul></div>"
    )


FOOTNOTES: list[str] = []


def cite(text: str) -> str:
    """Register a footnote and return its superscript marker."""
    FOOTNOTES.append(text)
    return f"<sup class=fn>{len(FOOTNOTES)}</sup>"


def render_footnotes() -> str:
    if not FOOTNOTES:
        return ""
    items = "".join(f"<li>{n}</li>" for n in FOOTNOTES)
    return f"<div class=notes><h4>References</h4><ol class=footnotes>{items}</ol></div>"
