"""Build committed test fixtures from the local corpus.

Run manually when the corpus changes:  uv run python scripts/build_version_fixtures.py

Only format metadata is emitted. .mus fixtures are header prefixes; .musx
fixtures are rebuilt archives without score.dat or presets. No musical content
is ever written.
"""

from __future__ import annotations

import copy
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import cast

from defusedxml.ElementTree import fromstring as defused_fromstring

from finale_file_parser import MusDetail, NotFinaleFileError, detect_version
from finale_file_parser.version.family import HEADER_SIZE
from finale_file_parser.version.models import MusStamp
from finale_file_parser.version.mus import MUS_METADATA_SIZE

CORPUS = Path("corpus")
OUT = Path("tests/fixtures/version")
ALLOWED_MUSX_MEMBERS = {"mimetype", "NotationMetadata.xml"}

# Keep-allowlist: only these fileInfo children are known to be read by version
# detection. Anything else -- title, subtitle, composer, arranger, lyricist,
# copyright, description, and any future field not on this list -- is absent
# from the rebuilt output by construction, not by removal.
ALLOWED_FILE_INFO_CHILDREN = ("created", "modified")


def _local_name(tag: str) -> str:
    """Strip a Clark-notation `{namespace}local` tag down to `local`."""
    return tag.rsplit("}", 1)[-1]


def _namespace_of(tag: str) -> str:
    """Return the namespace URI of a Clark-notation tag, or "" if it has none."""
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _blank_modified_by(subtree: ET.Element) -> None:
    """Blank (not drop) every <modifiedBy> element's text anywhere in `subtree`."""
    for element in subtree.iter():
        if _local_name(element.tag) == "modifiedBy" and element.text:
            element.text = ""


def _strip_attributes(subtree: ET.Element) -> None:
    """Remove every XML attribute from `subtree` and all of its descendants.

    Version detection reads only element text, never attributes, and no
    attribute on <created>/<modified> is known to be needed, so none are
    allowlisted. Without this, an attribute such as `<created author="...">`
    would ride along in a deep-copied subtree unexamined and reach a
    committed fixture untouched by the child-name allowlist above (which
    only governs which child *elements* are copied).
    """
    for element in subtree.iter():
        element.attrib.clear()


def _scrub_notation_metadata(raw: bytes, source: str) -> bytes:
    """Rebuild NotationMetadata.xml containing only what version detection reads.

    The output tree is constructed fresh, not pruned from the input, so
    anything not explicitly named here is absent by construction: a new root
    <metadata> element carrying only the input's namespace and its `version`
    attribute, a <fileInfo> child, and within it only the complete <created>
    and <modified> subtrees (with every <modifiedBy> blanked and every
    attribute, on every element in those subtrees, stripped). Root-level
    siblings of <fileInfo>, other root attributes, title, subtitle, composer,
    arranger, lyricist, copyright, description, and any future field never
    make it into the new tree.

    fileInfo/created/modified are matched by local element name only, so a
    future namespace change cannot silently no-op this scrub. Whatever
    namespace the input declares is preserved on the output.

    Raises:
        SystemExit: the root element is not <metadata>, or no <fileInfo>
            child is found under it. Never falls back to emitting the raw
            input.
    """
    root = defused_fromstring(raw)
    if _local_name(root.tag) != "metadata":
        raise SystemExit(f"refusing to scrub {source}: root element is not <metadata>")

    file_info = next((child for child in root if _local_name(child.tag) == "fileInfo"), None)
    if file_info is None:
        raise SystemExit(f"refusing to scrub {source}: no <fileInfo> found under <metadata>")

    ns = _namespace_of(root.tag)
    if ns:
        ET.register_namespace("", ns)

    new_root = ET.Element(root.tag)
    version = root.get("version")
    if version is not None:
        new_root.set("version", version)

    new_file_info = ET.SubElement(new_root, file_info.tag)
    for child in file_info:
        if _local_name(child.tag) not in ALLOWED_FILE_INFO_CHILDREN:
            continue
        subtree = copy.deepcopy(child)
        _blank_modified_by(subtree)
        _strip_attributes(subtree)
        new_file_info.append(subtree)

    # `encoding="UTF-8"` (any str other than the literal "unicode") makes
    # ET.tostring return bytes at runtime, but typeshed's overload for a
    # non-literal `str` encoding can only declare the return type `Any` — it
    # has no way to further overload on this string's *value*. The cast
    # documents that guarantee instead of widening this function's own
    # return type or silencing the checker.
    return cast(bytes, ET.tostring(new_root, encoding="UTF-8", xml_declaration=True))


def _mus_fixtures() -> dict[str, Path]:
    """One .mus file per distinct banner year, plus the trailing-garbage case."""
    chosen: dict[str, Path] = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".mus":
            continue
        with path.open("rb") as handle:
            head = handle.read(HEADER_SIZE)
        if not head.startswith(b"ENIGMA BINARY FILE"):
            continue
        field = head[0x20:HEADER_SIZE]
        banner = field.split(b"\x00", 1)[0].decode("latin-1")
        year = banner.split()[1] if len(banner.split()) > 1 else "unknown"
        residue = field[len(banner) :].strip(b"\x00")
        key = f"mus-{year}-residue" if residue else f"mus-{year}"
        chosen.setdefault(key, path)
    return chosen


def _musx_fixtures() -> dict[str, Path]:
    """One .musx per distinct (modified major, platform) pair."""
    chosen: dict[str, Path] = {}
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".musx":
            continue
        try:
            detail = detect_version(path).detail
        except (FileNotFoundError, NotFinaleFileError):
            continue
        app = getattr(detail, "modified", None)
        platform = getattr(detail, "platform", None)
        key = f"musx-{app.major if app else 'none'}-{platform or 'none'}"
        chosen.setdefault(key, path)
    return chosen


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    entries: list[str] = []

    for name, src in sorted(_mus_fixtures().items()):
        target = OUT / f"{name}.bin"
        with src.open("rb") as handle:
            target.write_bytes(handle.read(MUS_METADATA_SIZE))
        entries.append(_entry(target, src, f"first {MUS_METADATA_SIZE} bytes"))

    for name, src in sorted(_musx_fixtures().items()):
        target = OUT / f"{name}.musx"
        with zipfile.ZipFile(src) as source, zipfile.ZipFile(target, "w") as out:
            for member in source.namelist():
                if member not in ALLOWED_MUSX_MEMBERS:
                    continue
                data = source.read(member)
                if member == "NotationMetadata.xml":
                    data = _scrub_notation_metadata(data, str(src))
                out.writestr(member, data)
        _assert_metadata_only(target)
        entries.append(_entry(target, src, "mimetype + scrubbed NotationMetadata.xml only"))

    (OUT / "MANIFEST.toml").write_text(
        "# Generated by scripts/build_version_fixtures.py — do not edit by hand.\n"
        "# Sources are local corpus files, which are NOT committed.\n\n" + "\n".join(entries)
    )
    print(f"wrote {len(entries)} fixtures to {OUT}")


def _assert_metadata_only(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        extra = set(archive.namelist()) - ALLOWED_MUSX_MEMBERS
    if extra:
        raise SystemExit(f"refusing to emit {archive_path}: unexpected members {sorted(extra)}")


def _entry(target: Path, source: Path, taken: str) -> str:
    result = detect_version(target)
    text = (
        "[[fixture]]\n"
        f'file = "{target.name}"\n'
        f'source = "{source.relative_to(CORPUS)}"\n'
        f'bytes = "{taken}"\n'
        f'expected_family = "{result.family.value}"\n'
        f'expected_label = "{result.label}"\n'
        f'expected_confidence = "{result.confidence.value}"\n'
    )
    if isinstance(result.detail, MusDetail):
        if result.detail.created is not None:
            text += f"created = {_stamp_toml(result.detail.created)}\n"
        if result.detail.modified is not None:
            text += f"modified = {_stamp_toml(result.detail.modified)}\n"
    return text


def _stamp_toml(stamp: MusStamp) -> str:
    return (
        "{ "
        f"year = {stamp.year}, month = {stamp.month}, day = {stamp.day}, "
        f'application = "{stamp.application}", platform = "{stamp.platform}"'
        " }"
    )


if __name__ == "__main__":
    main()
