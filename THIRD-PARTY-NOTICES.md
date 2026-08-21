# Third-party notices

`finale-file-parser` is MIT licensed (see `LICENSE`). It vendors no third-party
code: its install dependencies are `defusedxml` and `verovio`, and the
optional `pdf` extra adds `svglib` and `reportlab` — all used as ordinary
imported packages. Two modules were written *from* third-party work,
and this file carries the notices that work asks to be carried.

`docs/REFERENCES.md` records every source consulted, including ones that
imposed no obligation. This file is narrower: it is the set of notices that
travel with a redistribution.

## `svglib` — SVG to PDF, LGPL-3.0 (optional)

`finale-parser convert --format pdf` converts Verovio's engraved SVG into a PDF
using [svglib](https://github.com/deeplook/svglib), which is **LGPL-3.0**, with
[reportlab](https://www.reportlab.com/) (BSD) underneath it.

Both arrive only with the optional `pdf` extra. A plain
`pip install finale-file-parser` installs neither, so anyone who does not ask
for PDF output carries no obligation for them at all.

Nothing of either is copied into this repository, and the arrangement is the
same one described for Verovio below: separate packages, imported at runtime by
`export/pdf.py`. The same paragraph about bundling applies — shipping this
library, or telling users to install it, carries no new obligation; folding the
LGPL parts into a single distributed artifact does.

## `verovio` — score engraving, LGPL-3.0

The inspection report's Music tab shows the parsed score as notation, engraved
by [Verovio](https://www.verovio.org/), which is **LGPL-3.0** where this project
is MIT.

Nothing of Verovio is copied into this repository. It is installed as a separate
package and imported at runtime — `report/notation.py` calls its toolkit and
embeds the SVG it returns. That is the arrangement the LGPL is written for, and
it leaves this project's own licence unchanged: MIT code may depend on an LGPL
library.

**What it means for a redistributor.** Shipping this library on its own, or
telling users to `pip install finale-file-parser`, carries no new obligation —
Verovio arrives as its own package under its own licence. Bundling it into a
single distributed artifact (a frozen application, a container image presented
as one program) does carry the LGPL's obligations for the Verovio portion:
notably that recipients can replace it with their own build. If that is the
plan, read the licence rather than this paragraph.

The SVG Verovio produces is output, not a derivative of Verovio's code, and is
this project's to embed freely.

## `enigma/blast.py` — PKWARE DCL decompression

An independent Python port of Mark Adler's `blast.c` from zlib's
`contrib/blast`. The format knowledge — the bit-length tables, the inverted
canonical code assignment, the length and distance encodings — is his. The
implementation, its allocation caps, and its error handling are this project's,
and it is not a line-for-line translation.

zlib's licence permits use and modification provided the origin is not
misrepresented and altered versions are marked as such. This port is marked as
altered here, in `docs/REFERENCES.md`, and in the module's own docstring.

    Copyright (C) 2003, 2012, 2013 Mark Adler

    This software is provided 'as-is', without any express or implied
    warranty.  In no event will the author be held liable for any damages
    arising from the use of this software.

    Permission is granted to anyone to use this software for any purpose,
    including commercial applications, and to alter it and redistribute it
    freely, subject to the following restrictions:

    1. The origin of this software must not be misrepresented; you must not
       claim that you wrote the original software. If you use this software
       in a product, an acknowledgment in the product documentation would be
       appreciated but is not required.
    2. Altered source versions must be plainly marked as such, and must not be
       misrepresented as being the original software.
    3. This notice may not be removed or altered from any source distribution.

    Mark Adler    madler@alumni.caltech.edu

## `enigma/crypt.py` — `score.dat` cipher parameters

The cipher's parameters — the fixed LCG seed, the `(upper + upper // 255)`
output function, and the 128 KiB keystream reset — were taken as facts from
[denigma](https://github.com/chrisroode/denigma), which is MIT licensed and
whose own source credits [Deguerre](https://github.com/Deguerre) for working
out the cipher. No denigma code was copied; the implementation here is this
project's.

Facts about a format are not themselves copyrightable, and no denigma code was
copied, so MIT's "include the copyright notice in all copies" condition is not
triggered here. This entry is therefore attribution, not a licence obligation,
and denigma's notice is deliberately **not** reproduced below: doing so would
mean transcribing a copyright line for a project whose exact holder and year we
have not verified, and a notices file is the wrong place to guess. Anyone
tracing the lineage should read the licence at the source repository.

## Documents vendored in `docs/`

Four out-of-print reference documents are committed to `docs/`: the ETF
specification, the 1996 Enigma Entry Pool document, the Cahill thesis, and the
LilyPond ETF notes. They are **not** covered by this project's MIT licence —
they are third-party works reproduced for research and scholarship, each cited
in `docs/REFERENCES.md` with author, original URL, and archive URL. See the
2026-07-24 entry in `docs/DECISIONS.md` for the owner's determination and the
commitment to comply promptly with any takedown request.

They are documentation, not part of the distributed package: no sdist or wheel
built from this project contains them.
