"""Generator for the Finale file format specification.

Run `make spec` (or `python -m scripts.format_spec`) to regenerate
`docs/formats/finale-formats.html`, then render it to PDF with headless Chrome.

The point of generating rather than hand-writing: every offset, size and
constant is imported from the parser, so a layout in the specification cannot
silently drift from the code that reads it.
"""
