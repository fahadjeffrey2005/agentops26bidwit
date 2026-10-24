"""Part 6: the workflow end to end, on a small synthetic tender (fast) with the real classify/kb/judge/checker,
a fake Groq for the Writer, and no network. Crashes are planted to prove one failing part never kills a run."""
import json
from datetime import date

import httpx
import pytest

import bidwit.core.llm as llm
import bidwit.parts.checker as checker
import bidwit.parts.classify as classify
import bidwit.parts.extract as extract
import bidwit.parts.judge as judge
import bidwit.parts.kb as kb
import bidwit.parts.writer as writer
import bidwit.workflow.graph as graph
from bidwit.core.contracts import Clause, ExtractResult, Source, Verdict
from bidwit.core.llm import LLMClient, parse_chain
from bidwit.workflow import MAX_REWRITES, Runner, RunNotFound, RunNotWaiting

from ..agents_shared import fake_client
from ..test_agents import honest

SEC = "Section 4: Eligibility Criteria"
TEXTS = [
    ("heading", "ELIGIBILITY CRITERIA", None),
    ("clause", "The bidder should have an average annual turnover of at least Rs. 10 Crores per annum for last three financial years", SEC),
    ("clause", "The bidder should not be blacklisted by any Government, PSU or Bank within the last 3 years", SEC),
    ("clause", "The bidder must have valid ISO 27001 certification for its 24x7 Network Operations Centre", SEC),
    ("clause", "The bidder should have experience managing at least 900 network devices across bank branches", SEC),
    ("clause", "Interest free Earnest Money Deposit of Rs.5,00,000 to be paid by RTGS before submission of the bid", "Section 6: Commercial"),
    ("clause", "Note:", "Section 6: Commercial"),
    ("clause", "The bidder shall repaint the rack cabinets in the corporate colour scheme once every year", "Section 7: Scope of Work"),
]
TODAY = date(2026, 10, 24)


def tender(_req):
    clauses = tuple(Clause(id=f"R-{i:03d}", kind=k, text=t, section=s, source=Source(file="t.pdf", page=1 + i // 3, end_page=1 + i // 3))
                    for i, (k, t, s) in enumerate(TEXTS, 1))
    return ExtractResult(file="t.pdf", sha256="a" * 64, pages=3, clauses=clauses)


def dead_client():
    return LLMClient(parse_chain("groq:m1", httpx.MockTransport(lambda r: httpx.Response(401))), cache_dir=None, max_calls=5)


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("BIDWIT_LLM", "on")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)          # meaning search falls back to keyword: no network
    monkeypatch.setenv("BIDWIT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(extract, "run", tender)
    monkeypatch.setattr(classify, "make_client", dead_client)     # classify AI down -> rules (still a full run)
    seen = []
    monkeypatch.setattr(writer, "make_client", lambda: fake_client(honest, seen, tmp_path / "llm"))
    r = Runner(runs_dir=tmp_path / "runs")
    r.seen = seen
    return r


def to_end(r, v, a=None, b=None):
    assert v["status"] == "waiting" and v["gate"]["gate"] == "A", v
    v = r.resume(v["run_id"], a or {"reviewer": "Fahad"})
    if v["status"] == "waiting" and v["gate"]["gate"] == "B":
        v = r.resume(v["run_id"], b if b is not None else {"reviewer": "Fahad", "decisions": {x["id"]: "approve" for x in v["gate"]["queue"]}})
    return v


def test_happy_path_pauses_at_both_gates_and_writes_every_output(runner):
    v = runner.start("t.pdf", today=TODAY)
    assert v["gate"]["gate"] == "A" and {x["id"] for x in v["gate"]["pass_fail"]} >= {"R-002", "R-003", "R-004", "R-005"}
    v = runner.resume(v["run_id"], {"reviewer": "Fahad"})
    q = v["gate"]["queue"]
    assert v["gate"]["gate"] == "B" and q
    order = ["failed_check", "blocking_gap", "gap", "pass_fail", "answer", "human_task", "compliance"]
    assert [order.index(x["risk"]) for x in q] == sorted(order.index(x["risk"]) for x in q)       # risk first
    v = runner.resume(v["run_id"], {"reviewer": "Fahad", "decisions": {x["id"]: "approve" for x in q}})
    rep = v["report"]
    assert v["status"] == "done" and rep["silent_misses_count"] == 0 and rep["counts"]["answered"] >= 1
    assert {"R-004", "R-006"} <= {i["requirement_id"] for i in rep["items"] if i["status"] == "gap"}  # expired ISO; EMD is a person's job
    assert next(i for i in rep["items"] if i["requirement_id"] == "R-007")["status"] == "skipped"     # "Note:" is not a criterion
    files = {p.name for p in (runner.runs_dir / v["run_id"]).iterdir()}
    assert files == {"report.json", "compliance.csv", "bid_draft.md", "audit.jsonl"}
    md = (runner.runs_dir / v["run_id"] / "bid_draft.md").read_text()
    assert "## Approved answers" in md and "E-001" in md and "R-006" in md
    assert all(e["level"] != "error" for e in v["audit"]), v["audit"]


def test_gate_a_edits_are_applied(runner):
    v = runner.start("t.pdf", today=TODAY)
    v = to_end(runner, v, a={"reviewer": "A", "not_requirements": ["R-005"], "pass_fail_remove": ["R-003"]})
    items = {i["requirement_id"]: i for i in v["report"]["items"]}
    assert "R-005" not in items and items["R-003"]["pass_fail"] is False


def test_lying_writer_is_rewritten_at_most_twice_then_shown_to_the_human(runner, monkeypatch, tmp_path):
    def liar(items):
        return {"answers": [{"i": x["i"], "text": "Northwind led 9,999 sites and guarantees compliance.",
                             "evidence_ids": [x["evidence"][0]["id"]], "quote": "the largest provider in the world"} for x in items]}
    calls = []
    monkeypatch.setattr(writer, "make_client", lambda: fake_client(liar, calls, tmp_path / "liar"))
    v = runner.start("t.pdf", today=TODAY)
    v = runner.resume(v["run_id"], {"reviewer": "x"})
    assert v["gate"]["gate"] == "B" and len(calls) == 1 + MAX_REWRITES
    q = v["gate"]["queue"]
    assert q[0]["risk"] == "failed_check" and any("overclaim" in c for c in q[0]["checks"])
    v = runner.resume(v["run_id"], {"reviewer": "x", "decisions": {}})
    assert v["report"]["counts"]["failed_checks"] >= 1 and v["report"]["counts"]["rewrite_rounds"] == 1 + MAX_REWRITES


def test_no_go_stops_by_default_and_can_be_overridden(runner, monkeypatch):
    nogo = lambda req: Verdict(decision="no_go", summary="too many gaps", pass_fail_total=4, pass_fail_covered=0)
    monkeypatch.setattr(judge, "run", nogo)
    v = runner.resume(runner.start("t.pdf", today=TODAY)["run_id"], {})
    assert v["gate"]["gate"] == "no_go"
    v = runner.resume(v["run_id"], {})                                 # no explicit 'continue' -> stop (safe default)
    assert v["status"] == "done" and v["stopped"] and runner.seen == [] and v["report"]["verdict"]["decision"] == "no_go"
    v = runner.resume(runner.start("t.pdf", today=TODAY)["run_id"], {})
    v = runner.resume(v["run_id"], {"action": "continue", "reviewer": "boss"})
    assert v["gate"]["gate"] == "B" and runner.seen


@pytest.mark.parametrize("part", [kb, judge, writer, checker, classify])
def test_any_crashing_part_still_ends_the_run_with_no_silent_miss(runner, monkeypatch, part):
    def boom(_):
        raise RuntimeError("planted crash")
    monkeypatch.setattr(part, "run", boom)
    v = to_end(runner, runner.start("t.pdf", today=TODAY))
    if v["status"] == "waiting":                                        # judge crash -> safe no_go gate
        v = runner.resume(v["run_id"], {})
    assert v["status"] == "done" and v["report"]["errors"] and "planted crash" in v["report"]["errors"][0]["message"]
    if part is not checker:
        assert v["report"]["silent_misses_count"] in (0, None)


def test_unreadable_tender_ends_cleanly_with_a_report(runner, monkeypatch):
    monkeypatch.undo()                                                  # real extract: file does not exist
    v = Runner(runs_dir=runner.runs_dir).start("/nope/missing.pdf", today=TODAY)
    assert v["status"] == "done" and "could not be read" in v["stopped"] and v["report"]["tender"] is None
    assert json.loads((runner.runs_dir / v["run_id"] / "report.json").read_text())["stopped"]


def test_run_guards(runner):
    with pytest.raises(RunNotFound):
        runner.view("run-x")
    v = to_end(runner, runner.start("t.pdf", run_id="run-fixed", today=TODAY))
    with pytest.raises(RunNotWaiting):
        runner.resume(v["run_id"], {})
    with pytest.raises(RunNotWaiting):
        runner.start("t.pdf", run_id="run-fixed")


def test_a_bug_in_the_graph_itself_is_reported_not_raised(runner, monkeypatch):
    monkeypatch.setattr(graph, "review_queue", lambda s: 1 / 0)
    v = runner.resume(runner.start("t.pdf", today=TODAY)["run_id"], {})
    assert v["status"] == "failed" and "ZeroDivisionError" in v["failure"]


def test_gate_b_groups_person_tasks_and_compliance_statements(runner):
    v = runner.resume(runner.start("t.pdf", today=TODAY)["run_id"], {"reviewer": "x"})
    groups = {x["id"]: x for x in v["gate"]["queue"] if x["kind"] == "group"}
    assert [i["requirement_id"] for i in groups["G-COMPLY"]["items"]] == ["R-008"]
    assert "R-006" in [i["requirement_id"] for i in groups["G-PERSON"]["items"]]
    v = runner.resume(v["run_id"], {"reviewer": "x", "decisions": {"G-COMPLY": "approve", "G-PERSON": "approve"}})
    items = {i["requirement_id"]: i for i in v["report"]["items"]}
    assert items["R-008"]["status"] == "complied" and items["R-008"]["human_decision"] == "approve"
    assert items["R-006"]["human_decision"] == "approve" and v["report"]["silent_misses_count"] == 0


def test_progress_checkpoints_are_recorded_live(runner):
    v = runner.start("t.pdf", today=TODAY)
    msgs = [f"{p['part']}: {p['message']}" for p in v["progress"]]
    assert any("stage 1/7" in m for m in msgs) and any(m.startswith("classify:") for m in msgs)
    assert msgs[-1].startswith("workflow: waiting for Gate A")
