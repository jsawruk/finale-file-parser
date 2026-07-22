"""Member-name safety.

Reject names that are dangerous; allow names that are merely unfamiliar. A
future Finale release may add members we have never seen, and those must stay
inspectable rather than making the whole archive unreadable.
"""

from __future__ import annotations

import unicodedata

_UNSAFE_CHARS = frozenset("\\")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf"})


def is_safe_name(name: str) -> bool:
    """Return True if `name` is safe to surface and to look up.

    Unsafe means: empty, absolute, containing a `..` path segment, containing a
    backslash, containing control or format characters (Unicode categories
    Cc/Cf — including DEL, the C1 range, and bidi overrides such as U+202E),
    or containing a colon anywhere. There is no dedicated drive-letter check;
    a Windows drive-letter prefix such as `C:` is rejected as a side effect of
    the colon check, which also rejects a colon anywhere else in the name
    (e.g. an NTFS alternate-data-stream suffix).
    """
    if not name:
        return False
    if name.startswith("/"):
        return False
    if any(char in _UNSAFE_CHARS for char in name):
        return False
    if any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in name):
        return False
    if ":" in name:
        return False
    return ".." not in name.split("/")
