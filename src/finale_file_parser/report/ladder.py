"""Running a pipeline stage so that failure becomes data rather than an exception.

The tool exists for documents that do not work, so a stage that fails is the
normal path. Two failures are distinguished, because the difference is the most
useful thing a report can say:

**Refused** -- a `FinaleFileError`. The reader deliberately declined, and its
message already explains why.

**Crashed** -- anything else. That is a reader *bug* rather than a bad file, and
naming it as such is what makes this a bug-finder as well as a viewer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from finale_file_parser.errors import FinaleFileError

__all__ = ["CRASHED", "OK", "REFUSED", "SKIPPED", "Ladder", "Stage"]

OK = "ok"
REFUSED = "refused"
CRASHED = "crashed"
SKIPPED = "skipped"
"""Not attempted, because an earlier stage stopped the ladder."""

T = TypeVar("T")


@dataclass(frozen=True)
class Stage:
    """One rung: what was tried, how it went, and what it produced."""

    name: str
    status: str
    detail: dict[str, str] = field(default_factory=dict)
    error: str | None = None


class Ladder:
    """Runs stages in order and stops at the first failure.

    Stopping matters: a later stage given a value an earlier one never produced
    would either crash for the wrong reason or, worse, look like it passed.

    Not every rung fits that model, though: a report depth that is independent
    of the pipeline proper (e.g. a supplementary view built alongside it) can
    fail on its own without the rest of the pipeline having received a bad
    value. `halt=False` records exactly the same OK/REFUSED/CRASHED outcome
    for such a rung without stopping the ladder for the ones after it.
    """

    def __init__(self) -> None:
        self.stages: list[Stage] = []
        self._stopped = False

    def run(
        self,
        name: str,
        call: Callable[[], T],
        detail: Callable[[T], dict[str, str]] | None = None,
        *,
        halt: bool = True,
    ) -> T | None:
        if self._stopped:
            self.stages.append(Stage(name, SKIPPED))
            return None
        try:
            value = call()
        except FinaleFileError as error:
            self._stopped = halt
            self.stages.append(Stage(name, REFUSED, error=str(error)))
            return None
        except Exception as error:  # noqa: BLE001 - a reader bug is a finding, not a crash
            self._stopped = halt
            self.stages.append(Stage(name, CRASHED, error=f"{type(error).__name__}: {error}"))
            return None
        self.stages.append(Stage(name, OK, self._detail(detail, value)))
        return value

    @staticmethod
    def _detail(detail: Callable[[T], dict[str, str]] | None, value: T) -> dict[str, str]:
        """`detail` only formats an already-successful `call` -- it does not get
        a vote on pass or fail. A `detail` that raises (e.g. indexing an empty
        result) must not turn a working stage into a failed one or stop the
        ladder; it goes in the stage's own detail instead."""
        if detail is None:
            return {}
        try:
            return detail(value)
        except Exception as error:  # noqa: BLE001 - formatting is not the reader
            return {"detail unavailable": f"{type(error).__name__}: {error}"}
