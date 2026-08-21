"""Write `docs/formats/finale-mus.hexpat`.

Run through `make hexpat`, never directly, so the output always lands in the
one place the currency test looks for it.
"""

from __future__ import annotations

from pathlib import Path

from .render import render_pattern

OUTPUT = Path("docs/formats/finale-mus.hexpat")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_pattern(), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
