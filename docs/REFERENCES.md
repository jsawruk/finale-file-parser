# References

Sources consulted for this project. Each entry: what it is, where it came from, and its license
where known.

**On the vendored copies in `docs/`:** four out-of-print documents are committed to this repo.
They are no longer available through their original channels, are cited here with author, original
URL, and archive URL, and are reproduced for research and scholarship under fair use. The project
will comply promptly with any takedown request. See `docs/DECISIONS.md`.

**Scope of this file:** it indexes sources and judges their reliability. Conclusions we draw about
the format — offsets, record layouts, field meanings — belong in `docs/ARCHITECTURE.md`, citing the
entry here that supports them.

## Primary — official / from the vendor

**Enigma Transportable File Specification**

- Local copy: `docs/etfspec.pdf`
- Appears to be official Coda Music Technologies documentation.
- The Library of Congress identifies this as "Enigma Transportable File Specification, Version
  98c.0 (for Finale 97 for Mac and Windows)".
  https://www.loc.gov/preservation/digital/formats/fdd/fdd000633.shtml
- Vendored under fair use; see note above.

**Enigma Entry Pool documentation (1996)** — Coda Music Technologies

- Local copy: `docs/eeppd.txt`
- Archive: https://web.archive.org/web/19990203113959/http://www.codamusic.com:80/down/finale/eeppd.txt
- Vendored under fair use; see note above.

## Community reverse engineering

<!-- Note the license of anything with code. See DECISIONS.md — open question. -->

**denigma**

- https://github.com/chrisroode/denigma
- MIT License
- Source of the `score.dat` cipher parameters used in `enigma/crypt.py`: the fixed LCG seed, the
  `(upper + upper // 255)` output function, and the 128 KiB keystream reset. denigma's own source
  credits [Deguerre](https://github.com/Deguerre) for working out the cipher. See
  `docs/formats/score-dat.md` and the 2026-07-22 DECIDED entry in `docs/DECISIONS.md`.

**EnigmaXML documentation**

- https://github.com/Project-Attacca/enigmaxml-documentation
- Community reverse-engineering documentation for `.musx` files.
- MIT License

**musxdom**

- https://github.com/rpatters1/musxdom
- C++17 object model for the EnigmaXML (`.musx`) format.
- https://rpatters1.github.io/musxdom/
- MIT License

**zlib `contrib/blast`** — Mark Adler

- https://github.com/madler/zlib (`contrib/blast`)
- zlib License
- Source of the PKWARE DCL ("implode") format knowledge implemented in
  `enigma/blast.py`: the three fixed Huffman bit-length tables, the inverted canonical code
  assignment, and the length/distance encodings. The Python port and its safety limits are this
  project's; the format knowledge is Adler's. Correctness is pinned by that project's own documented
  test vector (`00 04 82 24 25 8f 80 7f` -> `AIAIAIAIAIAIA`); see `tests/enigma/test_blast.py`.
- Legacy `.mus` files from Finale 2001-2005 store their payload as a single DCL stream, and no stdlib
  module reads the format. See `docs/formats/mus-binary-notes.md`.

**musx2mxl**

- https://github.com/joris-vaneyghen/musx2mxl
- MIT License

**The Translation of Finale's Enigma File Format for CPNView** — Margaret Cahill, M.Sc. thesis

- Local copy: `docs/cahill-enigma-cpnview-thesis.pdf`
- Original URL: http://www.csis.ul.ie/staff/margaretcahill/Research/MSc/MSc.pdf
- Archive: https://web.archive.org/web/20041228062027/http://www.csis.ul.ie/staff/margaretcahill/Research/MSc/MSc.pdf
- Sustained academic treatment of **ETF, the plaintext transportable format** — despite the title,
  it does not document the legacy *binary* layout. Useful for record semantics, not byte offsets.
- Vendored under fair use; see note above.

**An incomplete description of the Enigma Transport Format** — LilyPond project

- Local copy: `docs/lilypond-etf-format.html`
- Original URL: http://www.lilypond.org/web/devel/misc/etfformat
- Archive: https://web.archive.org/web/20050525005327/http://www.lilypond.org/web/devel/misc/etfformat
- Self-described as incomplete — corroborate before relying on it.
- Vendored under fair use; see note above.

## Format registries — versioning and identification

**Finale Legacy Music Notation File (Library of Congress)**

- ETF: https://www.loc.gov/preservation/digital/formats/fdd/fdd000633.shtml
- MUS: https://www.loc.gov/preservation/digital/formats/fdd/fdd000632.shtml
- MUSX: https://www.loc.gov/preservation/digital/formats/fdd/fdd000631.shtml

**PRONOM (The National Archives, UK)**

- Enigma Binary File (Finale) 1:
  https://www.nationalarchives.gov.uk/PRONOM/Format/proFormatSearch.aspx?status=detailReport&id=2837
- Enigma Binary File (Finale) 2:
  https://www.nationalarchives.gov.uk/PRONOM/Format/proFormatSearch.aspx?status=detailReport&id=2839
- Enigma Binary File (Finale) 3+:
  https://www.nationalarchives.gov.uk/PRONOM/Format/proFormatSearch.aspx?status=detailReport&id=1145
- The three distinct signatures are the main external evidence for on-disk format variation across
  Finale releases.

**Obsolete Thor: Finale**

- https://preservation.tylerthorsted.com/2024/02/09/finale/
- Digital-preservation write-up on Finale's discontinuation.

## Output formats

**MusicXML** — our first export target

- Specification repository: https://github.com/w3c/musicxml
- Published specification: https://www.w3.org/2021/06/musicxml40/
- W3C Music Notation Community Group. Check the repository for current license terms before
  reusing any schema files.

**SMuFL (Standard Music Font Layout)** — relevant to notation rendering in the frontend

- Latest specification: https://w3c.github.io/smufl/latest/
- Specification repository: https://github.com/w3c/smufl
- W3C Music Notation Community Group.

## Tools

**Finale PDK Framework / Finale Lua**

- Lua plugin support for Finale — useful for extracting ground truth from files by scripting Finale
  itself, where a copy is available.
- https://finalelua.com/
- https://pdk.finalelua.com/
- https://github.com/finale-lua/lua-scripts
- CC0-1.0 License
