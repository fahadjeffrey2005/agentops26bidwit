"""Part 7: the HTTP API (FastAPI). Thin: it validates input, starts/resumes workflow runs in the background,
and serves their state and output files. All logic lives in the parts and the workflow.

    uvicorn bidwit.api:app --host 127.0.0.1 --port 8000

  GET  /api/health                      AI on/off, which providers have a key (never the key), versions
  GET  /api/evidence                    the company evidence library (restricted text is never sent)
  POST /api/runs                        upload a tender PDF (form field 'file') or pick a sample ('sample')
  GET  /api/runs                        all runs, newest first (live ones and finished ones on disk)
  GET  /api/runs/{id}                   status, the gate waiting for a human, live audit trail, report
  POST /api/runs/{id}/gates/{gate}      the human's answer at gate A, no_go or B
  GET  /api/runs/{id}/files/{name}      report.json, compliance.csv, bid_draft.md, audit.jsonl
"""
from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from bidwit.core.config import load_settings
from bidwit.core.contracts import SCHEMA_VERSION, ClauseId
from bidwit.workflow import Runner, RunNotFound, RunNotWaiting
from bidwit.workflow.companies import companies as list_companies, find as find_company, profile as company_profile

from .security import Hardening

RUN_ID = re.compile(r"^run-\d{8}-\d{6}-[0-9a-f]{6}$")
OUTPUTS = {"report.json": "application/json", "compliance.csv": "text/csv", "bid_draft.md": "text/markdown",
           "audit.jsonl": "application/x-ndjson"}
DEFAULT_COMPANY = "northwind"
SAMPLES = {"tender_main": "tender_main.pdf", "tender_backup": "tender_backup.pdf"}
CHUNK = 1 << 20
MAX_ACTIVE = 3                                   # runs working at the same time (each may use the AI)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GateA(_In):
    reviewer: str = Field(min_length=1, max_length=60)
    not_requirements: list[ClauseId] = Field(default_factory=list, max_length=5000)
    pass_fail_add: list[ClauseId] = Field(default_factory=list, max_length=5000)
    pass_fail_remove: list[ClauseId] = Field(default_factory=list, max_length=5000)


class GateNoGo(_In):
    reviewer: str = Field(min_length=1, max_length=60)
    action: Literal["stop", "continue"]


class GateB(_In):
    reviewer: str = Field(min_length=1, max_length=60)
    decisions: dict[str, Literal["approve", "reject"]] = Field(default_factory=dict, max_length=10000)


GATES = {"A": GateA, "no_go": GateNoGo, "B": GateB}


def create_app(runner: Runner | None = None, workers: int = 2) -> FastAPI:
    settings = load_settings()
    runner = runner or Runner()
    runs_dir = runner.runs_dir
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bidwit-run")
    busy: dict[str, str] = {}                    # run_id -> what it is doing right now, before/between checkpoints
    busy_lock = threading.Lock()

    app = FastAPI(title="BidWit", version=SCHEMA_VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")
    origins = [o for o in os.environ.get("BIDWIT_UI_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-BidWit"])
    app.add_middleware(Hardening, max_upload_mb=settings.max_upload_mb)   # outermost: host, CSRF, size, headers

    def background(run_id: str, label: str, fn, *args) -> None:
        with busy_lock:
            if run_id in busy:
                raise HTTPException(409, f"{run_id} is busy: {busy[run_id]}")
            if len(busy) >= MAX_ACTIVE:
                raise HTTPException(429, f"{MAX_ACTIVE} runs are already working; try again when one pauses or finishes")
            busy[run_id] = label

        def job():
            try:
                fn(*args)
            except (RunNotWaiting, RunNotFound):
                pass                                      # the state endpoint shows the real status
            finally:
                with busy_lock:
                    busy.pop(run_id, None)
        pool.submit(job)

    def check_id(run_id: str) -> str:
        if not RUN_ID.match(run_id):
            raise HTTPException(404, "no such run")
        return run_id

    def from_disk(run_id: str) -> dict | None:
        p = runs_dir / run_id / "report.json"
        if not p.is_file():
            return None
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return {"run_id": run_id, "status": "done", "gate": None, "stopped": rep.get("stopped", ""), "report": rep,
                "audit": [], "errors": rep.get("errors", []), "failure": "", "archived": True}

    def state(run_id: str) -> dict:
        with busy_lock:
            doing = busy.get(run_id)
        try:
            v = runner.view(run_id)
        except RunNotFound:
            v = None
        if v is None:
            if doing:
                trail = runner.progress(run_id)
                if trail:
                    doing = f"{trail[-1]['part']}: {trail[-1]['message']}"
                return {"run_id": run_id, "status": "running", "doing": doing, "gate": None, "audit": [], "errors": [],
                        "progress": list(trail)}
            disk = from_disk(run_id)
            if disk is None:
                raise HTTPException(404, "no such run")
            return disk
        if doing and v["status"] != "failed":
            v = {**v, "status": "running", "gate": None}
            if v.get("progress"):
                last = v["progress"][-1]
                doing = f"{last['part']}: {last['message']}"
        v.pop("out_dir", None)
        return {**v, "doing": doing or ""}

    @app.get("/api/health")
    def health():
        st = load_settings()
        return {"ok": True, "version": SCHEMA_VERSION, "llm": st.llm, "chain": st.llm_chain.split(","),
                "keys": {"groq": bool(os.environ.get("GROQ_API_KEY")), "gemini": bool(os.environ.get("GEMINI_API_KEY"))},
                "max_upload_mb": st.max_upload_mb, "ai_budget": st.llm_max_calls}

    @app.get("/api/companies")
    def companies():
        return [{k: c.get(k) for k in ("id", "name", "city", "founded", "blurb", "facts")} for c in list_companies(settings.data_dir)]

    @app.get("/api/companies/{company}")
    def company(company: str):
        prof = company_profile(settings.data_dir, company, date.today())
        if prof is None:
            raise HTTPException(404, "no such company")
        return prof

    @app.get("/api/evidence")
    def evidence(company: str = DEFAULT_COMPANY):
        from bidwit.workflow.companies import evidence_file
        try:
            rows = json.loads(Path(evidence_file(settings.data_dir, company)).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise HTTPException(503, f"evidence library unreadable: {type(e).__name__}")
        today = date.today().isoformat()
        out = []
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            restricted = r.get("confidentiality") == "restricted"
            expired = bool(r.get("expires_on")) and str(r.get("expires_on")) < today
            out.append({k: r.get(k) for k in ("id", "title", "client", "confidentiality", "date", "expires_on")}
                       | {"text": None if restricted else r.get("text"), "usable": not restricted and not expired,
                          "blocked_reason": "restricted" if restricted else ("expired" if expired else "")})
        return out

    @app.post("/api/runs", status_code=202)
    def create_run(file: UploadFile | None = File(default=None), sample: str | None = Form(default=None),
                   company: str = Form(default=DEFAULT_COMPANY)):
        if (file is None) == (sample is None):
            raise HTTPException(422, "send exactly one of: a PDF file, or a sample name")
        if sample is not None and sample not in SAMPLES:
            raise HTTPException(422, f"unknown sample; choose one of {sorted(SAMPLES)}")
        if find_company(settings.data_dir, company) is None:
            raise HTTPException(422, "unknown company")
        with busy_lock:
            if len(busy) >= MAX_ACTIVE:              # checked before anything is written to disk
                raise HTTPException(429, f"{MAX_ACTIVE} runs are already working; try again when one pauses or finishes")
        run_id = runner.new_run_id()
        folder = runs_dir / run_id
        folder.mkdir(parents=True, exist_ok=False)
        if sample is not None:
            path = settings.data_dir / "tenders" / SAMPLES[sample]
        else:
            path = folder / "tender.pdf"
            limit = settings.max_upload_mb * CHUNK
            size, head, problem = 0, b"", None
            with path.open("wb") as f:
                while chunk := file.file.read(CHUNK):
                    size += len(chunk)
                    if size > limit:
                        problem = (413, f"file is larger than {settings.max_upload_mb} MB")
                        break
                    head = head or chunk[:5]
                    f.write(chunk)
            if problem is None and head != b"%PDF-":
                problem = (415, "not a PDF file")
            if problem:
                path.unlink(missing_ok=True)
                folder.rmdir()
                raise HTTPException(*problem)
        background(run_id, "reading the tender", runner.start, path, run_id, None, company)
        return {"run_id": run_id, "status": "running"}

    @app.get("/api/runs")
    def list_runs():
        ids = {p.name for p in runs_dir.iterdir() if p.is_dir() and RUN_ID.match(p.name)} if runs_dir.is_dir() else set()
        out = []
        for run_id in sorted(ids, reverse=True):          # ids start with a UTC timestamp: newest first
            try:
                v = state(run_id)
            except HTTPException:
                continue
            rep = v.get("report") or {}
            out.append({"run_id": run_id, "status": v["status"], "gate": (v.get("gate") or {}).get("gate"),
                        "tender": (rep.get("tender") or {}).get("file"),
                        "decision": (rep.get("verdict") or {}).get("decision"), "stopped": v.get("stopped", "")})
        return out

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return state(check_id(run_id))

    @app.post("/api/runs/{run_id}/gates/{gate}", status_code=202)
    def answer_gate(run_id: str, gate: Literal["A", "no_go", "B"], body: dict):
        v = state(check_id(run_id))
        if v["status"] != "waiting" or not v.get("gate"):
            raise HTTPException(409, f"run is {v['status']}, not waiting at a gate")
        if v["gate"]["gate"] != gate:
            raise HTTPException(409, f"run is waiting at gate {v['gate']['gate']}, not {gate}")
        try:
            answer = GATES[gate].model_validate(body)
        except ValueError as e:
            raise HTTPException(422, str(e)[:500])
        background(run_id, f"continuing after gate {gate}", runner.resume, run_id, answer.model_dump())
        return {"run_id": run_id, "status": "running"}

    @app.get("/api/runs/{run_id}/files/{name}")
    def get_file(run_id: str, name: str):
        check_id(run_id)
        if name not in OUTPUTS:
            raise HTTPException(404, "no such file")
        p = runs_dir / run_id / name
        if not p.is_file():
            raise HTTPException(404, "not written yet")
        return FileResponse(p, media_type=OUTPUTS[name], filename=f"{run_id}-{name}")

    app.state.runner = runner
    app.state.pool = pool
    return app


def __getattr__(name: str):
    """`bidwit.api:app` is built on first use, so importing this module never starts anything."""
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
