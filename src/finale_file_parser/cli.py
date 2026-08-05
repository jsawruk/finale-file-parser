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

from finale_file_parser.enigma.document import EnigmaDocument, parse_enigma
from finale_file_parser.enigma.mus_document import read_mus_document
from finale_file_parser.enigma.score import score_xml
from finale_file_parser.enigma.to_ir import build_score
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.export.musicxml import to_musicxml
from finale_file_parser.ir import Score
from finale_file_parser.report import inspect_document
from finale_file_parser.report.html import render_html
from finale_file_parser.version.detect import detect_version

__all__ = ["main"]

PROGRAM = "finale-parser"

_MUS = ".mus"
_MUSX = ".musx"
_OUTPUT_SUFFIX = ".musicxml"

EXIT_OK = 0
EXIT_FAILURES = 1
"""Some input could not be converted. The rest still were."""
EXIT_USAGE = 2
"""The command itself was wrong -- no such path, output would be clobbered."""


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


def load_document(path: Path) -> EnigmaDocument:
    """Read either container into the shared document model."""
    if path.suffix.lower() == _MUSX:
        return parse_enigma(score_xml(path))
    return read_mus_document(path)


def output_path(source: Path, root: Path, destination: Path | None) -> Path:
    """Where `source`'s MusicXML goes.

    With no `-o`, it lands beside the input. With one, the input's position
    *relative to the root* is preserved, so converting a directory tree does not
    flatten it into a single folder -- an archive's layout is usually part of how
    it is catalogued.
    """
    if destination is None:
        return source.with_suffix(_OUTPUT_SUFFIX)
    if root.is_file():
        # `-o` names the file itself, unless it is an existing directory.
        if destination.is_dir():
            return destination / source.with_suffix(_OUTPUT_SUFFIX).name
        return destination
    return destination / source.relative_to(root).with_suffix(_OUTPUT_SUFFIX)


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
        target = output_path(source, root, args.output)
        reason = _clobber_reason(target, args.force)
        if reason:
            failures.append((source, reason))
            continue
        try:
            score = build_score(load_document(source))
            data = to_musicxml(score)
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
            args.report.write_text(render_html(inspect_document(sources[0])), encoding="utf-8")
        except OSError as error:
            print(
                f"{PROGRAM}: cannot write {args.report.name}: {_reason(error)}",
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
            score = build_score(load_document(source))
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
    return _inspect(args, out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
