"""Part 6: the workflow. Joins the parts with LangGraph and pauses at the human gates.

    runner = Runner()
    v = runner.start("tender.pdf")            # runs until Gate A, returns {"status": "waiting", "gate": {...}}
    v = runner.resume(v["run_id"], {...})     # human answer; runs to the next gate or to the end
    v["status"] == "done" -> v["report"]      # outputs are in runs/<run_id>/

The workflow may import parts; parts never import the workflow (checked by tests/core/test_boundaries.py).
"""
from __future__ import annotations

import secrets
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.types import Command

from bidwit.core.config import load_settings
from bidwit.core.progress import reset_sink, set_sink

from .graph import MAX_REWRITES, build_graph
from .package import build_report

RUN_ID = "run-{}-{}"
PROGRESS_KEEP = 200


class RunNotFound(KeyError):
    pass


class RunNotWaiting(RuntimeError):
    pass


class Runner:
    def __init__(self, checkpointer=None, runs_dir: Path | None = None):
        self.graph = build_graph(checkpointer)
        self.runs_dir = Path(runs_dir) if runs_dir else load_settings().runs_dir
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._failed: dict[str, str] = {}
        self._progress: dict[str, list[dict]] = {}       # run_id -> recent checkpoints, newest last                 # run_id -> why the graph itself broke (a bug, not a part)

    def _lock(self, run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(run_id, threading.Lock())

    @staticmethod
    def _cfg(run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    def new_run_id(self) -> str:
        return RUN_ID.format(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"), secrets.token_hex(3))

    def start(self, tender_path: str | Path, run_id: str | None = None, today: date | None = None) -> dict:
        run_id = run_id or self.new_run_id()
        with self._lock(run_id):
            if self.graph.get_state(self._cfg(run_id)).values:
                raise RunNotWaiting(f"{run_id} already exists")
            self._invoke(run_id, {"run_id": run_id, "tender_path": str(tender_path), "today": today or date.today(),
                                  "out_dir": str(self.runs_dir / run_id), "errors": [], "audit": []})
        return self.view(run_id)

    def resume(self, run_id: str, answer: dict[str, Any]) -> dict:
        with self._lock(run_id):
            v = self.view(run_id)
            if v["status"] != "waiting":
                raise RunNotWaiting(f"{run_id} is {v['status']}, not waiting at a gate")
            self._invoke(run_id, Command(resume={"answer": dict(answer or {})}))   # wrapped: {} is still an answer
        return self.view(run_id)

    def _invoke(self, run_id: str, inp: Any) -> None:
        trail = self._progress.setdefault(run_id, [])

        def sink(part: str, msg: str) -> None:
            trail.append({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "part": part, "message": msg})
            del trail[:-PROGRESS_KEEP]

        token = set_sink(sink)
        try:
            self.graph.invoke(inp, self._cfg(run_id))
            self._failed.pop(run_id, None)
        except Exception as e:                            # noqa: BLE001 - reported, the server keeps running
            self._failed[run_id] = f"{type(e).__name__}: {e}"[:500]
        finally:
            reset_sink(token)

    @staticmethod
    def _snapshot(s: dict) -> dict | None:
        """The report so far, while the run is paused or still going (same shape as the final report.json)."""
        try:
            return build_report(s)
        except Exception:                                 # noqa: BLE001 - a partial view must never break polling
            return None

    def progress(self, run_id: str) -> list[dict]:
        return list(self._progress.get(run_id, []))

    def view(self, run_id: str) -> dict:
        st = self.graph.get_state(self._cfg(run_id))
        if not st.values:
            raise RunNotFound(run_id)
        s = st.values
        waiting = [i.value for t in st.tasks for i in (t.interrupts or ())]
        status = "waiting" if waiting else ("done" if not st.next else ("failed" if run_id in self._failed else "running"))
        return {"run_id": run_id, "status": status, "failure": self._failed.get(run_id, ""), "gate": waiting[0] if waiting else None,
                "stopped": s.get("stopped") or "",
                "report": s.get("report") or (self._snapshot(s) if s.get("requirements") else None),
                "audit": [e.model_dump(mode="json") for e in s.get("audit") or []],
                "errors": [e.model_dump(mode="json") for e in s.get("errors") or []],
                "progress": list(self._progress.get(run_id, [])), "out_dir": s.get("out_dir")}


__all__ = ["Runner", "RunNotFound", "RunNotWaiting", "MAX_REWRITES", "build_graph"]
