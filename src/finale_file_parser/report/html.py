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

from finale_file_parser.formats.layouts import PALETTE
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
.score { overflow-x: auto; margin-bottom: 1rem; }
.score .page { margin-bottom: 0.5rem; }
.score svg { max-width: 100%; height: auto; }
.tagdef { margin: 0.4rem 0 0.8rem; }
.tagdef dt { font-weight: bold; }
.tagdef dd { margin: 0.1rem 0 0 1.5rem; color: #444; max-width: 44rem; }
.swatch { display: inline-block; width: 0.9rem; height: 0.9rem; border: 1px solid #ccc; }
"""

_SCRIPT = (
    f"""
// Generated from the library's palette rather than restated here, so a field
// is the same colour in this report as in the specification document.
const PALETTE = {json.dumps(list(PALETTE))};
"""
    + """
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
// Inside the "document options" group the sentinel is already said once, at the
// top. What is left is whatever else keys the record -- a part, an incidence --
// which is the only part worth repeating per row.
// No regex: this script is a Python string literal, where a backslash is
// Python's escape before it is ever JavaScript's. A key is always parenthesised
// by `_key`, so slicing the ends off is both simpler and safe.
// A DCL tag is two characters decoded from a u16 as latin-1, and the era uses
// plenty of bytes that are not letters: 0x80 and friends arrive as C1 controls,
// which a browser draws as a blank, a box, or whatever glyph the font happens
// to put there. None of those can be read back, typed, or searched for. Show
// the code point instead, and leave printable tags exactly as they are so the
// numeric 2011 tags and the ordinary two-letter ones are untouched.
function displayTag(tag) {
  const codes = [...tag].map(c => c.codePointAt(0));
  const printable = n => n >= 33 && n <= 126;
  if (codes.every(printable)) { return tag; }
  return [...tag]
    .map((c, i) => printable(codes[i])
      ? c
      : 'U+' + codes[i].toString(16).toUpperCase().padStart(4, '0'))
    .join(' ');
}
const SENTINEL = 'document options';
function withoutSentinel(key) {
  const inner = key.slice(1, -1).split(', ').filter(p => p !== SENTINEL);
  return inner.length === 0 ? SENTINEL : '(' + inner.join(', ') + ')';
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

  // A leaf, not another expander. The fields used to nest a third level down,
  // which made clicking a record look like it did nothing much; they are the
  // right-hand panel's job now.
  function recordRow(pool, tag, rec, label) {
    const row = document.createElement('div');
    row.className = 'rec';
    row.textContent = label;
    row.addEventListener('click', () => {
      for (const other of left.querySelectorAll('.rec.on')) { other.classList.remove('on'); }
      row.classList.add('on');
      showRecord(right, pool, tag, rec);
    });
    return row;
  }
  // The name belongs in the tree as much as in the panel: a tree of bare
  // numbers is a tree nobody can navigate.
  function tagLabel(pool, tag) {
    const known = ((data.tags || {})[pool] || {})[tag];
    // The raw tag stays the lookup key everywhere; only what is shown changes.
    const shown = displayTag(tag);
    return known ? shown + '  ' + known.name : shown;
  }

  for (const [pool, tags] of pools) {
    const total = Object.values(tags).reduce((n, rs) => n + rs.length, 0);
    const node = tree(pool, Object.keys(tags).length + ' tags, ' + group(total) + ' records');

    // Document-wide options first, together. They are keyed by a sentinel
    // rather than by anything, so a document carries one under each of around
    // ninety tags -- scattered through the tree they read as the same row over
    // and over. Split per record and not per tag: 94 corpus tags hold a
    // document-wide default alongside the numbered records it applies to.
    const optionTags = Object.entries(tags)
      .map(([tag, records]) => [tag, records.filter(r => r.options)])
      .filter(([, records]) => records.length !== 0);
    if (optionTags.length !== 0) {
      const box = tree('document options', optionTags.length + ' tags');
      for (const [tag, records] of optionTags) {
        // One record is the overwhelming case (4,743 of 4,790 across the
        // corpus), and it needs no row of its own: the tag IS the record, so
        // the tag is what you click.
        if (records.length === 1) {
          box.appendChild(recordRow(pool, tag, records[0], tagLabel(pool, tag)));
          continue;
        }
        const tagNode = tree(tagLabel(pool, tag));
        for (const rec of records) {
          tagNode.appendChild(recordRow(pool, tag, rec, withoutSentinel(rec.key)));
        }
        box.appendChild(tagNode);
      }
      node.appendChild(box);
    }

    for (const [tag, records] of Object.entries(tags)) {
      const rest = records.filter(r => !r.options);
      if (rest.length === 0) { continue; }
      // No count on a tag row. The pool above already gives the totals, and a
      // number beside every tag competed with the name for attention while
      // answering a question nobody was asking at that level.
      const tagNode = tree(tagLabel(pool, tag));
      for (const rec of rest) {
        tagNode.appendChild(recordRow(pool, tag, rec, rec.key));
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
// Which field, if any, claims each byte. A layout describes the payload only,
// so `limit` stops the tint at the payload's end -- past it lie the record's
// `extra` bytes, which the layout says nothing about. A strided layout
// describes one slot and the payload repeats it, so the spans repeat too.
function tintMap(layout, limit) {
  const map = [];
  if (!layout) { return map; }
  const stride = layout.stride || 0;
  const slots = stride ? Math.ceil(limit / stride) : 1;
  for (let slot = 0; slot < slots; slot++) {
    const base = slot * stride;
    layout.fields.forEach((f, i) => {
      for (let b = 0; b < f.size; b++) {
        const at = base + f.offset + b;
        if (at < limit) { map[at] = i; }
      }
    });
  }
  return map;
}
function tinted(text, field) {
  const span = document.createElement('span');
  span.textContent = text;
  if (field !== undefined) {
    span.style.background = PALETTE[field % PALETTE.length];
  }
  return span;
}
// One span per byte rather than one per row: a field is tinted where it sits,
// including a field that straddles a row boundary.
function hexBlock(bin, map) {
  const tint = map || [];
  const box = document.createElement('div');
  box.className = 'hex';
  for (let base = 0; base < bin.length; base += 16) {
    const off = document.createElement('span');
    off.className = 'off';
    off.textContent = base.toString(16).padStart(8, '0') + '  ';
    box.appendChild(off);
    for (let i = base; i < base + 16; i++) {
      if (i >= bin.length) {
        box.appendChild(document.createTextNode('   '));
        continue;
      }
      const b = bin.charCodeAt(i);
      box.appendChild(tinted(b.toString(16).padStart(2, '0'), tint[i]));
      box.appendChild(document.createTextNode(' '));
    }
    const gap = document.createElement('span');
    gap.className = 'txt';
    gap.textContent = ' ';
    box.appendChild(gap);
    for (let i = base; i < base + 16 && i < bin.length; i++) {
      const b = bin.charCodeAt(i);
      const ch = (b >= 32 && b < 127) ? bin[i] : '.';
      const cell = tinted(ch, tint[i]);
      cell.className = 'txt';
      box.appendChild(cell);
    }
    box.appendChild(document.createTextNode(NEWLINE));
  }
  return box;
}
// A field's value, read off the same bytes the dump shows. The byte order is
// the document's own: a .mus states it, and the 2001-2005 era does occur
// big-endian, where reading a width the wrong way round gives a number rather
// than an error.
function decode(bin, offset, field, order) {
  if (offset + field.size > bin.length) { return '—'; }
  const bytes = [];
  for (let i = 0; i < field.size; i++) { bytes.push(bin.charCodeAt(offset + i)); }
  if (field.type === 'char[]') {
    // A name, NUL-terminated. Latin-1 because that is what the era wrote and
    // what the tag decoder already assumes; a byte over 127 is a character
    // here, not a decoding failure.
    let text = '';
    for (const b of bytes) {
      if (b === 0) { break; }
      text += String.fromCharCode(b);
    }
    return JSON.stringify(text);
  }
  if (!/^u?int(8|16|32)$/.test(field.type)) {
    // char[4], uint8[]: no single number to state, so show the bytes as they lie.
    return bytes.map(b => b.toString(16).padStart(2, '0')).join(' ');
  }
  const ordered = (order === 'big') ? bytes : bytes.slice().reverse();
  let value = 0;
  for (const b of ordered) { value = value * 256 + b; }
  if (field.type[0] === 'i' && value >= Math.pow(2, field.size * 8 - 1)) {
    value -= Math.pow(2, field.size * 8);
  }
  // Hex alongside: several of these fields pack a sign bit or a nibble beside
  // their value, and the decimal alone hides that.
  return (field.size > 1) ? value + '  0x' + (value >>> 0).toString(16) : String(value);
}
function layoutTable(layout, bin, order) {
  const table = document.createElement('table');
  const head = document.createElement('tr');
  for (const label of ['', 'offset', 'size', 'type', 'field', 'value', 'meaning']) {
    const th = document.createElement('th');
    th.textContent = label;
    head.appendChild(th);
  }
  table.appendChild(head);
  layout.fields.forEach((f, i) => {
    const row = document.createElement('tr');
    const swatch = document.createElement('span');
    swatch.className = 'swatch';
    swatch.style.background = PALETTE[i % PALETTE.length];
    const span = (f.size === 1)
      ? '0x' + f.offset.toString(16)
      : '0x' + f.offset.toString(16) + '–0x' + (f.offset + f.size - 1).toString(16);
    const cells = [null, span, String(f.size), f.type, f.name,
                   decode(bin, f.offset, f, order), f.note];
    cells.forEach((text, n) => {
      const td = document.createElement('td');
      if (n === 0) { td.appendChild(swatch); } else { td.textContent = text; }
      row.appendChild(td);
    });
    table.appendChild(row);
  });
  return table;
}
// `payload` and `extra` ARE the bytes shown above, so listing them again as
// decoded values would just repeat the hex in base64.
const BYTE_FIELDS = ['payload', 'extra'];
function showRecord(right, pool, tag, rec) {
  right.innerHTML = '';
  // A tag on its own says nothing: "others / 176 / 1/0" names a record only to
  // someone holding the catalogue. Where this project can name it, the name
  // leads and the tag follows.
  const named = ((data.tags || {})[pool] || {})[tag];
  const heading = document.createElement('h3');
  heading.textContent = named
    ? named.name + '  —  ' + pool + ' / ' + displayTag(tag) + ' ' + rec.key
    : pool + ' / ' + displayTag(tag) + ' ' + rec.key;
  right.appendChild(heading);
  // A definition, not a sentence: the tag on its own line and its meaning
  // indented beneath. Run together as "fg tag — 'Simple Major Triad', ..." the
  // two halves wrap into each other and the tag stops being findable.
  if (named && named.description) {
    const list = document.createElement('dl');
    list.className = 'tagdef';
    const term = document.createElement('dt');
    term.textContent = displayTag(tag);
    const meaning = document.createElement('dd');
    meaning.textContent = named.description;
    list.appendChild(term);
    list.appendChild(meaning);
    right.appendChild(list);
  }

  let raw = '';
  let payloadLength = 0;
  for (const name of BYTE_FIELDS) {
    const value = rec.fields && rec.fields[name];
    if (typeof value === 'string' && value !== '') { raw += atob(value); }
    // A layout describes the payload, and `extra` follows it in the same dump.
    // Where the one ends is not in the report -- `length` is their sum -- so it
    // is taken here, from the field the bytes came out of.
    if (name === 'payload') { payloadLength = raw.length; }
  }
  if (raw === '') {
    // A .musx record has no undecoded bytes -- EnigmaXML arrives as XML -- so
    // the source form to show is the XML itself. Rebuilt here from the parse
    // rather than carried in the payload, which would have doubled it. Nothing
    // is lost in the round trip: a Record keeps every attribute verbatim and
    // maps every child element into its fields, coercing none of them.
    const box = document.createElement('div');
    box.className = 'hex';
    box.textContent = rec.xml || '';
    right.appendChild(box);
  } else {
    // Absent for most tags, and that is the honest answer rather than a gap:
    // this project has decoded nine record payloads, and a document carries
    // upwards of 180 tags. Untinted hex says "not decoded"; a layout guessed
    // at would say something false.
    let layout = ((data.layouts || {})[pool] || {})[tag];
    // No full layout, but the catalogue knows where this record's name begins.
    // The fields are built here rather than carried in the payload because
    // their extent is a property of the bytes: a name runs to the first NUL,
    // and how far that is differs per record and per slot.
    if (!layout && named && typeof named.textAt === 'number') {
      // A strided record holds several names, one per slot -- `fg` carries two
      // in a 120-byte payload. One field per slot rather than one field
      // repeated, because each name is its own length, and a repeated field
      // would tint the second slot to the first name's width.
      const stride = named.textStride || payloadLength;
      const fields = [];
      for (let base = 0; base + named.textAt < payloadLength; base += stride) {
        const at = base + named.textAt;
        let end = raw.indexOf(String.fromCharCode(0), at);
        if (end < 0 || end > base + stride) { end = Math.min(base + stride, payloadLength); }
        if (end > at) {
          fields.push({
            offset: at,
            size: end - at,
            name: 'name',
            type: 'char[]',
            note: 'runs to the first NUL; the bytes around it are not decoded',
          });
        }
        if (!named.textStride) { break; }
      }
      if (fields.length) {
        layout = {record: named.name, stride: 0, fields: fields};
      }
    }
    right.appendChild(hexBlock(raw, tintMap(layout, payloadLength)));
    if (!layout) {
      // Say it rather than showing nothing. Nine record payloads are decoded
      // against roughly 180 tags in a document, so most records land here, and
      // an empty space below the hex reads as a table that failed to render
      // rather than as the honest answer.
      const none = document.createElement('p');
      none.className = 'txt';
      none.textContent = 'No field layout is known for this record, so the bytes '
        + 'above are shown undecoded.';
      right.appendChild(none);
    }
    if (layout) {
      const caption = document.createElement('p');
      caption.className = 'txt';
      const slots = layout.stride
        ? ', in ' + Math.ceil(payloadLength / layout.stride) + ' slots of ' + layout.stride +
          ' bytes — the table shows the first'
        : '';
      caption.textContent = 'decodes as ' + layout.record + slots;
      right.appendChild(caption);
      right.appendChild(layoutTable(layout, raw, data.byteOrder));
    }
  }
  // Whatever the record carries that is neither its bytes nor its key. For a
  // .mus `others` or `details` record that is nothing at all: an "addressed by"
  // block used to sit here restating the cmper and part, which are the key and
  // could never differ from it. A DCL row still has `incidences` -- how many
  // rows were joined to assemble the payload -- which the key does not say.
  const rest = {};
  for (const [k, v] of Object.entries(rec.fields || {})) {
    if (!BYTE_FIELDS.includes(k)) { rest[k] = v; }
  }
  if (Object.keys(rest).length !== 0) {
    right.appendChild(fields(rest));
  }
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
  // The engraved staves are already in the page, written as markup rather than
  // rebuilt from the payload. This fills the tree beneath them.
  const el = document.getElementById('music-tree');
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
renderRecords();
show('music');
"""
)


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


def _notation(inspection: Inspection) -> str:
    """The engraved pages, or a line saying why there are none.

    Verovio's SVG goes in verbatim: it is generated markup, not document text,
    and it is the one thing on this page that must not be escaped. Nothing from
    the file reaches it as markup either -- the engraver is handed a `Score`,
    which is the parser's own typed model, and every string in it has already
    been through MusicXML serialisation.
    """
    engraving = inspection.notation
    if engraving is None or not engraving.pages:
        stage = next((s for s in inspection.stages if s.name == "engrave notation"), None)
        why = f"the {stage.name} stage {stage.status}" if stage else "it was not reached"
        return f'<p class="stopped">No notation — {_text(why)}. See the Debug tab.</p>'
    omitted = ""
    if engraving.omitted:
        omitted = (
            f'<p class="meta">Showing {len(engraving.pages)} of {engraving.total} pages; '
            f"the rest are omitted to keep the report a size worth opening.</p>"
        )
    pages = "".join(f'<div class="page">{page}</div>' for page in engraving.pages)
    return f'<div class="score">{pages}</div>{omitted}'


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
            "records": inspection.records,
            "tags": inspection.tags,
            "layouts": inspection.layouts,
            "byteOrder": inspection.byte_order,
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
        f'<section id="music">{_notation(inspection)}<div id="music-tree"></div></section>'
        '<section id="records"></section>'
        '<section id="debug">'
        "<h2>File</h2>"
        f'<p class="meta">{meta}</p>{notes}'
        "<h2>Pipeline</h2>"
        f"{_ladder(inspection)}"
        '<h2>Stats</h2><div id="stats"></div>'
        "</section>"
        f'<script id="inspection" type="application/json">{payload}</script>'
        f"<script>//<![CDATA[\n{_SCRIPT}\n//]]></script>"
        "</body></html>"
    )
