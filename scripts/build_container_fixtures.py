"""Build synthetic .musx container fixtures from the local corpus.

Run manually when the corpus changes:
    uv run python scripts/build_container_fixtures.py

Only STRUCTURE is harvested — member names, their order, compression method,
and declared uncompressed lengths. Every payload is regenerated as a repeating
pattern, so declared sizes stay realistic while the committed archives stay
small. No payload byte from the corpus is ever written.

Profiles are keyed on ordered member NAMES only, not on (name, size, method).
`score.dat`'s declared length differs per musical work, so keying on the full
per-member tuple makes nearly every corpus archive its own "shape" (measured:
329 groups on this corpus). The survey's "22 distinct shapes" was measured by
ordered member names alone. Within each name-shape group this script takes,
independently per member position, the MODAL declared size and the MODAL
compression method across every archive that shares the shape (via
`statistics.mode`). Where a group has only one archive, its values are simply
that archive's. Where the compression method disagreed across a group's
archives at some member position, the emitted profile carries
`method_varied = true` so that fact is not silently lost.
"""

from __future__ import annotations

import re
import shutil
import statistics
import zipfile
from dataclasses import dataclass
from pathlib import Path

from finale_file_parser.container.musx import MIMETYPE_NAME, MIMETYPE_VALUE

_REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = _REPO_ROOT / "corpus"
OUT = _REPO_ROOT / "tests/fixtures/container"

ALLOWED_NAME = re.compile(
    r"^(mimetype"
    r"|META-INF/container\.xml"
    r"|NotationMetadata\.xml"
    r"|score\.dat"
    r"|presets/\d+\.preset"
    r"|graphics/\d+\.jpg)$"
)
"""Strict allowlist for HARVESTING. The reader is deliberately more permissive;
here we control what gets committed, so anything unrecognised is a hard stop."""

FILLER = b"FINALE-FIXTURE-SYNTHETIC-PAYLOAD-DO-NOT-INTERPRET-"


def _payload(name: str, size: int) -> bytes:
    """Deterministic payload of exactly `size` bytes for member `name`.

    The `mimetype` member is special-cased to carry the real
    `MIMETYPE_VALUE` bytes: that value is a fixed protocol constant already
    present verbatim in our own reader source (`container/musx.py`), never
    read out of a corpus archive here, so writing it is not "a payload byte
    from the corpus" in the sense this generator forbids. It is also required
    for the fixtures to be openable at all: `open_musx` rejects any archive
    whose `mimetype` member does not equal this value. Every corpus archive's
    `mimetype` member is exactly `len(MIMETYPE_VALUE)` bytes, so no padding or
    truncation is needed in practice; the branch below still guards against a
    future corpus outlier.

    Every other member gets highly compressible synthetic filler.
    """
    if name == MIMETYPE_NAME:
        if size == len(MIMETYPE_VALUE):
            return MIMETYPE_VALUE
        return (MIMETYPE_VALUE * (size // len(MIMETYPE_VALUE) + 1))[:size]
    if size == 0:
        return b""
    repeats = size // len(FILLER) + 1
    return (FILLER * repeats)[:size]


NameShape = tuple[str, ...]
"""One archive's ordered member names — the grouping key for a profile."""

ArchiveRecord = tuple[tuple[int, ...], tuple[int, ...]]
"""One archive's (declared sizes, compression methods), aligned position-for-
position with some NameShape."""


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    compress_type: int


@dataclass(frozen=True)
class Profile:
    names: NameShape
    members: tuple[Member, ...]
    source_count: int
    method_varied: bool


def _harvest() -> dict[NameShape, list[ArchiveRecord]]:
    """Group corpus archives by ordered member NAMES only.

    Fails loudly (SystemExit) if any archive carries a member name outside
    ALLOWED_NAME — a member named after a piece must not ride along.
    """
    groups: dict[NameShape, list[ArchiveRecord]] = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".musx":
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
        except zipfile.BadZipFile:
            continue
        for info in infos:
            if not ALLOWED_NAME.fullmatch(info.filename):
                raise SystemExit(
                    f"refusing to harvest {path.name}: unrecognised member name "
                    f"{info.filename!r}. Widen ALLOWED_NAME only after confirming "
                    f"the name carries no title, composer, or personal data."
                )
        names = tuple(info.filename for info in infos)
        sizes = tuple(info.file_size for info in infos)
        methods = tuple(info.compress_type for info in infos)
        groups.setdefault(names, []).append((sizes, methods))
    return groups


def _profiles() -> list[Profile]:
    """Reduce each name-shape group to one profile: modal size and modal
    compression method per member position, plus whether method disagreed.

    When a group's declared sizes (or methods) at a position are all
    distinct, there is no true mode; `statistics.mode` then returns the
    first-encountered value. That's deterministic given `_harvest`'s stable
    ordering, but it is a tie-break, not evidence of a genuine consensus
    value.
    """
    profiles: list[Profile] = []
    for names, records in sorted(_harvest().items()):
        members: list[Member] = []
        method_varied = False
        for position in range(len(names)):
            sizes_here = [sizes[position] for sizes, _methods in records]
            methods_here = [methods[position] for _sizes, methods in records]
            # Named `_pick`, not `_mode`: statistics.mode() degenerates to a
            # first-seen tie-break, not a genuine consensus value, whenever
            # every value at this position is distinct (see this function's
            # docstring below) -- a name claiming "mode" would overstate that.
            size_pick = statistics.mode(sizes_here)
            method_pick = statistics.mode(methods_here)
            if len(set(methods_here)) > 1:
                method_varied = True
            members.append(Member(names[position], size_pick, method_pick))
        profiles.append(
            Profile(
                names=names,
                members=tuple(members),
                source_count=len(records),
                method_varied=method_varied,
            )
        )
    return profiles


def main() -> None:
    # Harvest (and let any allowlist refusal raise) before touching OUT, so a
    # mid-run SystemExit can't leave the 22 committed fixtures deleted.
    profiles = _profiles()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    entries: list[str] = []
    for index, profile in enumerate(profiles, start=1):
        name = f"variant-{index:02d}.musx"
        target = OUT / name
        with zipfile.ZipFile(target, "w") as archive:
            for member in profile.members:
                info = zipfile.ZipInfo(member.name)
                info.compress_type = member.compress_type
                archive.writestr(info, _payload(member.name, member.size))
        _assert_structure_matches(target, profile.members)

        member_lines = "\n".join(
            f'  {{ name = "{m.name}", size = {m.size}, compress_type = {m.compress_type} }},'
            for m in profile.members
        )
        method_varied_line = "method_varied = true\n" if profile.method_varied else ""
        entries.append(
            "[[profile]]\n"
            f'file = "{name}"\n'
            f"source_count = {profile.source_count}\n"
            f"{method_varied_line}"
            f"members = [\n{member_lines}\n]\n"
        )

    (OUT / "PROFILES.toml").write_text(
        "# Generated by scripts/build_container_fixtures.py — do not edit by hand.\n"
        "# Structure harvested from the local corpus; ALL payloads are synthetic.\n"
        "#\n"
        "# Profiles are keyed on ordered member names only. Within a profile, `size`\n"
        "# and `compress_type` per member are the MODAL values observed across every\n"
        "# corpus archive sharing that name-shape (see module docstring). A profile\n"
        "# carrying `method_varied = true` means at least one member position saw more\n"
        "# than one distinct compression method across the group's real archives; the\n"
        "# declared `compress_type` there is still the modal one, not the only one.\n\n"
        + "\n".join(entries)
    )
    print(f"wrote {len(entries)} container fixtures to {OUT}")


def _assert_structure_matches(path: Path, members: tuple[Member, ...]) -> None:
    with zipfile.ZipFile(path) as archive:
        actual = tuple((i.filename, i.file_size, i.compress_type) for i in archive.infolist())
    expected = tuple((m.name, m.size, m.compress_type) for m in members)
    if actual != expected:
        raise SystemExit(f"generated {path} does not match its harvested profile")


if __name__ == "__main__":
    main()
