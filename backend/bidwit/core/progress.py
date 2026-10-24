"""Live progress: parts call step() at each checkpoint; whoever is running them decides where it goes.

    step("classify", "batch 3/27")

- Always written to the 'bidwit' logger (scripts print it; see use_console()).
- If a sink is set for the current run (the workflow sets one per run), it receives (part, message) too.
A broken sink is ignored: progress reporting can never break a part.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Callable

log = logging.getLogger("bidwit")
_sink: ContextVar[Callable[[str, str], None] | None] = ContextVar("bidwit_progress_sink", default=None)


def step(part: str, message: str) -> None:
    message = " ".join(str(message).split())[:300]
    log.info("[%s] %s", part, message)
    sink = _sink.get()
    if sink is not None:
        try:
            sink(part, message)
        except Exception:  # noqa: BLE001 - progress must never break the work
            pass


def set_sink(sink: Callable[[str, str], None] | None):
    """Returns a token for reset_sink()."""
    return _sink.set(sink)


def reset_sink(token) -> None:
    _sink.reset(token)


def use_console() -> None:
    """For scripts: print every checkpoint with a timestamp."""
    if not any(getattr(h, "_bidwit", False) for h in log.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        h._bidwit = True
        log.addHandler(h)
    log.setLevel(logging.INFO)
