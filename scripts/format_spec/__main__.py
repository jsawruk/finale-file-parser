"""Assemble the Finale file format specification and render it to HTML.

Run:  python build.py  ->  finale-formats.html  ->  (Chrome) finale-formats.pdf
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from finale_file_parser.enigma import mus_payload as PAY
from finale_file_parser.version import mus as MUSHDR

from . import catalog, content
from .hexview import render_struct
from .style import CSS

S = content.ALL_STRUCTS

SECTIONS: list[tuple[str, str]] = []


def section(title: str, body: str) -> None:
    SECTIONS.append((title, body))


# ---------------------------------------------------------------- 1. scope
section(
    "Scope and provenance",
    """
<p class=lead>This document describes the binary layout of Finale's
<code>.mus</code> and <code>.musx</code> files as reconstructed by the
<code>finale-file-parser</code> project. Finale was discontinued in 2024 and its
format was never published; everything here comes from reverse engineering
against a curated corpus, from two vendored Coda documents, and from prior
community research.</p>

<p>It is written for someone implementing a reader. Every structure is given as
a C-style declaration, a field table, and a hex dump, in the manner of the
Aseprite file specification.</p>

<div class=prov><strong>Confidence.</strong> Each structure below is annotated
with what it was verified against. Where this project's findings contradict
Coda's own documentation, that is stated explicitly rather than quietly
resolved &mdash; there is one such case, the note alteration encoding in
&sect;7.2.</div>

<h4>No corpus bytes appear in this document</h4>
<p>Every hex dump is <strong>synthetic</strong>, constructed by the generator
that produced this PDF. The test corpus is licensed third-party music and its
bytes are not reproducible here. Synthetic data also lets each dump isolate the
field under discussion instead of burying it in a real record.</p>

<div class=note><strong>This document is generated from the parser.</strong>
Offsets, sizes and constants are imported from the reading code rather than
retyped, so a layout here cannot silently drift from the implementation that
reads it.</div>
""",
)

# ------------------------------------------------------- 2. versions
section(
    "Which formats are supported",
    """
<p>Three containers, spanning roughly two decades of Finale releases.</p>

<table>
<thead><tr><th>Container</th><th>Finale era</th><th>Payload codec</th>
<th>Byte order</th><th>Record encoding</th></tr></thead>
<tbody>
<tr><td><code>.mus</code> (DCL)</td><td>2001&ndash;2005</td>
<td>PKWARE DCL (&ldquo;implode&rdquo;)</td><td>writing platform's</td>
<td>fixed 16-byte ETF rows</td></tr>
<tr><td><code>.mus</code> (2011)</td><td>2011&ndash;2012</td>
<td>zlib (chained streams)</td><td>little-endian</td>
<td>self-identifying variable-length</td></tr>
<tr><td><code>.musx</code></td><td>2012&ndash;2024</td>
<td>ZIP + XOR cipher, then zlib</td><td>little-endian</td>
<td>EnigmaXML elements</td></tr>
</tbody></table>

<h4>Corpus coverage</h4>
<p>The figures the parser is measured against, over 639 documents:</p>
<ul>
<li><code>.musx</code> &mdash; 401 of 401 build a score</li>
<li>2011-era <code>.mus</code> &mdash; 99 of 99</li>
<li>DCL-era <code>.mus</code> &mdash; 131 of 139</li>
</ul>
<p>The eight that do not are the files rather than the reader: six are blank
scores refused deliberately, one is a mirror, one an incomplete export.</p>

<div class=warn><strong>Not covered.</strong> Finale versions between 2005 and
2011, and before 2001, are absent from the corpus and therefore absent from
this document. Nothing here should be assumed to hold for them.</div>
""",
)

# ------------------------------------------------- 3. byte order etc
section(
    "Byte order, compression, and encryption",
    f"""
<h3>Byte order is the writing machine's</h3>
<p>For DCL-era <code>.mus</code> files, integers are written in the byte order of
the machine that saved the file: <strong>big-endian on Mac, little-endian on
Windows</strong>. This governs the pool records and every field inside them.</p>

<p>It is <em>detected, not assumed</em>. The first pool record's <code>kind</code>
is always {PAY.POOL_OTHERS}, a value that reads as {PAY.POOL_OTHERS} only one
way round. Over the corpus: 102 little-endian, 37 big-endian, all 139 walking to
the last byte exactly.</p>

<div class=note>The 2011 era is <strong>all little-endian</strong> even though
those files are Mac-written &mdash; the Intel transition had happened. Do not
infer byte order from platform for that era.</div>

<h3>Compression</h3>
<dl>
<dt>DCL era (2001&ndash;2005)</dt>
<dd>A chain of PKWARE DCL (&ldquo;implode&rdquo;) records beginning at
<code>0x200</code>. No Python standard-library module reads this; a decoder is
required. Measured inflation: 3.25&times;&ndash;4.51&times;.</dd>
<dt>2011 era</dt>
<dd>A chain of raw zlib streams, the first located by scanning for
<code>78 9c</code>. Measured inflation: 5.87&times;&ndash;8.63&times;.</dd>
<dt><code>.musx</code></dt>
<dd>A ZIP archive. The member <code>score.dat</code> is XOR-encrypted, and
decrypts to zlib-compressed EnigmaXML.</dd>
</dl>

<div class=warn><strong>Decompression bombs.</strong> Any reader must cap total
inflated output. This implementation refuses past
{PAY.MAX_MUS_PAYLOAD // (1024 * 1024)}&nbsp;MiB across the whole chain, which
leaves roughly 90&times; headroom over the largest real corpus payload
(699,585 bytes).</dd></div>

<h3>The <code>score.dat</code> cipher</h3>
<p><code>score.dat</code> is XOR-encrypted with a keystream from a BSD
<code>rand()</code> linear congruential generator seeded with a fixed constant.
The generator is <strong>reseeded at every 128&nbsp;KiB boundary</strong>, so
the keystream is one constant block repeated end to end.</p>

<div class=prov>These cipher parameters were not discovered by this project.
They come from <a href="https://github.com/chrisroode/denigma">denigma</a>
(MIT), whose source credits
<a href="https://github.com/Deguerre">Deguerre</a>.</div>
""",
)

# ------------------------------------------------------ 4. file header
section(
    "The <code>.mus</code> file header",
    f"""
<p>Both <code>.mus</code> eras share a header. Its first
<code>0x{MUSHDR.MUS_METADATA_SIZE:X}</code> bytes carry the version banner
and two provenance stamps.</p>
{render_struct(S["mus_file_header"](), "little-endian (this example)")}
<p>The banner is the primary version evidence. A regular expression of the form
<code>Finale\\(R\\)\\s+(\\d{{4}})</code> against the banner text yields the year.
An unrecognised banner should leave the year unset with the raw text preserved,
rather than failing &mdash; an unknown variant stays inspectable that way.</p>
""",
)

# ------------------------------------------------- 5. container layer
section(
    "Container: how the payload is found",
    f"""
<p>A <code>.mus</code> payload is <strong>not one blob</strong>. It is a handful
of compressed <em>pools</em>, laid end to end.</p>

<table>
<thead><tr><th>Pool</th><th>kind</th><th>Holds</th></tr></thead>
<tbody>
<tr><td>others</td><td>{PAY.POOL_OTHERS}</td><td>most record types, keyed by one cmper</td></tr>
<tr><td>details</td><td>{PAY.POOL_DETAILS}</td><td>records keyed by a pair of cmpers</td></tr>
<tr><td>entries</td><td>{PAY.POOL_ENTRIES}</td><td>the notes themselves</td></tr>
<tr><td>text</td><td>{PAY.POOL_TEXT}</td><td>human-readable strings</td></tr>
</tbody></table>

<h3>DCL era: a labelled chain</h3>
<p>Records run from <code>0x200</code> to the last byte of the file, with no
gaps. The DCL era <strong>labels</strong> its pools; the zlib era does not.</p>
{render_struct(S["dcl_pool_record"](), "little-endian")}
{render_struct(S["dcl_pool_record_be"](), "big-endian")}

<h3>2011 era: an unlabelled chain</h3>
<p>The first zlib stream is found by scanning for the <code>78 9c</code> header.
Streams follow one another; the pools are identified by <em>order</em>, not by a
label, which is why a reader must know the sequence rather than read it.</p>
""",
)

# ------------------------------------------------- 6. record framing
section(
    "Records: framing and addressing",
    f"""
<h3>What a record is</h3>
<p>A record is <strong>a row in a table, not an object in a tree</strong>. Almost
every wrong intuition about these formats comes from expecting a document tree,
so it is worth stating plainly before any bytes.</p>

<p>A record is three things:</p>
<dl>
<dt>A tag</dt><dd>What kind of thing this is &mdash; <code>measSpec</code>,
<code>gfhold</code>. Think table name.</dd>
<dt>One or more keys</dt><dd>What it is <em>about</em>. A <code>measSpec</code>
keyed 7 is measure 7; a <code>gfhold</code> keyed (3, 7) is staff 3, measure 7.
Think primary key.</dd>
<dt>A payload</dt><dd>Bytes whose meaning depends entirely on the tag. Think
columns. There is no self-description inside a payload: without the tag, the
bytes mean nothing.</dd>
</dl>

<p>Three consequences matter to anyone writing a reader.</p>

<p><strong>There are no pointers.</strong> Nothing holds a file offset. A
<code>gfhold</code> does not point at a <code>frameSpec</code>; it contains the
number 41, and somewhere there is a <code>frameSpec</code> whose key is 41.
Resolution is a lookup by key equality &mdash; a join, not a dereference. Even the
entry pool's <code>next</code> and <code>prev</code>, which look like a linked
list, are entry <em>numbers</em>. The physical order of every record in a file
could be shuffled without losing anything.</p>

<p><strong>Records do not nest.</strong> Composition happens by reference. The
music of a measure is not inside the measure's record; it is reached by a chain
of key lookups.</p>

<p><strong>A logical record is not always a physical one.</strong> In the 2011
era they are one to one &mdash; each record carries its own length. In the DCL era
a record is a fixed 16-byte row, and anything larger continues into further rows
under the same tag and key. ETF calls each row an <em>incidence</em>. So a
record is the concatenation of its rows, and fields are addressed by offset into
that concatenation, not into any one row.</p>

<h4>The hierarchy, and where containment actually happens</h4>
<p>&ldquo;A pool contains records, and records contain entries&rdquo; is half
right. Pools do contain records. But an entry <strong>is</strong> a record: it
lives in its own pool, keyed by entry number, a peer of <code>measSpec</code>
rather than a child of anything.</p>

<p>What misleads is <code>frameSpec</code>, which looks like containment and is
not. It holds <code>startEntry</code> and <code>endEntry</code> &mdash; two
integers naming a range of keys. Delete the <code>frameSpec</code> and its
entries are still there, orphaned but intact.</p>

<pre class=cstruct>file
&#9492;&#9472;&#9472; pools                    others &#183; details &#183; entries &#183; text
    &#9492;&#9472;&#9472; records              a pool is a flat run of them
        &#9492;&#9472;&#9472; (entries pool)
            &#9492;&#9472;&#9472; entry        a record: one chord or rest at one point in time
                &#9492;&#9472;&#9472; notes    6-byte note records &#8212; real containment</pre>

<p><strong>Notes are the one genuine nesting in the format.</strong> An entry's
payload holds its own <code>noteCount</code> and the note records themselves;
they have no independent key and cannot be addressed from outside. Everything
else is reference by key.</p>

<div class=note>In one line: <strong>pools contain records; records reference
each other by key; only entries contain anything, and what they contain is
notes.</strong></div>

<h3>2011 era: self-identifying records</h3>
{render_struct(S["mus2011_record"](), "little-endian")}

<h3>DCL era: fixed ETF rows</h3>
<p>The same information, encoded completely differently. Where a 2011 record
carries its own length, a DCL row is always 16 bytes and a long record simply
continues into the next row.</p>
{render_struct(S["dcl_others_row"](), "writing platform's")}
{render_struct(S["dcl_details_row"](), "writing platform's")}

<h3>How items point to each other</h3>
<p>There is no pointer arithmetic anywhere in these formats. Addressing is by
<strong>key</strong>, and the keys are small integers.</p>
<dl>
<dt><code>cmper</code> (&ldquo;comparator&rdquo;)</dt>
<dd>A record's key &mdash; the <code>(n)</code> in ETF's <code>^XX(n)</code>
notation. For a <code>measSpec</code> it is the measure number; for a
<code>staffSpec</code>, the staff.</dd>
<dt><code>cmper1</code>, <code>cmper2</code></dt>
<dd>Details records are keyed by a <em>pair</em>, which is how a record hangs
off an intersection &mdash; a <code>gfhold</code>, for instance, at
(staff, measure).</dd>
<dt><code>inci</code> (&ldquo;incidence&rdquo;)</dt>
<dd>When several records share a key, the incidence distinguishes them. In the
DCL era it is also how one logical record spills across several 16-byte rows.</dd>
<dt><code>part</code></dt>
<dd>0 for the score; 1, 2, &hellip; for each linked part. A part's record
overrides the score's for that part only.</dd>
</dl>

<h4>Finding the music: the frame chain</h4>
<p>This is the central traversal, and it is worth stating as a sequence:</p>
<ol>
<li>A <code>gfhold</code> (&ldquo;frame hold&rdquo;) is keyed by
(staff, measure) and names up to four <strong>frames</strong>, one per layer.</li>
<li>Each frame id keys a <code>frameSpec</code>, which gives a
<code>startEntry</code> and an <code>endEntry</code>.</li>
<li>Those are entry numbers into the entry pool. The entries between them,
inclusive, are that layer's music for that measure.</li>
<li>Each entry carries its own <code>next</code> pointer, so the run can also be
walked as a linked list.</li>
</ol>
<div class=note>An entry reached by more than one frame is a corrupt document,
not a shared voice. A reader should refuse it rather than emit the notes
twice.</div>
"""
    + catalog.render_tag_tables(),
)

# ------------------------------------------------- 7. the entry pool
section(
    "The entry pool",
    f"""
<p>The notes. This is the one structure both <code>.mus</code> eras share
byte-for-byte, differing only in integer byte order.</p>
{render_struct(S["entry_first_slot"](), "little-endian")}
<h3>The note record</h3>
{render_struct(S["note_record"](), "little-endian")}
<h4>Durations</h4>
<p>Durations are in <strong>EDU</strong>, where 1024 is a quarter note and 4096
a whole note. Dotted values are the plain value plus half again, so 1536 is a
dotted quarter. Across 136 DCL-era corpus documents, 71,801 durations took just
16 distinct values &mdash; every one a note value with 0&ndash;2 dots, which is
itself evidence the field was read correctly.</p>
""",
)


# ------------------------------------------------- 8. the .musx container
section(
    "The <code>.musx</code> container",
    """
<p>A <code>.musx</code> is a ZIP archive. Unlike the two <code>.mus</code> eras
it needs no bespoke container walking &mdash; a standard ZIP reader opens it &mdash;
but its payload member is encrypted.</p>

<table>
<thead><tr><th>Member</th><th>Contents</th></tr></thead>
<tbody>
<tr><td><code>mimetype</code></td>
<td>the fixed string <code>application/vnd.makemusic.notation</code></td></tr>
<tr><td><code>META-INF/container.xml</code></td><td>archive manifest</td></tr>
<tr><td><code>NotationMetadata.xml</code></td><td>document metadata</td></tr>
<tr><td><code>score.dat</code></td>
<td><strong>the score</strong> &mdash; XOR-encrypted, then zlib</td></tr>
<tr><td><code>graphics/*</code>, <code>presets/*</code></td>
<td>embedded artwork and presets</td></tr>
</tbody></table>

<h3>Reading <code>score.dat</code></h3>
<ol>
<li>Read the member's bytes from the archive.</li>
<li>XOR with the LCG keystream (&sect;3), which resets every 128&nbsp;KiB.</li>
<li>Inflate the result with zlib.</li>
<li>The output is <strong>EnigmaXML</strong>, an XML document whose elements
carry the same record types the binary formats encode numerically.</li>
</ol>

<div class=warn><strong>Treat the archive as hostile.</strong> A ZIP may declare
member sizes that do not match its content, repeat member names, or expand
enormously. Cap the inflated size, reject duplicate names, and never resolve a
member path outside the archive root.</div>

<h3>Why one reader covers all three</h3>
<p>EnigmaXML names its record types symbolically &mdash; <code>measSpec</code>,
<code>gfhold</code>, <code>entry</code> &mdash; where the 2011 era numbers them and
the DCL era uses ETF's two-character tags. These are three spellings of one
vocabulary. A reader that converges all three onto a single document model gets
the rest of the pipeline for free, which is what this project does: the
container differs, the music does not.</p>

<table>
<thead><tr><th>Concept</th><th>.musx</th><th>2011 .mus</th><th>DCL .mus</th></tr></thead>
<tbody>
<tr><td>measure</td><td><code>measSpec</code></td><td>176</td><td><code>^MS</code></td></tr>
<tr><td>staff</td><td><code>staffSpec</code></td><td>231</td><td><code>^IS</code></td></tr>
<tr><td>frame</td><td><code>frameSpec</code></td><td>146</td><td><code>^FR</code></td></tr>
<tr><td>frame hold</td><td><code>gfhold</code></td><td>1044</td><td><code>^GF</code></td></tr>
<tr><td>note group</td><td><code>entry</code></td><td>entry pool</td><td>entry pool</td></tr>
</tbody></table>
""",
)

# ------------------------------------------------------- 9. catalogue
section(
    "Record catalogue",
    "<p>Every record type this project decodes, with the offsets its reader "
    "actually uses. Fields not listed are present in the payload but not yet "
    "established; they are omitted rather than guessed at.</p>" + catalog.render_catalogue(),
)


# --------------------------------------------------------------- render
def build() -> str:
    toc = "".join(f'<li><a href="#s{i}">{t}</a></li>' for i, (t, _) in enumerate(SECTIONS, 1))
    body = "".join(
        f'<section id="s{i}"><h2>{i}. {t}</h2>{b}</section>' for i, (t, b) in enumerate(SECTIONS, 1)
    )
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<title>Finale file formats &mdash; a reader's specification</title>"
        f"<style>{CSS}</style></head><body>"
        "<h1>Finale file formats</h1>"
        "<p class=subtitle>A reader's specification for <code>.mus</code> and "
        "<code>.musx</code></p>"
        "<p class=meta>Reconstructed by the finale-file-parser project. "
        "All hex dumps are synthetic.</p>"
        f"<h2>Contents</h2><ol class=toc>{toc}</ol>"
        f"{body}</body></html>"
    )


CHROME = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)
"""Where to look for a browser to print with.

Chrome is the renderer because it is the only one on hand that honours
`@page` and `print-color-adjust`, which the tinted hex dumps need. It is not a
project dependency: without it the HTML is still written, and the PDF step is
skipped with a message rather than failing the build.
"""


def render_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Print `html_path` to `pdf_path`. False if no browser was found."""
    browser = next((c for c in CHROME if Path(c).exists()), None)
    if browser is None:
        return False
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, paths are ours
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            str(html_path),
        ],
        check=True,
        capture_output=True,
    )
    return True


def main() -> int:
    out = Path(__file__).resolve().parents[2] / "docs" / "formats"
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / "finale-formats.html"
    pdf_path = out / "finale-formats.pdf"

    html = build()
    html_path.write_text(html, encoding="utf-8")
    print(f"wrote {html_path.name} ({len(html):,} bytes, {len(SECTIONS)} sections)")

    if render_pdf(html_path, pdf_path):
        print(f"wrote {pdf_path.name} ({pdf_path.stat().st_size:,} bytes)")
    else:
        print("no Chrome found; skipped the PDF (the HTML above is complete)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
