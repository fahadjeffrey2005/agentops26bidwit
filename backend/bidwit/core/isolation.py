"""run_part: the single wrapper every part runs through.

A part that crashes, or returns something that is not the agreed output type,
produces a PartResult with ok=False instead of raising. The workflow then turns
that into a flagged item for a human. One failing part never kills the run.
"""
from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from pydantic import TypeAdapter, ValidationError

from .contracts import AuditEvent, PartError, PartResult, Rejected

I = TypeVar("I")
O = TypeVar("O")

MAX_MSG = 500


def _short(text: str) -> str:
    text = " ".join(str(text).split())             # one line, no traceback layout
    return text if len(text) <= MAX_MSG else text[: MAX_MSG - 3] + "..."


def run_part(part: str, fn: Callable[[I], Any], inp: I, output_type: type[O] | Any) -> tuple[PartResult[O], AuditEvent]:
    """Run one part safely. Returns (result, audit event). Never raises an Exception."""
    part = (str(part).strip() or "unknown")[:40]
    t0 = time.perf_counter()
    value: O | None = None
    error: PartError | None = None
    try:
        raw = fn(inp)
    except Rejected as e:                          # the part refused its input on purpose
        error = PartError(kind="rejected", type="Rejected", message=_short(e) or "rejected")
    except ValidationError as e:                   # the part rejected its input
        error = PartError(kind="bad_input", type="ValidationError", message=_short(f"{e.error_count()} validation error(s): {e.errors()[0]['msg']}"))
    except Exception as e:                         # noqa: BLE001 - containment is the point
        error = PartError(kind="crash", type=type(e).__name__[:120], message=_short(e))
    else:
        try:
            value = TypeAdapter(output_type).validate_python(raw, strict=True)
        except ValidationError as e:
            error = PartError(kind="bad_output", type="ValidationError", message=_short(f"{e.error_count()} validation error(s): {e.errors()[0]['msg']}"))
    secs = round(time.perf_counter() - t0, 4)
    ok = error is None
    result: PartResult[O] = PartResult[output_type](part=part, ok=ok, value=value, error=error, seconds=secs)  # type: ignore[valid-type]
    event = AuditEvent(
        part=part,
        level="info" if ok else "error",
        event="ok" if ok else _short(f"{error.kind}: {error.type}: {error.message}"),  # type: ignore[union-attr]
        data={"seconds": secs},
    )
    return result, event
