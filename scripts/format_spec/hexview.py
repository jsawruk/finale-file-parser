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

from finale_file_parser.formats.layouts import PALETTE, Field, Layout

__all__ = ["PALETTE", "Field", "Layout", "Struct"]

BYTES_PER_ROW = 16


@dataclass
class Struct:
    """A named binary layout, its fields, and one worth of example bytes.

    The example bytes and the prose are the document's own: they exist to
    explain a layout, not to describe one. A record type's layout itself comes
    from `finale_file_parser.formats.layouts`, via `Struct.of`, so this document
    and the parser cannot disagree about where a field sits. Container-level
    structures -- a file header, a row framing -- are not record payloads and so
    are declared here directly.
    """

    name: str
    fields: list[Field]
    data: bytes
    caption: str = ""
    notes: list[str] = dc_field(default_factory=list)

    @classmethod
    def of(
        cls,
        layout: Layout,
        data: bytes,
        caption: str = "",
        notes: list[str] | None = None,
        extra: list[Field] | None = None,
    ) -> Struct:
        """A struct drawing its fields from `layout`.

        `extra` appends fields that illustrate rather than describe -- a second
        array slot shown so the reader can see the stride, for instance, which
        belongs in the document and not in a layout a decoder consults.
        """
        return cls(
            name=layout.name,
            fields=[*layout.fields, *(extra or [])],
            data=data,
            caption=caption,
            notes=notes or [],
        )

    def field_at(self, index: int) -> tuple[int, Field] | None:
        """Which field claims byte `index`; see `Layout.field_at`, which this
        matches so the document and the inspector tint the same bytes.

        A tail claims the rest of the example bytes, which is what it does in a
        real payload too.
        """
        for i, f in enumerate(self.fields):
            if f.offset <= index and (f.is_tail or index < f.end):
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
        if f.is_tail:
            # No end to name: the field runs to the end of whatever payload this
            # is. Writing `f.end - 1` here would print a span that ends before it
            # begins.
            span = f"0x{f.offset:02x}&#8211;end"
            size = "var"
        else:
            span = (
                f"0x{f.offset:02x}" if f.size == 1 else f"0x{f.offset:02x}&#8211;0x{f.end - 1:02x}"
            )
            size = str(f.size)
        rows.append(
            f"<tr><td class=sw>{swatch}</td><td class=off>{span}</td>"
            f"<td class=sz>{size}</td><td class=ty><code>{html.escape(f.type_)}</code></td>"
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


# Treble staff geometry. Lines are five units apart in diatonic steps, so one
# step is half a line-gap; F5 is the top line and E4 the bottom.
_STAFF_TOP = 12.0
_STEP = 4.0
_TREBLE_TOP_STEP = 38  # diatonic index of F5 (5 * 7 + 3), counting C0 = 0

_LETTERS = "CDEFGAB"


def _diatonic(name: str) -> int:
    """Diatonic index of a note like 'C4' or 'F#4', counting C0 as 0."""
    letter = name[0].upper()
    octave = int(name[-1])
    return octave * 7 + _LETTERS.index(letter)


def render_staff(notes: list[tuple[str, str]], sharps: int, caption: str) -> str:
    """A short treble staff with `notes` as (pitch, label-under-the-note).

    `sharps` is how many sharps the key signature carries. Drawn as plain SVG:
    five lines with ellipses on them are enough to show which pitch a number
    means, without invoking the report's notation engraver for this small diagram.
    """
    left, gap, width = 62.0, 34.0, 0.0
    width = left + gap * (len(notes) + 1)
    lines = "".join(
        f'<line x1="8" y1="{_STAFF_TOP + i * _STEP * 2:.1f}" x2="{width - 8:.1f}" '
        f'y2="{_STAFF_TOP + i * _STEP * 2:.1f}" stroke="#222" stroke-width="0.9"/>'
        for i in range(5)
    )
    # key signature sharps, in the usual F C G D A E B order, at their staff rows
    sharp_rows = [_diatonic(p) for p in ("F5", "C5", "G5", "D5", "A4", "E5", "B4")]
    keysig = "".join(
        f'<text x="{26 + n * 7.5:.1f}" '
        f'y="{_STAFF_TOP + (_TREBLE_TOP_STEP - sharp_rows[n]) * _STEP + 3:.1f}" '
        f'font-size="13" fill="#222">&#9839;</text>'
        for n in range(min(sharps, 7))
    )
    heads, labels, ledgers = "", "", ""
    for i, (pitch, label) in enumerate(notes):
        x = left + gap * (i + 1)
        # an accidental written before the note, if the pitch names one
        acc = {"#": "&#9839;", "n": "&#9838;", "x": "&#119082;", "b": "&#9837;"}
        mark = acc.get(pitch[1]) if len(pitch) > 2 and pitch[1] in acc else None
        y = _STAFF_TOP + (_TREBLE_TOP_STEP - _diatonic(pitch)) * _STEP
        heads += (
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="5.2" ry="3.9" '
            f'fill="#222" transform="rotate(-18 {x:.1f} {y:.1f})"/>'
        )
        bottom = _STAFF_TOP + 8 * _STEP
        row = bottom + _STEP * 2
        while row <= y + 0.1:  # ledger lines below the staff
            ledgers += (
                f'<line x1="{x - 9:.1f}" y1="{row:.1f}" x2="{x + 9:.1f}" '
                f'y2="{row:.1f}" stroke="#222" stroke-width="0.9"/>'
            )
            row += _STEP * 2
        if mark:
            heads += (
                f'<text x="{x - 17:.1f}" y="{y + 4:.1f}" font-size="12" fill="#222">{mark}</text>'
            )
        labels += (
            f'<text x="{x:.1f}" y="{bottom + 26:.1f}" font-size="7.5" '
            f'text-anchor="middle" fill="#444">{html.escape(html.unescape(label))}</text>'
        )
    return (
        f'<div class=staff><svg viewBox="0 0 {width:.0f} 88" width="{width:.0f}" '
        f'height="88" role="img">'
        f'<text x="10" y="{_STAFF_TOP + 30:.1f}" font-size="38" fill="#222">&#119070;</text>'
        f"{lines}{keysig}{ledgers}{heads}{labels}</svg>"
        f"<p class=hexcap>{caption}</p></div>"
    )
