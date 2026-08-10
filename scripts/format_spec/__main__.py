"""Assemble the Finale file format specification and render it to HTML.

Run:  python build.py  ->  finale-formats.html  ->  (Chrome) finale-formats.pdf
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from finale_file_parser.enigma import crypt as CRYPT
from finale_file_parser.enigma import mus_payload as PAY
from finale_file_parser.version import mus as MUSHDR

from . import catalog, content
from .catalog import render_durations, render_note_flags
from .hexview import cite, render_footnotes, render_pie, render_staff, render_struct
from .style import CSS

S = content.ALL_STRUCTS

SECTIONS: list[tuple[str, str]] = []


def section(title: str, body: str) -> None:
    SECTIONS.append((title, body))


# ---------------------------------------------------------------- 1. scope
CITE_ETF = cite(
    "<em>Enigma Transportable File Specification</em>, Coda Music Technologies. "
    "Identified by the Library of Congress as version 98c.0, for Finale 97 for Mac "
    "and Windows: <code>loc.gov/preservation/digital/formats/fdd/fdd000633.shtml</code>. "
    "Vendored as <code>docs/etfspec.pdf</code>."
)
CITE_EEPPD = cite(
    "<em>Enigma Entry Pool: preliminary documentation</em>, Coda Music Technologies, "
    "8 February 1996. Archived at <code>web.archive.org/web/19990203113959/"
    "http://www.codamusic.com:80/down/finale/eeppd.txt</code>. Vendored as "
    "<code>docs/eeppd.txt</code>."
)
CITE_COMMUNITY = cite(
    "Principally <em>denigma</em> (MIT), <code>github.com/chrisroode/denigma</code>, "
    "which credits Deguerre for the <code>score.dat</code> keystream; the "
    "<em>EnigmaXML documentation</em> (MIT), "
    "<code>github.com/Project-Attacca/enigmaxml-documentation</code>; and "
    "<em>musxdom</em> (MIT), <code>github.com/rpatters1/musxdom</code>. The full "
    "list, with what each contributed, is in <code>docs/REFERENCES.md</code>."
)
CITE_MIRROR = cite(
    "<em>Enigma Entry Pool: preliminary documentation</em> (see note 2), which "
    "records the term: &ldquo;Certain situations like mirrors and voice 2 create "
    "complications.&rdquo;"
)
CITE_BILLION = cite(
    "&ldquo;Billion laughs attack&rdquo;, Wikipedia: "
    "<code>en.wikipedia.org/wiki/Billion_laughs_attack</code>."
)
CITE_XXE = cite(
    "&ldquo;XML external entity attack&rdquo;, Wikipedia: "
    "<code>en.wikipedia.org/wiki/XML_external_entity_attack</code>."
)
CITE_UNITS = cite(
    "Both expansions are Coda's, from the ETF specification (see note 1): "
    "&ldquo;the entry duration in EDUs (Enigma Duration Units, 1024 == quarter "
    "note)&rdquo; and &ldquo;manual positioning in EVPUs (Enigma Virtual Page "
    "Units, 288 per inch)&rdquo;."
)

section(
    "Scope and provenance",
    f"""
<p class=lead>This document describes the binary layout of Finale's
<code>.mus</code> and <code>.musx</code> files as reconstructed by the
<code>finale-file-parser</code> project. Finale was discontinued in 2024 and its
format was never published; everything here comes from analyzing a curated
corpus, from two Coda documents{CITE_ETF}{CITE_EEPPD} vendored into the
repository, and from prior community research.{CITE_COMMUNITY}</p>

<p>It is written for someone implementing a reader. Every structure is given as
a C-style declaration, a field table, and a hex dump.</p>

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
    f"""
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
<p>The figures the parser is measured against, over 639 documents. 631 build a
score.</p>
{
        render_pie(
            [
                (".musx, 401 of 401", 401, "#4a7fb5"),
                ("2011 .mus, 99 of 99", 99, "#5da36a"),
                ("DCL .mus, 131 of 139", 131, "#c9954a"),
                ("Other", 8, "#b5534a"),
            ]
        )
    }

<h4>The other eight files</h4>
<dl>
<dt>Six empty scores</dt>
<dd>These files appear to be empty. They carry staves and measures, but no
notes. The reader refuses them rather than returning an empty score, because an
empty result is indistinguishable from a parse that went wrong.</dd>

<dt>One mirror</dt>
<dd><strong>Mirror</strong> is Coda's own term &mdash; their 1996
documentation{CITE_MIRROR} warns that &ldquo;mirrors and voice 2 create
complications&rdquo;, and Finale shipped a Mirror Tool for creating them.</p>

<p>A mirror is a staff that <em>displays another staff's music instead of
holding its own copy</em>. An engraver reaches for one when two parts play the
same thing &mdash; a doubled line, a cue, a piano reduction of what the winds
are doing. Rather than duplicating the notes, the second staff is pointed at the
first, so editing the original changes both.</p>

<p>Stored, this means exactly what it sounds like: there is one set of entries,
and two <code>gfhold</code> records name the same entry span. Nothing marks
either as the copy. To a reader walking the frame chain, the same entries simply
turn up twice, in two different places in the score.</p>

<p>Five DCL documents in the corpus contain mirrors; four read fine,
because their mirrored spans are named once. The one that fails is the only
document where <em>two</em> <code>gfhold</code> records name the same entry
span, which would require a single entry to exist in two places at once. The
intermediate representation gives an entry exactly one location, so supporting
this is a design change rather than a decoding problem.</dd>

<dt>One with a measure count mismatch</dt>
<dd>A file has 36 measures declared in the <code>measSpec</code> records, but
measures as high as 111 appear in the <code>gfhold</code> records. The measures
being referenced are not in the file, so most of the score cannot be
reconstructed.</dd>
</dl>

<div class=warn><strong>Not covered.</strong> Finale versions between 2005 and
2011, and before 2001, are absent from the corpus and therefore absent from
this document. Nothing here should be assumed to hold for them.</div>
""",
)

# ------------------------------------------------- 3. byte order etc
section(
    "Byte order, compression, and encryption",
    f"""
<h3>Byte order is determined by the underlying architecture</h3>
<p>For DCL-era <code>.mus</code> files, integers are written in the byte order of
the machine that saved the file: <strong>big-endian on Mac, little-endian on
Windows</strong>. This governs the pool records and every field inside them.</p>

<p>It is <em>detected, not assumed</em>, and the first pool record makes that
possible. Its <code>kind</code> field is always
{PAY.POOL_OTHERS}, and {PAY.POOL_OTHERS} in a 16-bit field is
<code>0f 00</code> in little-endian and <code>00 0f</code> in big-endian. So
a reader tries one order, and if the first two bytes do not give
{PAY.POOL_OTHERS} it tries the other: the wrong order yields 3,840, which is not
a pool kind. One field, read two ways, decides the whole file.</p>

<p>The check that the choice was right is that the <strong>chain walks to the
last byte exactly</strong>. Each pool record's <code>length</code> says how far
the next one begins, so a reader adds lengths from <code>0x200</code> and lands
on record after record. If the byte order were wrong the lengths would be wrong,
and the walk would overshoot the end of the file or stop short of it. Landing
precisely on the final byte, with no gap and no overrun, is strong evidence that
every length was read correctly. All 139 DCL documents in the corpus do this:
102 little-endian, 37 big-endian.</p>

<div class=note>All files in the 2011 era are <strong>little-endian</strong>,
since this is after Apple switched to Intel-based Macs.</div>

<h3>Compression</h3>
<dl>
<dt>DCL era (2001&ndash;2005)</dt>
<dd>A chain of PKWARE DCL (&ldquo;implode&rdquo;) records beginning at
<code>0x200</code>. No Python standard-library module reads this format. This
project <strong>wrote its own decoder</strong>, an independent Python port of
Mark Adler's <code>blast.c</code> from zlib's <code>contrib/blast</code>, whose
correctness is pinned by that implementation's own published test vector.</dd>
<dt>2011 era</dt>
<dd>A chain of raw zlib streams, the first located by scanning for the
<code>78 9c</code> header. The standard library reads these.</dd>
<dt><code>.musx</code></dt>
<dd>A ZIP archive. The member <code>score.dat</code> is XOR-obfuscated, and
decodes to zlib-compressed EnigmaXML.</dd>
</dl>
<p>A DCL payload decompresses to about
3.3&ndash;4.5 times its stored size, and a 2011 payload to about
5.9&ndash;8.6 times. Decoded payloads in the corpus run from 32&nbsp;KB to
683&nbsp;KB.</p>

<h3>Reading a file</h3>
<p>Every input is hostile until parsed. A specification that describes only
well-formed files leaves a reader open to three distinct attacks, which need
three distinct defenses.</p>

<dl>
<dt>Decompression bombs</dt>
<dd>A small file can declare an enormous decompressed size, exhausting memory
before anything is validated. Neither DCL nor zlib bounds its own output. This
parser <strong>rejects any score whose decoded payload exceeds
{PAY.MAX_MUS_PAYLOAD // (1024 * 1024)}&nbsp;MiB</strong>, counted across the
whole pool chain rather than per stream, so a chain of individually modest pools
cannot add up to an unbounded total. The largest real payload in the corpus is
683&nbsp;KB, so the limit sits about 90 times above anything legitimate.</dd>

<dt>XML entity attacks</dt>
<dd>A <code>.musx</code> carries XML, and the XML standard's entity mechanism
leaves parsers susceptible to two well-known attacks. A <em>billion laughs</em>
attack{CITE_BILLION} defines nested entities that expand exponentially, so a few
kilobytes of markup inflate to gigabytes in memory. An <em>XML external
entity</em> (XXE) attack{CITE_XXE} declares an entity pointing at a local file or
a network address, and a parser that resolves it reads that file or makes that
request on the attacker's behalf. Neither was intended by the standard; both
follow from a feature it does include. All XML in this project is parsed with
<strong><code>defusedxml</code></strong>, which disables entity expansion and
external references. This is the project's only runtime dependency, and it
exists for this reason alone.</dd>

<dt>Malformed offsets and lengths</dt>
<dd>Every offset and length in this document is read <em>from the file</em>,
and may be incorrect. A record can declare a length running past the end of its pool,
a frame can name entries that do not exist, and a walk can be steered into an
infinite loop. Each such value is bounds-checked before use, and a file that
fails a check raises a clear error naming what was wrong &mdash; never a crash,
a hang, or a silent truncation.</dd>
</dl>

<h3>The <code>score.dat</code> obfuscation</h3>
<p><code>score.dat</code> is XOR-ed with a keystream from a BSD
<code>rand()</code> linear congruential generator, whose state advances as
<code>state = state &times; {CRYPT.MULTIPLIER:#x} + {CRYPT.INCREMENT:#x}</code>
(mod 2<sup>32</sup>), starting from the fixed seed
<code>{CRYPT.INITIAL_STATE:#x}</code>. The generator is restarted from that same
seed at every {CRYPT.RESET_EVERY // 1024}&nbsp;KiB boundary, so the keystream is
one {CRYPT.RESET_EVERY // 1024}&nbsp;KiB block repeated end to end for the whole
file.</p>



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
{MUSHDR.MUS_METADATA_SIZE} (<code>0x{MUSHDR.MUS_METADATA_SIZE:X}</code>) bytes
carry the version banner and two provenance stamps.</p>
{render_struct(S["mus_file_header"]())}
<p>The banner is the primary version evidence. A regular expression of the form
<code>Finale\\(R\\)\\s+(\\d{{4}})</code> against the banner text yields the year.
An unrecognized banner should leave the year unset with the raw text preserved,
rather than failing &mdash; an unknown variant stays inspectable that way.</p>
""",
)

# ------------------------------------------------- 5. container layer
section(
    "Container: how the payload is found",
    f"""
<p>A <code>.mus</code> payload is a handful of compressed <em>pools</em>, laid
end to end.</p>

<table>
<thead><tr><th>Pool</th><th>kind</th><th>Holds</th></tr></thead>
<tbody>
<tr><td>others</td><td>{PAY.POOL_OTHERS}</td>
<td>most record types, keyed by one cmper (a record's key; see &sect;6)</td></tr>
<tr><td>details</td><td>{PAY.POOL_DETAILS}</td><td>records keyed by a pair of cmpers</td></tr>
<tr><td>entries</td><td>{PAY.POOL_ENTRIES}</td><td>the notes themselves</td></tr>
<tr><td>text</td><td>{PAY.POOL_TEXT}</td><td>human-readable strings</td></tr>
</tbody></table>

<h3>DCL era: a labeled chain</h3>
<p>Records run from <code>0x200</code> to the last byte of the file, with no
gaps. The DCL era <strong>labels</strong> its pools: every pool record opens
with a two-byte <code>kind</code> field naming which pool follows &mdash;
{PAY.POOL_OTHERS} others, {PAY.POOL_DETAILS} details, {PAY.POOL_ENTRIES}
entries, {PAY.POOL_TEXT} text.</p>
{render_struct(S["dcl_pool_record"]())}

<h3>2011 era: an unlabeled chain</h3>
<p>The first zlib stream is found by scanning for the <code>78 9c</code> header,
and the rest follow one after another. There is no <code>kind</code> field, so
nothing in the container says which pool a given stream holds.</p>

<p>A reader therefore identifies each pool <strong>by recognizing its
shape</strong> rather than by counting positions. Each stream is tried against
the structure a pool is expected to have, and the one that parses is that pool:
a stream is the <code>others</code> pool if it walks cleanly as a run of
self-identifying records and yields a plausible number of them, and the
<code>entries</code> pool if it divides exactly into 38-byte slots with
consistent entry numbers. A stream that satisfies neither is left alone.</p>

<p>The order <em>is</em> consistent in practice. Across all 99 2011-era corpus
documents the <code>others</code> pool is the first stream, without exception,
and the text pool is last in 98 of them. So a reader keyed to position would
work on every file measured here.</p>

<div class=note>Recognition is still the right choice, because position is an
assumption a file can violate and shape is not. A reader relying on order would
fail <em>silently</em> on the first file that broke the pattern &mdash; producing
a wrong score rather than an error &mdash; and 99 documents from a two-year
window is thin evidence for a rule the format never states. More data would
raise confidence in the ordering; it would not make the ordering a
guarantee.</div>
""",
)

# ------------------------------------------------- 6. record framing
section(
    "Records: framing and addressing",
    f"""
<h3>What a record is</h3>
<p>A record is an object that contains three things:</p>
<dl>
<dt>A tag</dt><dd>What kind of record this is &mdash; <code>measSpec</code>,
<code>gfhold</code>. The full vocabulary is catalogued at the end of this
section.</dd>
<dt>One or more keys</dt><dd>What a record is about. A <code>measSpec</code>
keyed 7 is measure 7; a <code>gfhold</code> keyed (3, 7) is staff 3,
measure 7.</dd>
<dt>A payload</dt><dd>Bytes whose meaning depends entirely on the tag. There is
no self-description inside a payload: without the tag, the bytes mean
nothing.</dd>
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

<p><code>frameSpec</code> is what makes this look like containment. Reading
&ldquo;a frame holds entries 101 to 108&rdquo;, it is natural to picture the
entries sitting inside the frame. They do not. The <code>frameSpec</code>
record's payload is eight bytes: the number 101 and the number 108. The entries
are in a different pool entirely, each keyed by its own number, and the
<code>frameSpec</code> merely names two of those keys.</p>

<p>Concretely: a <code>frameSpec</code> is the same size on disk whether it names
two entries or two hundred. Delete one and entries 101 to 108 are still in the
entry pool, unchanged and readable &mdash; there is simply nothing left saying
which staff and measure they belong to.</p>

<pre class=cstruct>file
&#9492;&#9472;&#9472; pools                    others &#183; details &#183; entries &#183; text
    &#9492;&#9472;&#9472; records              a pool is a flat run of them
        &#9492;&#9472;&#9472; (entries pool)
            &#9492;&#9472;&#9472; entry        a record: one chord or rest at one point in time
                &#9492;&#9472;&#9472; notes    6-byte note records &#8212; real containment</pre>

<p><strong>Notes are the one genuine nesting in the format.</strong> An entry's
payload holds its own <code>noteCount</code> and the note records themselves;
they have no independent key and cannot be addressed from outside.</p>

<p>Everything else a score holds lives in a record's <em>payload</em>, as
fields. A lyric syllable, a staff name and a page margin are all payload bytes
of some record, addressed by offset once the tag is known. What makes an entry's
notes different is that they are a <em>repeated substructure</em>, counted by a
field of their parent, rather than fields at fixed offsets.</p>

<div class=note>In one line: <strong>pools contain records, records reference
each other by key, and a record's payload holds its fields &mdash; of which only
an entry's notes are themselves a repeated substructure.</strong></div>

<h3>2011 era: self-identifying records</h3>
{render_struct(S["mus2011_record"]())}

<h3>DCL era: fixed ETF rows</h3>
<p>The same information, encoded completely differently. Where a 2011 record
carries its own length, a DCL row is always 16 bytes and a long record simply
continues into the next row.</p>
{render_struct(S["dcl_others_row"]())}
{render_struct(S["dcl_details_row"]())}

<h3>How items point to each other</h3>
<p>Addressing is by <strong>key</strong>, and the keys are small integers.</p>
<dl>
<dt><code>cmper</code> (&ldquo;comparator&rdquo;)</dt>
<dd>A record's key &mdash; the <code>(n)</code> in ETF's <code>^XX(n)</code>
notation. What it counts depends on the tag: for a <code>measSpec</code> it is
the measure number, for a <code>staffSpec</code> the staff. The tag tables below
give the key's meaning for every documented record.</dd>
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
<pre class=cstruct>for staff in staves:
    for measure in measures:
        hold = details["GF", staff, measure]     # absent =&gt; staff rests here
        if hold is None:
            continue
        for layer in 0..3:
            frame_id = hold.frame[layer]         # 0 =&gt; layer is empty
            if frame_id == 0:
                continue
            frame = others["FR", frame_id]
            for entry in entries[frame.startEntry .. frame.endEntry]:
                emit(entry, staff, measure, layer)</pre>

<p>Four key lookups and no arithmetic on file positions. The entry range is
inclusive at both ends.</p>

<h4>Two ways to reach the same notes</h4>
<p>A layer's entries are also chained: every entry carries <code>prev</code> and
<code>next</code>, each holding another entry's number, so the entries of a
layer form a doubly linked list running across the whole staff. Coda's
documentation describes the pool this way, as entries &ldquo;streamed together
in a doubly linked list that roughly corresponds to a voice on a staff&rdquo;.
The frame gives the same run's two endpoints.</p>

<p>Either route reaches the same notes, and the reader above uses the frame
because it is the one that answers the question being asked. Walking the chain
tells you what follows a given entry; it does not tell you which measure or
staff you are in, since the chain runs straight through barlines. The
<code>gfhold</code> is what supplies that, so a reader wanting music
<em>by position</em> starts from the frame. A reader wanting to follow a voice
forward &mdash; to resolve a tie, say &mdash; follows the chain instead.</p>

<div class=note><strong>An entry reached by more than one frame.</strong> Two
frames naming the same entry span is how a <em>mirror</em> is stored
(&sect;2) &mdash; one staff displaying another's music. Nothing in the record
marks it as such: the two <code>gfhold</code> records are ordinary, and the only
sign is that their frames resolve to the same entries.

<p>The record decodes without difficulty; what is hard is representing it. An
intermediate form that gives each entry one location cannot hold an entry that
sounds in two places, so this implementation refuses such a document rather than
place the notes wrongly. That is a limitation of the representation, not of the
decoding, and one of the eight non-building corpus documents is a case of
it.</p></div>
"""
    + catalog.render_tag_tables(),
)

# ------------------------------------------------- 7. the entry pool
section(
    "The entry pool",
    f"""
<p>The entry pool contains the actual musical notes &mdash; both pitch and
duration. It is the one structure the two <code>.mus</code> eras share field for
field, differing only in the byte order their integers are written in.</p>

<h4>Two units, and one word, used throughout</h4>
<dl>
<dt>EDU &mdash; Enigma Duration Units</dt>
<dd>Coda's time unit, in which <strong>1024 is a quarter note</strong>. A whole
note is 4096, a dotted quarter 1536.{CITE_UNITS}</dd>
<dt>EVPU &mdash; Enigma Virtual Page Units</dt>
<dd>Coda's distance unit, <strong>288 to the inch</strong>. Positions and widths
elsewhere in this document are in EVPU.{CITE_UNITS}</dd>
<dt>Entry</dt>
<dd>In Coda's terminology an entry is <strong>a note, a chord, or a
rest</strong>. A chord is one entry with several notes, not several entries.</dd>
</dl>
{render_struct(S["entry_first_slot"]())}
<h3>The note record</h3>
<h4>TCD &mdash; Tone Center Displacement</h4>
<p>The first two bytes of a note record are a single 16-bit field Coda calls the
<strong>TCD</strong>. It carries two things at once: which pitch, and how that
pitch is altered against the key.</p>

<pre class=cstruct>bit   15 14 13 12 11 10  9  8  7  6  5  4   3   2  1  0
     +--------------------------------------+---+--------+
     |        harmonic value (12 bits)      | s | m m m  |
     +--------------------------------------+---+--------+
        diatonic step, signed, 0 = tonic      ^   alteration
                                              sign</pre>

<h4>The harmonic value</h4>
<p>The harmonic value is a diatonic step relative to the current key. 0 is the
tonic; &minus;1 is a step below, while 7 is an octave up.</p>
<p>The value counts <em>steps of the key</em>, not semitones, so the same
numbers name different pitches in different keys:</p>

{
        render_staff(
            [("C4", "0"), ("D4", "1"), ("B3", "&minus;1"), ("C5", "7")],
            0,
            "C major. Harmonic value below each note; all four have alteration 0.",
        )
    }

{
        render_staff(
            [("G4", "0"), ("A4", "1"), ("F4", "&minus;1"), ("G5", "7")],
            1,
            "G major, one sharp. The same four values. The third is F sharp, "
            "which the key already provides, so its alteration is 0 too.",
        )
    }

<p>This is why transposing a passage by changing its key signature moves every
note with it and rewrites nothing: the stored numbers do not change.</p>

<h4>The alteration</h4>
<p>The alteration is how far the note departs from that diatonic step: 0 means
the note the key gives, +1 a semitone above it, &minus;1 a semitone below.</p>
<p>It is measured against the key, not against the printed accidental:</p>

{
        render_staff(
            [
                ("F4", "&minus;1, alt 0"),
                ("F4", "&minus;1, alt &minus;1"),
                ("F4", "&minus;1, alt +1"),
            ],
            1,
            "G major. The same harmonic value, three alterations: F sharp as "
            "the key gives it, F natural a semitone below, F double sharp a "
            "semitone above.",
        )
    }

<p>So in G major <strong>F&#9839; has an alteration of 0</strong> &mdash; the key
already provides it &mdash; and an F natural is <strong>&minus;1</strong>, even
though the natural is the sign the engraver prints.</p>

<div class=warn><strong>The alteration is sign-and-magnitude, not two's
complement.</strong> Bit 3 is a sign, and bits 2&ndash;0 a magnitude from 0 to 7.
Coda's documentation calls it &ldquo;a signed quantity ... -8 to +7&rdquo;,
which reads as two's complement; the corpus disagrees, and the corpus wins.

<p>The two readings agree on naturals and sharps and diverge on every flat.
<code>0x1</code> is +1 either way, but <code>0x9</code> = binary
<code>1001</code> is <strong>&minus;1</strong> &mdash; sign set, magnitude 1.
Read as two's complement the same nibble is &minus;7, which spells a note six
steps away from the one Finale displays.</p></div>

{render_struct(S["note_record"]())}

<h4>The note flags</h4>
<p>The 32-bit field holds a note's properties. The id mask is the one an
implementer meets soonest: entry details such as articulations and performance
data address <em>one note of a chord</em> by that id.</p>
{render_note_flags()}

<h4>Durations</h4>
<p>Durations are measured in <strong>EDU</strong>, where 1024 is a quarter note
and 4096 a whole note. A dot adds half again, so a dotted quarter is 1536 and a
double-dotted quarter 1792.</p>

<p>Every duration observed across the 238 corpus <code>.mus</code> documents
&mdash; 108,466 of them &mdash; takes one of sixteen values:</p>

{render_durations()}
""",
)


# ------------------------------------------------- 8. the .musx container
section(
    "The <code>.musx</code> container",
    """
<p>A <code>.musx</code> is a ZIP archive. Unlike the two <code>.mus</code> eras
it needs no bespoke container walking &mdash; a standard ZIP reader opens it &mdash;
but its payload is encrypted.</p>

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

# ------------------------------------------------------- 9. catalog
section(
    "Record catalog",
    "<p>Every record type this project decodes, with the offsets its reader "
    "actually uses. Fields not listed are present in the payload but not yet "
    "established; they are omitted rather than guessed at.</p>" + catalog.render_catalog(),
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
        f"{body}"
        f'<section id="refs"><h2>References</h2>{render_footnotes()}</section>'
        "</body></html>"
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
