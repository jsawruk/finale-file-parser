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
h1 { font-size: 1.2rem; margin-bottom: 0.6rem; }
h2 { font-size: 1rem; margin: 1.2rem 0 0.3rem; }
h3 { font-size: 0.95rem; font-weight: normal; color: #444; margin: 0.8rem 0 0.2rem; }
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
.stopped { color: #666; }
details.node { margin-left: 1rem; }
details.node > summary { cursor: pointer; padding: 0.1rem 0; }
details.node > summary::marker { color: #999; }
.count { color: #666; font-weight: normal; }
.leaf { margin-left: 1rem; color: #333; }
.leaf .name { color: #666; }
.mirror { color: #a60; }
.rest { color: #999; font-style: italic; }
.bar { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-left: 1rem; }
.bar .ev { border: 1px solid #eee; padding: 0 0.3rem; }
.split { display: flex; gap: 1.5rem; align-items: flex-start; }
.split .tree { flex: 1 1 40%; min-width: 0; }
.split .detail { flex: 1 1 60%; min-width: 0; position: sticky; top: 1rem;
                 border-left: 1px solid #ddd; padding-left: 1rem; }
.rec { cursor: pointer; margin-left: 2rem; padding: 0.05rem 0.3rem; }
.rec:hover { background: #f2f2f2; }
.rec.on { background: #e8eef6; font-weight: bold; }
.hex { white-space: pre; font-size: 13px; line-height: 1.35; overflow-x: auto; }
.hex .off { color: #999; }
.hex .txt { color: #666; }
.no-bytes { color: #666; max-width: 34rem; }
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
function renderStats() {
  const el = document.getElementById('stats');
  if (!data.stats) { el.innerHTML = stopped('stats'); return; }
  let out = '';
  for (const part of data.stats.parts) {
    out += '<h3>' + esc(part.id) + ' — ' + esc(part.name) + '</h3><table>' +
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
// What this reader knowingly does not carry out of a file. The rest of the old
// Document summary is gone: its per-pool counts were identical to the ones the
// Records tree already shows on its own summaries -- measured across 40 .musx
// documents, identical in all 40 -- and its "version" was the family string the
// ladder reports one line above.
function renderUntranslated() {
  const el = document.getElementById('untranslated');
  const gaps = (data.document && data.document.untranslated) || [];
  if (gaps.length === 0) { el.innerHTML = stopped('list of gaps'); return; }
  const list = document.createElement('ul');
  for (const gap of gaps) {
    const item = document.createElement('li');
    item.textContent = gap;
    list.appendChild(item);
  }
  el.innerHTML = '';
  el.appendChild(list);
}
// The ladder used to sit above every pane, so an empty pane explained itself.
// It lives under Debug now, so a pane that has nothing to show has to say why
// and where to look -- otherwise a file that failed to parse opens on a blank
// Music tab and reads like a document with no music in it.
function stopped(what) {
  const bad = (data.stages || []).find(s => s.status === 'refused' || s.status === 'crashed');
  const why = bad ? 'the pipeline stopped at "' + bad.name + '" (' + bad.status + ')'
                  : 'the pipeline did not reach it';
  return '<p class="stopped">No ' + what + ' — ' + esc(why) +
         '. See the Debug tab for the full ladder.</p>';
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
    el.innerHTML = stopped('records');
    return;
  }
  el.innerHTML = '';
  const pools = Object.entries(data.records)
    .filter(([, tags]) => Object.keys(tags).length !== 0);
  if (pools.length === 0) { el.innerHTML = '<p class="stopped">No records.</p>'; return; }

  const split = document.createElement('div');
  split.className = 'split';
  const left = document.createElement('div');
  left.className = 'tree';
  const right = document.createElement('div');
  right.className = 'detail';
  right.innerHTML = '<p class="stopped">Select a record.</p>';

  for (const [pool, tags] of pools) {
    const total = Object.values(tags).reduce((n, rs) => n + rs.length, 0);
    const node = tree(pool, Object.keys(tags).length + ' tags, ' + group(total) + ' records');
    for (const [tag, records] of Object.entries(tags)) {
      const tagNode = tree(tag, group(records.length) + '');
      for (const rec of records) {
        // A leaf, not another expander. The fields used to nest a third level
        // down, which made clicking a record look like it did nothing much;
        // they are the right-hand panel's job now.
        const row = document.createElement('div');
        row.className = 'rec';
        const size = rec.length === null ? '' : '  ' + group(rec.length) + ' bytes';
        row.textContent = rec.key + size;
        row.addEventListener('click', () => {
          for (const other of left.querySelectorAll('.rec.on')) { other.classList.remove('on'); }
          row.classList.add('on');
          showRecord(right, pool, tag, rec);
        });
        tagNode.appendChild(row);
      }
      node.appendChild(tagNode);
    }
    left.appendChild(node);
  }
  split.appendChild(left);
  split.appendChild(right);
  el.appendChild(split);
}
// This script is a Python string literal, so a backslash-n here would be a real
// newline inside a JS string literal, which will not parse. Build it instead.
const NEWLINE = String.fromCharCode(10);
function hexRows(bin) {
  const rows = [];
  for (let base = 0; base < bin.length; base += 16) {
    const bytes = [];
    let text = '';
    for (let i = base; i < base + 16; i++) {
      if (i < bin.length) {
        const b = bin.charCodeAt(i);
        bytes.push(b.toString(16).padStart(2, '0'));
        text += (b >= 32 && b < 127) ? bin[i] : '.';
      } else {
        bytes.push('  ');
      }
    }
    rows.push({off: base.toString(16).padStart(8, '0'), hex: bytes.join(' '), txt: text});
  }
  return rows;
}
function hexBlock(bin) {
  const box = document.createElement('div');
  box.className = 'hex';
  for (const row of hexRows(bin)) {
    const off = document.createElement('span');
    off.className = 'off';
    off.textContent = row.off + '  ';
    const txt = document.createElement('span');
    txt.className = 'txt';
    txt.textContent = '  ' + row.txt;
    box.appendChild(off);
    box.appendChild(document.createTextNode(row.hex));
    box.appendChild(txt);
    box.appendChild(document.createTextNode(NEWLINE));
  }
  return box;
}
// `payload` and `extra` ARE the bytes shown above, so listing them again as
// decoded values would just repeat the hex in base64.
const BYTE_FIELDS = ['payload', 'extra'];
function showRecord(right, pool, tag, rec) {
  right.innerHTML = '';
  const heading = document.createElement('h3');
  heading.textContent = pool + ' / ' + tag + ' ' + rec.key;
  right.appendChild(heading);

  let raw = '';
  for (const name of BYTE_FIELDS) {
    const value = rec.fields && rec.fields[name];
    if (typeof value === 'string' && value !== '') { raw += atob(value); }
  }
  if (raw === '') {
    const note = document.createElement('p');
    note.className = 'no-bytes';
    // True of every .musx record: EnigmaXML arrives as XML, so a record has no
    // undecoded form to show. Saying so beats an empty box that reads like a
    // reader that lost the bytes.
    note.textContent = 'No raw bytes: this record was read from XML, so its ' +
                       'fields below are the source form rather than a decoding of it.';
    right.appendChild(note);
  } else {
    right.appendChild(hexBlock(raw));
    const caption = document.createElement('p');
    caption.className = 'txt';
    caption.textContent = 'decodes as';
    right.appendChild(caption);
  }
  const rest = {};
  for (const [k, v] of Object.entries(rec.fields || {})) {
    if (!BYTE_FIELDS.includes(k)) { rest[k] = v; }
  }
  right.appendChild(fields(rest));
}
// Both trees are built from DOM nodes rather than an innerHTML string: every
// key, tag and value goes in as text, so there is no second escaper to get
// wrong on a record whose field names came out of a hostile file.
function tree(label, count) {
  const node = document.createElement('details');
  node.className = 'node';
  const summary = document.createElement('summary');
  summary.textContent = label;
  if (count) {
    const badge = document.createElement('span');
    badge.className = 'count';
    badge.textContent = '  ' + count;
    summary.appendChild(badge);
  }
  node.appendChild(summary);
  return node;
}
function fields(value) {
  const box = document.createElement('div');
  if (value === null || typeof value !== 'object') {
    box.className = 'leaf';
    box.textContent = String(value);
    return box;
  }
  for (const [k, v] of Object.entries(value)) {
    if (v !== null && typeof v === 'object') {
      const child = tree(k, Array.isArray(v) ? v.length + ' items' : '');
      child.appendChild(fields(v));
      box.appendChild(child);
    } else {
      const leaf = document.createElement('div');
      leaf.className = 'leaf';
      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = k + ': ';
      leaf.appendChild(name);
      leaf.appendChild(document.createTextNode(String(v)));
      box.appendChild(leaf);
    }
  }
  return box;
}
function renderMusic() {
  const el = document.getElementById('music');
  if (!data.music) { el.innerHTML = stopped('music'); return; }
  el.innerHTML = '';
  for (const part of data.music.parts) {
    const label = part.id + (part.name ? ' — ' + part.name : '');
    const partNode = tree(label, group(part.measures.length) + ' measures');
    for (const measure of part.measures) {
      const events = measure.voices.reduce((n, v) => n + v.events.length, 0);
      const mirrored = measure.voices.some(v => v.mirrors.length !== 0);
      const measureNode = tree(
        'measure ' + measure.number,
        (events === 0 ? 'empty' : group(events) + ' events') + (mirrored ? ' · mirrored' : ''));
      for (const voice of measure.voices) {
        const voiceNode = tree('layer ' + voice.number, voiceLabel(voice));
        if (voice.mirrors.length !== 0) { voiceNode.classList.add('mirror'); }
        voiceNode.appendChild(bar(voice.events));
        measureNode.appendChild(voiceNode);
      }
      partNode.appendChild(measureNode);
    }
    el.appendChild(partNode);
  }
}
function voiceLabel(voice) {
  const n = group(voice.events.length) + ' events';
  if (voice.mirrors.length === 0) { return n; }
  // Not "copied from": the file names no original, so this states the fact
  // both staves agree on -- the same entries sound in both places.
  return n + ' · the same entries also sound on staff ' + voice.mirrors.join(', ');
}
function bar(events) {
  const box = document.createElement('div');
  box.className = 'bar';
  for (const event of events) {
    const cell = document.createElement('span');
    cell.className = 'ev';
    let text = event.rest ? 'rest' : event.pitches.join(' ');
    if (event.grace) { text = 'grace ' + text; }
    if (event.tie) { text += ' (tie ' + event.tie + ')'; }
    cell.textContent = text + '  ' + event.duration;
    if (event.rest) { cell.classList.add('rest'); }
    box.appendChild(cell);
  }
  return box;
}
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
function control(label, onClick) {
  const button = document.createElement('button');
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}
renderStats();
renderMusic();
renderUntranslated();
renderRecords();
show('music');
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


_MARK = {"ok": "\u2705", "refused": "\u274c", "crashed": "\u274c", "skipped": "\u00b7"}
"""A mark per stage status.

Refused and crashed share the cross because both mean "no result here"; what
separates them is whose fault it is -- the file declining to be read, or this
reader hitting a bug -- and the row's own styling already carries that. Skipped
gets a middle dot rather than a cross: nothing went wrong, the ladder simply
never reached it.
"""


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
        rows.append(f'<li class="{_text(stage.status)}">{_MARK[stage.status]} {text}</li>')
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
    meta = _text(f"{inspection.file.get('size', '?')} bytes")
    notes = "".join(f"<p>{_text(n)}</p>" for n in inspection.notes)
    payload = _embed(
        {
            "file": inspection.file,
            "stages": [asdict(s) for s in inspection.stages],
            "stats": inspection.stats,
            "music": inspection.music,
            "document": inspection.document,
            "records": inspection.records,
            "notes": inspection.notes,
        }
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8"/>'
        f"<title>{name} — inspection</title>"
        f"<style>{_STYLE}</style></head><body>"
        f"<h1>{name}</h1>"
        '<nav><button data-pane="music">Music</button>'
        '<button data-pane="records">Records</button>'
        '<button data-pane="debug">Debug</button></nav>'
        '<section id="music"></section><section id="records"></section>'
        '<section id="debug">'
        "<h2>File</h2>"
        f'<p class="meta">{meta}</p>{notes}'
        "<h2>Pipeline</h2>"
        f"{_ladder(inspection)}"
        '<h2>Stats</h2><div id="stats"></div>'
        '<h2>Not translated</h2><div id="untranslated"></div>'
        "</section>"
        f'<script id="inspection" type="application/json">{payload}</script>'
        f"<script>//<![CDATA[\n{_SCRIPT}\n//]]></script>"
        "</body></html>"
    )
