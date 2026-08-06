"""Rendering an `Inspection` as one self-contained HTML file.

No server, no external assets, no build step: the report is a file, which is what
makes it archivable beside the converted output and sendable by someone whose
score cannot leave their machine.
"""

from __future__ import annotations

import html as html_escape
import json
import re
from dataclasses import asdict

from finale_file_parser.report.model import Inspection

__all__ = ["render_html"]

_NOT_XML_TEXT = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
"""Every character XML 1.0 forbids in character data (its `Char` production).

Two of them arrive from real filenames. POSIX permits any byte but NUL and `/`,
so `os.fsdecode` turns an invalid UTF-8 byte into a lone surrogate -- which is
not encodable as UTF-8 at all, so `Path.write_text` raises `UnicodeEncodeError`
on the finished page. It also permits C0 control characters, which *are*
encodable but are illegal in XML even as a character reference, so the page
would be written and then refuse to parse. `html.escape` fixes neither: it only
touches `&`, `<`, `>` and the quotes.
"""


def _text(value: str) -> str:
    """One choke point for every string rendered as page text.

    Sanitising here rather than in `model.py` keeps the model honest: an
    `Inspection` should report the name the operating system actually gave the
    file, undamaged, for anything that reads it as data. It is only the
    *rendering* that cannot carry these characters, and only the raw-text path
    at that -- the JSON island escapes them itself, since `json.dumps` defaults
    to `ensure_ascii=True` and so emits `\\ud8ff`-style escapes rather than the
    characters. So this is the boundary where the constraint is real.
    """
    return html_escape.escape(_NOT_XML_TEXT.sub("\ufffd", value))


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
.controls button, .controls input { font: inherit; margin-right: 0.4rem; }
.range { color: #666; }
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
function findStage(name) {
  return (data.stages || []).find(s => s.name === name) || null;
}
function renderRecords() {
  // `records` defaults to {} rather than null, and {} is truthy in JS, so
  // renderJson's own truthiness check cannot tell "read fine, found nothing"
  // apart from "never read". The "read records" stage's own status can: it
  // is only ever OK when the read actually ran and returned (possibly empty).
  const el = document.getElementById('records');
  const stage = findStage('read records');
  if (!stage || stage.status !== 'ok') {
    let reason = 'the pipeline stopped before this stage';
    if (stage) {
      reason = stage.name + ': ' + stage.status;
      if (stage.error) { reason += ' (' + stage.error + ')'; }
    }
    el.innerHTML = '<p>Not available — ' + esc(reason) + '</p>';
    return;
  }
  el.innerHTML = '<pre>' + esc(JSON.stringify(data.records, null, 2)) + '</pre>';
}
// A pool is embedded whole, so the only limit here is how much hex is worth
// putting on screen at once: one 4 KB page, with the rest a click away rather
// than silently absent. The old loop stopped at 4096 bytes of a 269 KB pool
// and said nothing about the other 98%.
const PAGE_BYTES = 4096;

// This script is a Python string literal, so a backslash here would have to
// survive two layers of escaping. Nothing below uses one.
const NEWLINE = String.fromCharCode(10);

function group(n) {
  let rest = String(n);
  let out = '';
  while (rest.length !== 0) {
    const cut = Math.max(0, rest.length - 3);
    out = rest.slice(cut) + (out === '' ? '' : ',') + out;
    rest = rest.slice(0, cut);
  }
  return out;
}
function hexDump(bin, start, stop) {
  const lines = [];
  let line = '';
  for (let i = start; i !== stop; i++) {
    if (i % 16 === 0) { line = i.toString(16).padStart(8, '0') + '  '; }
    line += bin.charCodeAt(i).toString(16).padStart(2, '0') + ' ';
    if (i % 16 === 15) { lines.push(line); }
  }
  if (stop % 16 !== 0) { lines.push(line); }
  return lines.join(NEWLINE);
}
function control(label, onClick) {
  const button = document.createElement('button');
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}
function bytePool(name, bin) {
  // Built as DOM nodes rather than an innerHTML string: the pool name and the
  // hex both go in as text, so there is no second escaper to get wrong, and no
  // markup of this pane's own to keep well-formed.
  const heading = document.createElement('h2');
  heading.textContent = name;
  const controls = document.createElement('p');
  controls.className = 'controls';
  const range = document.createElement('span');
  range.className = 'range';
  const dump = document.createElement('pre');
  const lastPage = Math.max(0, Math.ceil(bin.length / PAGE_BYTES) - 1);
  let page = 0;

  function draw() {
    const start = page * PAGE_BYTES;
    const stop = Math.min(start + PAGE_BYTES, bin.length);
    dump.textContent = hexDump(bin, start, stop);
    // Always on screen: which slice this is, and how much there is in total.
    range.textContent = (bin.length === 0)
      ? 'empty pool'
      : 'bytes ' + group(start) + '–' + group(stop - 1) + ' of ' + group(bin.length);
    previous.disabled = (page === 0);
    next.disabled = (page === lastPage);
  }
  function step(by) {
    return function () {
      page = Math.min(lastPage, Math.max(0, page + by));
      draw();
    };
  }

  const previous = control('previous', step(-1));
  const next = control('next', step(1));
  const wanted = document.createElement('input');
  wanted.size = 8;
  wanted.placeholder = 'offset';
  const go = control('go', function () {
    const offset = parseInt(wanted.value, 10);
    if (!isNaN(offset)) {
      page = Math.min(lastPage, Math.max(0, Math.floor(offset / PAGE_BYTES)));
      draw();
    }
  });

  controls.appendChild(previous);
  controls.appendChild(next);
  controls.appendChild(wanted);
  controls.appendChild(go);
  controls.appendChild(range);
  const box = document.createElement('div');
  box.appendChild(heading);
  box.appendChild(controls);
  box.appendChild(dump);
  draw();
  return box;
}
function renderBytes() {
  const el = document.getElementById('bytes');
  el.textContent = '';
  const pools = Object.entries(data.raw || {});
  if (!pools.length) { el.textContent = 'No raw bytes were embedded.'; return; }
  for (const [name, b64] of pools) {
    el.appendChild(bytePool(name, atob(b64)));
  }
}
renderScore();
renderJson('document', data.document);
renderRecords();
renderBytes();
show('score');
"""


def _embed(data: object) -> str:
    """JSON safe to place inside a <script> block in an XML-well-formed page.

    Document text reaches this -- titles, part names, lyrics -- and the input is
    untrusted. A `</script>` in a lyric would end the block and turn the rest of
    the document into markup; a bare `<` or `&` would break well-formedness. So
    would a bare `>`: XML forbids the literal sequence `]]>` in character data
    outside a CDATA section (it is the CDATA end marker), and `json.dumps` will
    happily emit e.g. `"]]>hi"` verbatim inside a string value. Escaping all
    three as JSON unicode escapes closes every case at once and still parses as
    JSON on the other side.
    """
    return (
        json.dumps(data, default=str)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _ladder(inspection: Inspection) -> str:
    """The stage ladder as an always-visible `<ol>`: what was tried, in order,
    and how far it got. Shown unconditionally -- unlike the four panes below,
    which hide behind a nav button, this is the one part of the report that
    answers "did it work" without a click."""
    rows = []
    for stage in inspection.stages:
        detail = " ".join(f"{k}={v}" for k, v in stage.detail.items())
        text = _text(stage.name)
        if detail:
            text += " <span>" + _text(detail) + "</span>"
        if stage.error:
            text += " — " + _text(stage.error)
        rows.append(f'<li class="{_text(stage.status)}">{text}</li>')
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
    name = _text(inspection.file.get("name", "document"))
    meta = _text(
        f"{inspection.file.get('size', '?')} bytes · sha256 {inspection.file.get('sha256', '')}"
    )
    notes = "".join(f"<p>{_text(n)}</p>" for n in inspection.notes)
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
