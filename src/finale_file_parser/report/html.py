"""Rendering an `Inspection` as one self-contained HTML file.

No server, no external assets, no build step: the report is a file, which is what
makes it archivable beside the converted output and sendable by someone whose
score cannot leave their machine.
"""

from __future__ import annotations

import html as html_escape
import json
from dataclasses import asdict

from finale_file_parser.report.model import Inspection

__all__ = ["render_html"]


_STYLE = """
body { font: 14px/1.5 ui-monospace, monospace; margin: 2rem; max-width: 70rem; }
h1 { font-size: 1.2rem; margin-bottom: 0; }
.meta { color: #666; margin-top: 0.2rem; }
ol.ladder { list-style: none; padding: 0; }
ol.ladder li { padding: 0.3rem 0.6rem; border-left: 4px solid #ccc; margin: 0.2rem 0; }
li.ok { border-color: #2a7; }
li.refused { border-color: #c81; }
li.crashed { border-color: #c33; font-weight: bold; }
li.skipped { border-color: #ddd; color: #999; }
nav button { font: inherit; margin-right: 0.4rem; }
section { display: none; }
section.shown { display: block; }
table { border-collapse: collapse; }
td, th { border: 1px solid #ddd; padding: 0.15rem 0.5rem; text-align: left; }
.empty { color: #c33; }
"""

_SCRIPT = """
const data = JSON.parse(document.getElementById('inspection').textContent);
function show(name) {
  for (const s of document.querySelectorAll('section')) {
    s.className = (s.id === name) ? 'shown' : '';
  }
}
for (const b of document.querySelectorAll('nav button')) {
  b.addEventListener('click', () => show(b.dataset.pane));
}
function esc(t) {
  return String(t).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
}
function renderScore() {
  const el = document.getElementById('score');
  if (!data.score) { el.innerHTML = '<p>No score was built.</p>'; return; }
  let out = '';
  for (const part of data.score.parts) {
    out += '<h2>' + esc(part.id) + ' — ' + esc(part.name) + '</h2><table>' +
           '<tr><th>measure</th><th>time</th><th>clef</th><th>key</th>' +
           '<th>events</th><th>pitches</th></tr>';
    for (const m of part.measures) {
      const cls = m.events === 0 ? ' class="empty"' : '';
      out += '<tr' + cls + '><td>' + m.number + '</td><td>' + esc(m.time ?? '') +
             '</td><td>' + esc(m.clef ?? '') + '</td><td>' + esc(m.key ?? '') +
             '</td><td>' + m.events + '</td><td>' + m.pitches + '</td></tr>';
    }
    out += '</table>';
  }
  el.innerHTML = out;
}
function renderJson(id, value) {
  document.getElementById(id).innerHTML =
    value ? '<pre>' + esc(JSON.stringify(value, null, 2)) + '</pre>'
          : '<p>Not available — the pipeline stopped before this stage.</p>';
}
function renderBytes() {
  const el = document.getElementById('bytes');
  const pools = Object.entries(data.raw || {});
  if (!pools.length) { el.innerHTML = '<p>No raw bytes were embedded.</p>'; return; }
  let out = '';
  for (const [name, b64] of pools) {
    const bin = atob(b64);
    let hex = '';
    for (let i = 0; i < Math.min(bin.length, 4096); i++) {
      hex += bin.charCodeAt(i).toString(16).padStart(2, '0') + (i % 16 === 15 ? '\\n' : ' ');
    }
    out += '<h2>' + esc(name) + ' (' + bin.length + ' bytes)</h2><pre>' + esc(hex) + '</pre>';
  }
  el.innerHTML = out;
}
renderScore();
renderJson('document', data.document);
renderJson('records', data.records);
renderBytes();
show('score');
"""


def _embed(data: object) -> str:
    """JSON safe to place inside a <script> block in an XML-well-formed page.

    Document text reaches this -- titles, part names, lyrics -- and the input is
    untrusted. A `</script>` in a lyric would end the block and turn the rest of
    the document into markup; a bare `<` or `&` would break well-formedness.
    Escaping both as JSON unicode escapes fixes both at once and still parses as
    JSON on the other side.
    """
    return json.dumps(data, default=str).replace("<", "\\u003c").replace("&", "\\u0026")


def _ladder(inspection: Inspection) -> str:
    """The stage ladder as an always-visible `<ol>`: what was tried, in order,
    and how far it got. Shown unconditionally -- unlike the four panes below,
    which hide behind a nav button, this is the one part of the report that
    answers "did it work" without a click."""
    rows = []
    for stage in inspection.stages:
        detail = " ".join(f"{k}={v}" for k, v in stage.detail.items())
        text = html_escape.escape(stage.name)
        if detail:
            text += " <span>" + html_escape.escape(detail) + "</span>"
        if stage.error:
            text += " — " + html_escape.escape(stage.error)
        rows.append(f'<li class="{html_escape.escape(stage.status)}">{text}</li>')
    return '<ol class="ladder">' + "".join(rows) + "</ol>"


def render_html(inspection: Inspection) -> str:
    """One self-contained page. No network, no build step, no external assets.

    Must return a string for any `Inspection`, including one whose ladder
    stopped at the first rung and whose score/document/records/raw are all
    empty -- report generation itself must never fail, even for input the
    pipeline refused outright.

    The behaviour script is wrapped in a `<![CDATA[ ... ]]>` section (the `//`
    either side keeps both markers as JS comments): unlike a browser's HTML
    parser, which treats `<script>` content as raw text, an XML parser reads
    every child of every element as markup, so the JS's own `<`, `>` and `&`
    (comparisons, a character-class regex) would otherwise look like tags and
    entities and break the well-formedness this page is meant to keep.
    """
    name = html_escape.escape(inspection.file.get("name", "document"))
    meta = html_escape.escape(
        f"{inspection.file.get('size', '?')} bytes · sha256 {inspection.file.get('sha256', '')}"
    )
    notes = "".join(f"<p>{html_escape.escape(n)}</p>" for n in inspection.notes)
    payload = _embed(
        {
            "file": inspection.file,
            "stages": [asdict(s) for s in inspection.stages],
            "score": inspection.score,
            "document": inspection.document,
            "records": inspection.records,
            "raw": inspection.raw,
            "notes": inspection.notes,
        }
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8"/>'
        f"<title>{name} — inspection</title>"
        f"<style>{_STYLE}</style></head><body>"
        f'<h1>{name}</h1><p class="meta">{meta}</p>'
        f"{_ladder(inspection)}{notes}"
        '<nav><button data-pane="score">score</button>'
        '<button data-pane="document">document</button>'
        '<button data-pane="records">records</button>'
        '<button data-pane="bytes">bytes</button></nav>'
        '<section id="score"></section><section id="document"></section>'
        '<section id="records"></section><section id="bytes"></section>'
        f'<script id="inspection" type="application/json">{payload}</script>'
        f"<script>//<![CDATA[\n{_SCRIPT}\n//]]></script>"
        "</body></html>"
    )
