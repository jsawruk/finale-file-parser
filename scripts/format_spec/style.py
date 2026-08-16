"""Print stylesheet for the format specification.

Sized for A4 with margins a printer will honour. Hex dumps are the one thing
that must never wrap or reflow, so they get a fixed character width and are
allowed to break across pages only between rows.
"""

from __future__ import annotations

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
@page { @bottom-center { content: counter(page); } }

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font: 10.5pt/1.5 "Charter", "Georgia", serif;
  color: #1a1a1a; margin: 0;
}
code, pre, .hexdump { font-family: "SF Mono", "Menlo", "Consolas", monospace; }

h1 { font-size: 26pt; line-height: 1.15; margin: 0 0 4pt; letter-spacing: -0.4pt; }
h2 {
  font-size: 15pt; margin: 26pt 0 8pt; padding-bottom: 3pt;
  border-bottom: 1.5pt solid #1a1a1a; break-after: avoid;
}
h3 { font-size: 12pt; margin: 18pt 0 6pt; break-after: avoid; }
h4 { font-size: 10.5pt; margin: 12pt 0 4pt; font-variant: small-caps;
     letter-spacing: 0.5pt; break-after: avoid; }
h2 + h3 { margin-top: 10pt; }
p { margin: 0 0 7pt; }
a { color: #14507a; }

.subtitle { font-size: 12pt; color: #555; margin-bottom: 2pt; }
.meta { font-size: 9pt; color: #777; }
.lead { font-size: 11.5pt; color: #333; }

/* --- callouts --------------------------------------------------------- */
.note, .warn, .prov {
  font-size: 9.5pt; padding: 6pt 9pt; margin: 8pt 0; border-left: 2.5pt solid;
  background: #f7f7f7; break-inside: avoid;
}
.note { border-color: #6a8caf; }
.warn { border-color: #c07a3a; background: #fdf6ef; }
.prov { border-color: #7a9a6a; background: #f4f8f2; font-style: italic; }

/* --- review marks: temporary, and meant to be deleted ------------------
   Everything added or changed since the last read is badged, so a reviewer
   can find it without diffing a 200 KB document. Print-safe: the badge is
   an outline and a word, not a colour fill, so it survives greyscale and a
   black-and-white printer. Remove these rules with `NEW_SINCE_LAST_REVIEW`
   once the additions have been read. */
.newbadge {
  font-size: 7pt; font-weight: bold; letter-spacing: 0.5pt; vertical-align: 0.35em;
  border: 0.75pt solid #b03030; color: #b03030; padding: 0.5pt 3pt; margin-left: 6pt;
  border-radius: 2pt;
}
.review { border-color: #b03030; background: #fdf3f3; }
.review .newbadge { vertical-align: baseline; }

/* --- tables ----------------------------------------------------------- */
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9pt; }
th {
  text-align: left; border-bottom: 1pt solid #1a1a1a; padding: 3pt 5pt;
  font-weight: 600; font-size: 8.5pt; text-transform: uppercase;
  letter-spacing: 0.4pt;
}
td { padding: 3pt 5pt; border-bottom: 0.5pt solid #ddd; vertical-align: top; }
table.struct { break-inside: avoid; }
table.struct td.off, table.struct td.sz { text-align: right; white-space: nowrap;
  font-family: "SF Mono", "Menlo", monospace; font-size: 8.5pt; }
table.struct td.sw { width: 14pt; }
.swatch {
  display: inline-block; width: 9pt; height: 9pt; border: 0.5pt solid #999;
  vertical-align: middle;
}

/* --- code and hex ----------------------------------------------------- */
pre.cstruct {
  font-size: 8.5pt; line-height: 1.45; background: #f4f4f4; padding: 8pt 10pt;
  margin: 8pt 0; border: 0.5pt solid #ddd; overflow: hidden;
  white-space: pre-wrap; break-inside: avoid;
}
.hexdump { font-size: 8pt; line-height: 1.5; margin: 6pt 0 4pt; }
.hexrow { white-space: nowrap; }
.hexrow .off { color: #999; margin-right: 10pt; }
.hexrow .hex { letter-spacing: 0; }
.hexrow .asc { margin-left: 12pt; color: #555; }
.hexdump span.b { padding: 0.5pt 0; }
.hexcap, .caption { font-size: 9pt; color: #666; margin: 6pt 0 2pt; }
.caption { font-style: italic; }

.structblock { margin: 10pt 0 16pt; }
.legend { font-size: 8.5pt; color: #666; margin-top: 3pt; }

/* --- page furniture ---------------------------------------------------- */
.pagebreak { break-before: page; }
.toc { font-size: 10pt; }
.toc li { margin: 2pt 0; }
.toc .num { color: #888; margin-right: 6pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin: 2pt 0; }
dl { margin: 6pt 0; }
dt { font-weight: 600; margin-top: 6pt; }
dd { margin: 0 0 4pt 14pt; }
"""

CSS += """
/* --- footnotes, charts ------------------------------------------------- */
sup.fn { font-size: 7pt; color: #14507a; padding-left: 1pt; }
.notes { margin-top: 14pt; border-top: 0.5pt solid #ccc; padding-top: 6pt; }
ol.footnotes { font-size: 8.5pt; color: #444; padding-left: 16pt; }
ol.footnotes li { margin: 3pt 0; }

.chart { display: flex; align-items: center; gap: 18pt; margin: 10pt 0 12pt;
         break-inside: avoid; }
.chart svg { flex: 0 0 auto; }
ul.chartkey { list-style: none; padding: 0; margin: 0; font-size: 9.5pt; }
ul.chartkey li { margin: 4pt 0; }
ul.chartkey .swatch { margin-right: 5pt; }
"""

CSS += """
.staff { margin: 10pt 0 12pt; break-inside: avoid; }
.staff svg { display: block; }
.staff .hexcap { margin-top: 2pt; }
"""

CSS += """
.score { margin: 12pt 0 14pt; break-inside: avoid; }
/* Verovio emits a viewBox and no width, so max-width:100% would stretch the
   staff to the column. Fix the height and let the width follow the aspect. */
.score svg { height: 88pt; width: auto; max-width: 100%; display: block; }
"""

CSS += """
.scorerow { display: flex; align-items: flex-end; gap: 5pt; }
.scoreart { min-width: 0; }
/* The two lyric rows sit at the foot of the engraving; the labels are set to
   the same rhythm and bottom-aligned with them. */
.scorekey {
  display: flex; flex-direction: column; text-align: right;
  font-size: 9pt; color: #444; padding-bottom: 2pt; white-space: nowrap;
}
.scorekey span { line-height: 11pt; }
"""
