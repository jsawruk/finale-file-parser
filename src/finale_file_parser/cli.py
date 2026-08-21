"""Command line entry point: `finale-parser`.

Everything this exposes already existed as a library; what did not exist was a
way to reach it without writing Python. The audience for this project --
migrating, analysing or archiving scores that only exist as Finale files -- is
not necessarily a Python audience.

    finale-parser convert score.mus -o score.musicxml
    finale-parser convert ./scores -o ./out
    finale-parser inspect score.mus

Two rules shape the behaviour, and both come from the archival use case:

**A batch does not abort on one bad file.** Someone converting a folder of 300
scores needs the 292 that work; the 8 that do not are reported and skipped, and
the exit status says so. Stopping at the first failure would make the tool
useless on exactly the collections it exists for.

**Nothing is overwritten without being asked.** An output path that already
exists is refused unless `--force`. Conversion is cheap to repeat and a
clobbered file is not.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from finale_file_parser.enigma.mus_payload import read_mus_pools
from finale_file_parser.enigma.pool_file import era_of, identify_pools, write_pool_file
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.export.pdf import to_pdf
from finale_file_parser.ir import Score
from finale_file_parser.reader import read_score
from finale_file_parser.report import inspect_document
from finale_file_parser.report.html import render_html
from finale_file_parser.version.detect import detect_version

__all__ = ["main"]

PROGRAM = "finale-parser"

_MUS = ".mus"
_MUSX = ".musx"
_OUTPUT_SUFFIX = ".musicxml"
_POOLS_SUFFIX = ".bin"
"""Appended to the source's **own** extension, so `score.mus` becomes
`score.mus.bin`.

Appended rather than substituted so the Windows cohort keeps its case:
`SCORE.MUS` becomes `SCORE.MUS.bin`, where a fixed `.mus.bin` would have
lowercased it. 101 of the 238 legacy corpus documents are spelled `.MUS`.

The name says where the bytes came from, and `.bin` keeps it plainly binary."""

FORMATS = {"musicxml": ".musicxml", "pdf": ".pdf"}
"""What `--format` accepts, and the suffix each writes.

Keyed here rather than branched at the call site so the argument's choices, the
output suffix and the writer cannot drift out of step."""

EXIT_OK = 0
EXIT_FAILURES = 1
"""Some input could not be converted. The rest still were."""
EXIT_USAGE = 2
"""The command itself was wrong -- no such path."""


def source_paths(root: Path) -> list[Path]:
    """Every Finale file at `root`, which may be one file or a directory.

    Suffixes are matched **case insensitively**. `rglob("*.mus")` is case
    sensitive on a POSIX path and would silently skip every `.MUS` file -- the
    Windows spelling, and 101 of the 238 in this project's own corpus. A
    conversion tool that quietly ignored half an archive would be worse than one
    that refused to run.
    """
    if root.is_file():
        return [root]
    return sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {_MUS, _MUSX}
    )


def output_path(
    source: Path, root: Path, destination: Path | None, suffix: str = _OUTPUT_SUFFIX
) -> Path:
    """Where `source`'s output goes, whatever `suffix` names.

    Shared by every verb that writes a file per input -- `convert`, which
    writes MusicXML or PDF, and `extract`, which writes decompressed pools --
    so the wording is deliberately not "converted": the rule about *where* a
    file lands is the same one regardless of what is in it.

    With no `-o`, it lands beside the input. With one, the input's position
    *relative to the root* is preserved, so converting a directory tree does not
    flatten it into a single folder -- an archive's layout is usually part of how
    it is catalogued.
    """
    if destination is None:
        return source.with_suffix(suffix)
    if root.is_file():
        # `-o` names the file itself, unless it is an existing directory.
        if destination.is_dir():
            return destination / source.with_suffix(suffix).name
        return destination
    return destination / source.relative_to(root).with_suffix(suffix)


def _reason(error: Exception) -> str:
    """One line, with no traceback and no absolute paths.

    The path is already on the line this is printed after, and a traceback tells
    a user who did not write this program nothing they can act on.
    """
    text = str(error).strip() or error.__class__.__name__
    return text.replace(os.sep, "/").split("/")[-1] if text.startswith("/") else text


def _clobber_reason(path: Path, force: bool) -> str | None:
    """Why `path` must not be written, or None if it may be.

    Shared so the two commands cannot drift: `convert` and `inspect --report`
    refuse for the same reason and must say so in the same words.
    """
    if path.exists() and not force:
        return f"{path.name} exists; pass --force to overwrite"
    return None


def _convert(args: argparse.Namespace, out: object) -> int:
    root: Path = args.input
    sources = source_paths(root)
    if not sources:
        print(f"{PROGRAM}: no .mus or .musx files under {root}", file=sys.stderr)
        return EXIT_USAGE

    converted = 0
    failures: list[tuple[Path, str]] = []
    for source in sources:
        target = output_path(source, root, args.output, FORMATS[args.format])
        reason = _clobber_reason(target, args.force)
        if reason:
            failures.append((source, reason))
            continue
        try:
            score = read_score(source)
            data = to_pdf(score) if args.format == "pdf" else to_musicxml(score)
        except FinaleFileError as error:
            failures.append((source, _reason(error)))
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as error:
            failures.append((source, _reason(error)))
            continue
        converted += 1
        if args.verbose:
            print(f"{source} -> {target}", file=out)  # type: ignore[call-overload]

    if len(sources) > 1 or failures:
        print(f"{converted}/{len(sources)} converted", file=out)  # type: ignore[call-overload]
    for source, reason in failures:
        print(f"  skipped {source}: {reason}", file=sys.stderr)
    return EXIT_FAILURES if failures else EXIT_OK


def _extract(args: argparse.Namespace, out: object) -> int:
    """Write each score's decompressed pools as one framed file."""
    root: Path = args.input
    sources = source_paths(root)
    if not sources:
        print(f"{PROGRAM}: no .mus or .musx files under {root}", file=sys.stderr)
        return EXIT_USAGE

    written = 0
    failures: list[tuple[Path, str]] = []
    for source in sources:
        if source.suffix.lower() == ".musx":
            failures.append((source, "a .musx has no compressed pools to extract"))
            continue
        target = output_path(source, root, args.output, source.suffix + _POOLS_SUFFIX)
        reason = _clobber_reason(target, args.force)
        if reason:
            failures.append((source, reason))
            continue
        try:
            raw = read_mus_pools(source)
            # `era_of` asks the container whether it labelled its pools, so it
            # has to see the pools as read. `identify_pools` labels every one of
            # them, and asking after that can only ever answer "DCL".
            era = era_of(raw)
            pools = identify_pools(raw)
            data = write_pool_file(pools, era=era)
        except (FinaleFileError, ValueError) as error:
            failures.append((source, _reason(error)))
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as error:
            failures.append((source, _reason(error)))
            continue
        written += 1
        if args.verbose:
            print(f"{source} -> {target}", file=out)  # type: ignore[call-overload]

    if len(sources) > 1 or failures:
        print(f"{written}/{len(sources)} extracted", file=out)  # type: ignore[call-overload]
    for source, reason in failures:
        print(f"  skipped {source}: {reason}", file=sys.stderr)
    return EXIT_FAILURES if failures else EXIT_OK


def _describe(score: Score) -> str:
    measures = sum(len(part.measures) for part in score.parts)
    events = sum(
        len(voice.events)
        for part in score.parts
        for measure in part.measures
        for voice in measure.voices
    )
    pitches = sum(
        len(event.pitches)
        for part in score.parts
        for measure in part.measures
        for voice in measure.voices
        for event in voice.events
    )
    return f"{len(score.parts)} parts, {measures} measures, {events} events, {pitches} pitches"


def _inspect(args: argparse.Namespace, out: object) -> int:
    sources = source_paths(args.input)
    if not sources:
        print(f"{PROGRAM}: no .mus or .musx files under {args.input}", file=sys.stderr)
        return EXIT_USAGE

    if args.report is not None:
        if len(sources) != 1:
            print(f"{PROGRAM}: --report takes one file, not a directory", file=sys.stderr)
            return EXIT_USAGE
        reason = _clobber_reason(args.report, args.force)
        if reason:
            print(f"{PROGRAM}: {reason}", file=sys.stderr)
            return EXIT_USAGE
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            # `errors` is a second line of defence only: `render_html` already
            # replaces every character UTF-8 or XML cannot carry (a filename is
            # allowed to hold raw bytes, and `os.fsdecode` turns an invalid one
            # into a lone surrogate). Without that, this would merely turn an
            # unwritable page into an unparseable one -- so it is here to keep a
            # future leak from reaching the user as a traceback, not as the fix.
            args.report.write_text(
                render_html(inspect_document(sources[0])),
                encoding="utf-8",
                errors="xmlcharrefreplace",
            )
        except OSError as error:
            print(
                f"{PROGRAM}: cannot write {args.report}: {_reason(error)}",
                file=sys.stderr,
            )
            return EXIT_USAGE
        print(f"{sources[0]} -> {args.report}", file=out)  # type: ignore[call-overload]
        return EXIT_OK

    failures = 0
    for source in sources:
        print(f"{source}", file=out)  # type: ignore[call-overload]
        try:
            version = detect_version(source)
            print(f"  version   {version.label} ({version.family.value})", file=out)  # type: ignore[call-overload]
        except FinaleFileError as error:
            print(f"  version   unreadable: {_reason(error)}", file=sys.stderr)
            failures += 1
            continue
        try:
            score = read_score(source)
        except FinaleFileError as error:
            print(f"  score     will not build: {_reason(error)}", file=sys.stderr)
            failures += 1
            continue
        print(f"  score     {_describe(score)}", file=out)  # type: ignore[call-overload]
    return EXIT_FAILURES if failures else EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Read Finale .mus and .musx files and convert them to MusicXML.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="write MusicXML for a file or a directory")
    convert.add_argument("input", type=Path, help="a .mus/.musx file, or a directory of them")
    convert.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output file, or directory for a batch; defaults to beside the input",
    )
    convert.add_argument(
        "--force", action="store_true", help="overwrite an output file that already exists"
    )
    convert.add_argument(
        "--format",
        choices=sorted(FORMATS),
        default="musicxml",
        help="what to write; pdf needs the 'pdf' extra (default: musicxml)",
    )
    convert.add_argument("-v", "--verbose", action="store_true", help="name each file converted")

    inspect = sub.add_parser("inspect", help="report what a file is and what was read from it")
    inspect.add_argument("input", type=Path, help="a .mus/.musx file, or a directory of them")
    inspect.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write a self-contained HTML report instead of terminal output",
    )
    inspect.add_argument("--force", action="store_true", help="overwrite an existing report")

    extract = sub.add_parser("extract", help="write a .mus file's decompressed pools as one binary")
    extract.add_argument("input", type=Path, help="a .mus file, or a directory of them")
    extract.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output file, or directory for a batch; defaults to beside the input",
    )
    extract.add_argument(
        "--force", action="store_true", help="overwrite an output file that already exists"
    )
    extract.add_argument("-v", "--verbose", action="store_true", help="name each file written")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns the process exit status rather than calling exit()."""
    args = _parser().parse_args(argv)
    out = sys.stdout
    if not args.input.exists():
        print(f"{PROGRAM}: no such file or directory: {args.input}", file=sys.stderr)
        return EXIT_USAGE
    if args.command == "convert":
        return _convert(args, out)
    if args.command == "extract":
        return _extract(args, out)
    return _inspect(args, out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
