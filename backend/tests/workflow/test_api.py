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
    with TestClient(app, headers={"X-BidWit": "1"}) as c:
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
    with TestClient(fresh, headers={"X-BidWit": "1"}) as c:
        v = c.get(f"/api/runs/{rid}").json()
        assert v["status"] == "done" and v.get("archived") and v["report"]["run_id"] == rid
    fresh.state.pool.shutdown(wait=True)


def test_bad_uploads_are_refused_and_leave_nothing_behind(api, runner, monkeypatch):  # noqa: F811
    assert api.post("/api/runs", files={"file": ("x.pdf", b"MZ\x90 not a pdf", "application/pdf")}).status_code == 415
    assert api.post("/api/runs", data={"sample": "../../etc/passwd"}).status_code == 422
    assert api.post("/api/runs").status_code == 422
    monkeypatch.setenv("BIDWIT_MAX_UPLOAD_MB", "1")
    small = create_app(runner)
    with TestClient(small, headers={"X-BidWit": "1"}) as c:
        assert c.post("/api/runs", files={"file": ("x.pdf", b"%PDF-" + b"0" * (1 << 21), "application/pdf")}).status_code == 413
    assert not list(runner.runs_dir.glob("run-*")) if runner.runs_dir.exists() else True
    assert api.get("/api/runs/not-a-run").status_code == 404 and api.get("/api/runs/run-20260101-000000-abcdef").status_code == 404


def test_cross_site_and_rebinding_requests_are_refused(runner):  # noqa: F811
    app = create_app(runner)
    with TestClient(app) as c:                                         # no X-BidWit header: what a foreign page can send
        assert c.post("/api/runs", data={"sample": "tender_main"}).status_code == 403
        assert c.get("/api/health", headers={"host": "evil.example:8000"}).status_code == 421
        h = c.get("/api/health").headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and "default-src 'none'" in h["content-security-policy"]
    app.state.pool.shutdown(wait=True)


def test_oversized_json_is_refused_before_parsing(api):
    r = api.post("/api/runs/run-20260101-000000-abcdef/gates/A", content=b"{" + b" " * (1 << 20) + b"}", headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_too_many_active_runs_get_429(api, monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(api.app.state.runner, "start", lambda *a, **k: gate.wait(5))
    codes = [api.post("/api/runs", data={"sample": "tender_main"}).status_code for _ in range(4)]
    gate.set()
    assert codes == [202, 202, 202, 429]


def test_outputs_are_safe_to_open(runner, tmp_path):  # noqa: F811
    from bidwit.workflow.package import csv_safe, md_safe
    assert csv_safe("=HYPERLINK(\"http://x\")").startswith("'=") and csv_safe("+1") == "'+1" and csv_safe("ok") == "ok"
    assert md_safe("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_companies_and_profiles(api):
    cos = api.get("/api/companies").json()
    assert {c["id"] for c in cos} == {"northwind", "meridian"}
    p = api.get("/api/companies/meridian").json()
    assert p["name"] == "Meridian Netserve" and p["counts"]["blocked"] == 3
    restricted = next(d for d in p["documents"] if d["blocked_reason"] == "restricted")
    assert restricted["text"] is None                                  # never leaves the server
    assert api.get("/api/companies/../../etc").status_code in (404, 422)
    assert api.get("/api/companies/nope").status_code == 404


def test_run_uses_the_chosen_company(api, runner):  # noqa: F811
    started = {}
    real = runner.start
    runner.start = lambda path, rid=None, today=None, company="northwind", cached_only=False: (
        started.update(company=company), real(path, rid, today, company, cached_only))[1]
    r = api.post("/api/runs", data={"sample": "tender_main", "company": "meridian"})
    assert r.status_code == 202
    wait(api, r.json()["run_id"])
    assert started["company"] == "meridian"
    assert api.post("/api/runs", data={"sample": "tender_main", "company": "ghost"}).status_code == 422


def test_cached_only_never_calls_a_provider(api, runner, monkeypatch):  # noqa: F811
    """The demo switch: with no cached answer, the AI parts fall back instead of reaching the network."""
    import httpx
    import bidwit.parts.classify as classify
    import bidwit.parts.writer as writer
    from bidwit.core.llm import LLMClient, parse_chain

    def no_network(request):
        raise AssertionError(f"a provider was called in cached-only mode: {request.url}")

    def client():
        return LLMClient(parse_chain("groq:m1", httpx.MockTransport(no_network)), cache_dir=None, max_calls=50)
    monkeypatch.setattr(classify, "make_client", client)
    monkeypatch.setattr(writer, "make_client", client)
    rid = api.post("/api/runs", data={"sample": "tender_main", "cached": "true"}).json()["run_id"]
    v = wait(api, rid)
    assert v["status"] == "waiting" and v["gate"]["gate"] == "A"      # reached Gate A without any provider call
    assert v["gate"]["classify_mode"] == "rules"                      # nothing cached here, so it fell back
    assert isinstance(api.get("/api/health").json()["cached_answers"], int)
