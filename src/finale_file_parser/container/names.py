"""Member-name safety.

Reject names that are dangerous; allow names that are merely unfamiliar. A
future Finale release may add members we have never seen, and those must stay
inspectable rather than making the whole archive unreadable.
"""

from __future__ import annotations

_UNSAFE_CHARS = frozenset("\\")


def is_safe_name(name: str) -> bool:
    """Return True if `name` is safe to surface and to look up.

    Unsafe means: empty, absolute, containing a `..` path segment, containing a
    backslash, containing control characters, or carrying a drive-letter prefix.
    """
    if not name:
        return False
    if name.startswith("/"):
        return False
    if any(char in _UNSAFE_CHARS for char in name):
        return False
    if any(ord(char) < 0x20 for char in name):
        return False
    if len(name) > 1 and name[1] == ":":
        return False
    return ".." not in name.split("/")
