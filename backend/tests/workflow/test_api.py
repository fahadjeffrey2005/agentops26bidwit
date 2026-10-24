"""Part 7: the HTTP API, driven like the UI drives it: upload, poll, answer gates, download outputs."""
import time

import pytest
from fastapi.testclient import TestClient

from bidwit.api import create_app
from bidwit.workflow import Runner

from .test_workflow import runner  # noqa: F401  (fixture: synthetic tender, fake Groq, no network)


@pytest.fixture
def api(runner):  # noqa: F811
    app = create_app(runner)
    with TestClient(app) as c:
        yield c
    app.state.pool.shutdown(wait=True)


def wait(api, run_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = api.get(f"/api/runs/{run_id}").json()
        if v["status"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("run did not settle")


def test_health_never_shows_keys(api):
    h = api.get("/api/health").json()
    assert h["ok"] and h["keys"] == {"groq": True, "gemini": False} and "k" not in str(h["chain"])


def test_evidence_hides_restricted_text_and_marks_expired(api):
    ev = {e["id"]: e for e in api.get("/api/evidence").json()}
    assert ev["E-010"]["text"] is None and ev["E-010"]["blocked_reason"] == "restricted"
    assert ev["E-005"]["blocked_reason"] == "expired" and ev["E-001"]["usable"]


def test_full_run_over_http(api):
    r = api.post("/api/runs", files={"file": ("my tender.pdf", b"%PDF-1.7 fake", "application/pdf")})
    assert r.status_code == 202
    rid = r.json()["run_id"]
    v = wait(api, rid)
    assert v["status"] == "waiting" and v["gate"]["gate"] == "A" and v["audit"]
    assert api.post(f"/api/runs/{rid}/gates/B", json={"reviewer": "x"}).status_code == 409     # wrong gate
    assert api.post(f"/api/runs/{rid}/gates/A", json={"reviewer": "x", "evil": 1}).status_code == 422
    assert api.post(f"/api/runs/{rid}/gates/A", json={"reviewer": "Fahad"}).status_code == 202
    v = wait(api, rid)
    assert v["gate"]["gate"] == "B"
    decisions = {x["id"]: "approve" for x in v["gate"]["queue"]}
    assert api.post(f"/api/runs/{rid}/gates/B", json={"reviewer": "Fahad", "decisions": decisions}).status_code == 202
    v = wait(api, rid)
    assert v["status"] == "done" and v["report"]["silent_misses_count"] == 0
    assert api.post(f"/api/runs/{rid}/gates/B", json={"reviewer": "x"}).status_code == 409     # already done
    f = api.get(f"/api/runs/{rid}/files/compliance.csv")
    assert f.status_code == 200 and f.text.startswith("requirement_id,")
    assert api.get(f"/api/runs/{rid}/files/..%2F..%2Fsecret").status_code == 404
    assert [x["run_id"] for x in api.get("/api/runs").json()] == [rid]


def test_sample_run_and_finished_runs_survive_a_restart(api, runner):  # noqa: F811
    rid = api.post("/api/runs", data={"sample": "tender_main"}).json()["run_id"]
    v = wait(api, rid)
    api.post(f"/api/runs/{rid}/gates/A", json={"reviewer": "x"})
    api.post(f"/api/runs/{rid}/gates/B", json={"reviewer": "x", "decisions": {}}) if wait(api, rid)["gate"]["gate"] == "B" else None
    assert wait(api, rid)["status"] == "done"
    fresh = create_app(Runner(runs_dir=runner.runs_dir))                # new server process: memory is empty
    with TestClient(fresh) as c:
        v = c.get(f"/api/runs/{rid}").json()
        assert v["status"] == "done" and v.get("archived") and v["report"]["run_id"] == rid
    fresh.state.pool.shutdown(wait=True)


def test_bad_uploads_are_refused_and_leave_nothing_behind(api, runner, monkeypatch):  # noqa: F811
    assert api.post("/api/runs", files={"file": ("x.pdf", b"MZ\x90 not a pdf", "application/pdf")}).status_code == 415
    assert api.post("/api/runs", data={"sample": "../../etc/passwd"}).status_code == 422
    assert api.post("/api/runs").status_code == 422
    monkeypatch.setenv("BIDWIT_MAX_UPLOAD_MB", "1")
    small = create_app(runner)
    with TestClient(small) as c:
        assert c.post("/api/runs", files={"file": ("x.pdf", b"%PDF-" + b"0" * (1 << 21), "application/pdf")}).status_code == 413
    assert not list(runner.runs_dir.glob("run-*")) if runner.runs_dir.exists() else True
    assert api.get("/api/runs/not-a-run").status_code == 404 and api.get("/api/runs/run-20260101-000000-abcdef").status_code == 404
