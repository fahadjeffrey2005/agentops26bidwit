"""The workflow (LangGraph). Every step runs through run_part: a crash becomes a recorded error and a safe
fallback, never a dead run. Only an unreadable tender stops the run (there is nothing to work on).

  extract -> classify -> GATE A (human approves the checklist) -> retrieve -> judge
     -> [no_go? -> GATE NO-GO: human stops or overrides]
     -> write <-> check (at most MAX_REWRITES rewrites) -> GATE B (human reviews every item) -> package

Gates use interrupt(): the run pauses, its state is checkpointed, and it resumes with the human's answer.
"""
from __future__ import annotations

import operator
import time
from datetime import date
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from bidwit.core.config import load_settings
from bidwit.core.contracts import (AuditEvent, CheckReport, ClassifyResult, Draft, ExtractResult, Gap, PartError, Requirement,
                                   RetrieveResult, Verdict)
from bidwit.core.evidence import is_criterion
from bidwit.core.isolation import run_part
from bidwit.core.progress import step
from bidwit.parts import checker, classify, extract, judge, kb, writer
from bidwit.parts.classify.rules import wording_signal

from .companies import evidence_file
from .package import write_outputs

MAX_REWRITES = 2
STAGES = {"extract": "stage 1/7: reading the tender", "classify": "stage 2/7: classifying requirements",
          "gate_a": "waiting for Gate A (human approves the checklist)", "retrieve": "stage 3/7: searching company evidence",
          "judge": "stage 4/7: bid / no-bid decision", "gate_nogo": "waiting for the no-go gate (human decides)",
          "write": "stage 5/7: drafting answers", "check": "stage 6/7: checking every answer",
          "gate_b": "waiting for Gate B (human reviews)", "package": "stage 7/7: writing the outputs"}


class RunState(TypedDict, total=False):
    run_id: str
    tender_path: str
    company: str                                         # which bidder's evidence library to search
    cached_only: bool                                    # demo mode: AI answers come from the cache only
    out_dir: str
    today: date
    started: float
    extract: ExtractResult
    labels: ClassifyResult
    requirements: list[Requirement]
    retrieve: RetrieveResult
    verdict: Verdict
    draft: Draft
    check: CheckReport
    rewrites: int
    gate_a: dict
    gate_b: dict
    stopped: str                                         # why the run stopped early ("" if it didn't)
    errors: Annotated[list[PartError], operator.add]
    audit: Annotated[list[AuditEvent], operator.add]
    rounds: Annotated[list[dict], operator.add]          # per checker round: {round, passed, total}
    report: dict


def human(raw: Any) -> dict:
    """The human's answer, as sent by Runner.resume (wrapped so an empty answer still counts as an answer)."""
    raw = raw.get("answer") if isinstance(raw, dict) else None
    return raw if isinstance(raw, dict) else {}


def note(part: str, event: str, level: str = "info", **data: Any) -> list[AuditEvent]:
    clean = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool)) or v is None}
    return [AuditEvent(part=part, level=level, event=event[:500], data=clean)]


# ---------------------------------------------------------------- 1. extract
def n_extract(s: RunState):
    st = load_settings()
    res, ev = run_part("extract", extract.run, extract.ExtractRequest(path=s["tender_path"], max_mb=st.max_upload_mb),
                       ExtractResult)
    if not res.ok:
        return {"stopped": f"tender could not be read: {res.error.message}", "errors": [res.error], "audit": [ev],
                "started": time.time()}
    x = res.value
    flags = [f"p{n.page} {n.flag}" for n in x.notes]
    return {"extract": x, "started": time.time(), "rewrites": 0, "stopped": "",
            "audit": [ev] + note("extract", f"{x.pages} pages, {len(x.clauses)} units" + (f"; flags: {flags}" if flags else ""))}


def after_extract(s: RunState) -> str:
    return "package" if s.get("stopped") else "classify"


# ---------------------------------------------------------------- 2. classify
def n_classify(s: RunState):
    clauses = s["extract"].clauses
    res, ev = run_part("classify", classify.run, classify.ClassifyRequest(clauses=clauses), ClassifyResult)
    by_id = {c.id: c for c in clauses}
    if res.ok:
        labels = res.value
        reqs = [Requirement(id=l.clause_id, text=by_id[l.clause_id].text, section=by_id[l.clause_id].section,
                            page=by_id[l.clause_id].source.page, category=l.category, pass_fail=l.pass_fail)
                for l in labels.labels if l.labelled_by != "template"]
        extra = note("classify", f"mode={labels.mode}; {sum(r.pass_fail for r in reqs)} pass/fail of {len(reqs)} requirements"
                     + (f"; {labels.mode_reason}" if labels.mode_reason else ""), providers=",".join(labels.providers),
                     ai_calls=labels.ai_calls)
        return {"labels": labels, "requirements": reqs, "audit": [ev] + extra}
    # safe fallback: every non-heading unit becomes a requirement, flagged pass/fail by wording, category for a human
    reqs = [Requirement(id=c.id, text=c.text, section=c.section, page=c.source.page, category="technical",
                        pass_fail=wording_signal(c.text)) for c in clauses if c.kind not in ("heading", "table_header")]
    return {"requirements": reqs, "errors": [res.error], "audit": [ev] + note("classify", "classification failed; "
            "fallback: wording-only pass/fail, category to be checked by a human", "warn")}


# ---------------------------------------------------------------- GATE A
def n_gate_a(s: RunState):
    reqs = s["requirements"]
    answer = interrupt({
        "gate": "A",
        "notes": [n.model_dump(mode="json") for n in s["extract"].notes],
        "pass_fail": [r.model_dump(mode="json") for r in reqs if r.pass_fail],
        "requirement_count": len(reqs),
        "classify_mode": s["labels"].mode if "labels" in s else "fallback",
    })
    answer = human(answer)
    drop, add, remove = (set(answer.get(k) or []) for k in ("not_requirements", "pass_fail_add", "pass_fail_remove"))
    out = []
    for r in reqs:
        if r.id in drop:
            continue
        if r.id in add and not r.pass_fail:
            r = r.model_copy(update={"pass_fail": True})
        elif r.id in remove and r.pass_fail:
            r = r.model_copy(update={"pass_fail": False})
        out.append(r)
    return {"requirements": out, "gate_a": answer,
            "audit": note("gate_a", f"checklist approved by {str(answer.get('reviewer') or 'unnamed')[:60]}: "
                          f"{len(drop)} removed, {len(add)} marked pass/fail, {len(remove)} unmarked")}


# ---------------------------------------------------------------- 3. retrieve
def n_retrieve(s: RunState):
    st = load_settings()
    asked = [r for r in s["requirements"] if is_criterion(r.text) and r.category in ("eligibility", "technical")]
    rq = kb.RetrieveRequest(evidence_path=evidence_file(st.data_dir, s.get("company")), today=s["today"],
                            queries=tuple(kb.Query(clause_id=r.id, text=r.text) for r in asked),
                            meaning=st.llm == "on", cache_dir=str(st.runs_dir / "cache"))
    res, ev = run_part("kb", kb.run, rq, RetrieveResult)
    if not res.ok:
        empty = RetrieveResult(mode="keyword", mode_reason=f"evidence search failed: {res.error.message}"[:300], indexed=0)
        return {"retrieve": empty, "errors": [res.error], "audit": [ev] + note("kb", "evidence search failed; "
                "every requirement will show as a gap", "warn")}
    r = res.value
    blocked = [f"{b.id} ({b.reason})" for b in r.blocked]
    return {"retrieve": r, "audit": [ev] + note("kb", f"mode={r.mode}; searched {len(asked)} requirements in {r.indexed} records; "
                                              f"blocked: {', '.join(blocked) or 'none'}" + (f"; {r.mode_reason}" if r.mode_reason else ""))}


# ---------------------------------------------------------------- 4. judge
def n_judge(s: RunState):
    res, ev = run_part("judge", judge.run, judge.JudgeRequest(requirements=tuple(s["requirements"]),
                                                              retrievals=s["retrieve"].results), Verdict)
    if not res.ok:
        v = Verdict(decision="no_go", summary=f"judge failed ({res.error.message}); a human must decide"[:400],
                    pass_fail_total=0, pass_fail_covered=0)
        return {"verdict": v, "errors": [res.error], "audit": [ev] + note("judge", v.summary, "warn")}
    v = res.value
    return {"verdict": v, "audit": [ev] + note("judge", f"{v.decision.upper()}: {v.summary}")}


def after_judge(s: RunState) -> str:
    return "gate_nogo" if s["verdict"].decision == "no_go" else "write"


def n_gate_nogo(s: RunState):
    answer = interrupt({"gate": "no_go", "verdict": s["verdict"].model_dump(mode="json")})
    answer = human(answer)
    stop = answer.get("action") != "continue"            # anything but an explicit 'continue' stops: safe default
    who = str(answer.get("reviewer") or "unnamed")[:60]
    return {"stopped": "no-go confirmed by a human" if stop else "",
            "audit": note("gate_nogo", f"{who} {'confirmed the no-go' if stop else 'overrode the no-go'}")}


def after_nogo(s: RunState) -> str:
    return "package" if s.get("stopped") else "write"


# ---------------------------------------------------------------- 5. write <-> check
def n_write(s: RunState):
    rq = writer.WriteRequest(requirements=tuple(s["requirements"]), retrievals=s["retrieve"].results,
                             previous=s.get("draft") if s.get("rewrites") else None, attempt=s.get("rewrites", 0),
                             failures=tuple(r for r in s["check"].results if not r.passed) if s.get("rewrites") else ())
    res, ev = run_part("writer", writer.run, rq, Draft)
    if not res.ok:   # every criterion becomes a gap: a dead writer must never leave a silent miss
        why = f"writer failed: {res.error.message}"[:300]
        gaps = tuple(Gap(requirement_id=r.id, reason="ai_unavailable", detail=why) for r in s["requirements"]
                     if is_criterion(r.text) and r.category != "other")
        d = Draft(gaps=gaps, mode="none", mode_reason=why)
        return {"draft": d, "errors": [res.error], "audit": [ev] + note("writer", d.mode_reason, "warn")}
    d = res.value
    return {"draft": d, "audit": [ev] + note("writer", f"round {s.get('rewrites', 0)}: {len(d.claims)} answers, {len(d.gaps)} gaps, "
                                           f"{len(d.confirmations)} compliance statements"
                                           + (f"; {d.mode_reason}" if d.mode_reason else ""), ai_calls=d.ai_calls)}


def n_check(s: RunState):
    blocked = tuple(b.id for b in s["retrieve"].blocked)
    rq = checker.CheckRequest(requirements=tuple(s["requirements"]), retrievals=s["retrieve"].results,
                              draft=s["draft"], blocked_ids=blocked)
    res, ev = run_part("checker", checker.run, rq, CheckReport)
    if not res.ok:   # checker down: nothing is trusted; every claim goes to the human as failed
        rep = CheckReport(failing_claims=tuple(c.id for c in s["draft"].claims))
        return {"check": rep, "errors": [res.error], "rewrites": MAX_REWRITES + 1,     # no rewrite loop on a dead checker
                "audit": [ev] + note("checker", "checker failed; every answer marked unchecked for the human", "warn")}
    rep = res.value
    fails = [r for r in rep.results if not r.passed and r.check != "coverage"]
    events = [ev] + note("checker", f"{len(rep.failing_claims)} answers failed checks; silent misses: {len(rep.silent_misses)}")
    events += [e for f in fails[:20] for e in note("checker", f"FAIL {f.target_id} {f.check}: {f.detail}", "warn")]
    total = len(s["draft"].claims)
    rnd = {"round": s.get("rewrites", 0) + 1, "passed": total - len(rep.failing_claims), "total": total}
    return {"check": rep, "rewrites": s.get("rewrites", 0) + (1 if rep.failing_claims else 0), "audit": events,
            "rounds": [rnd]}


def after_check(s: RunState) -> str:
    return "write" if s["check"].failing_claims and s["rewrites"] <= MAX_REWRITES and s["draft"].mode == "ai" else "gate_b"


# ---------------------------------------------------------------- GATE B
GROUP_COMPLY, GROUP_PERSON = "G-COMPLY", "G-PERSON"


def review_queue(s: RunState) -> list[dict]:
    """Risk first: failed checks, blocking gaps, other gaps, pass/fail answers, other answers, then two groups decided
    with one click each: tasks only a person can do (prices, EMD, signatures) and standard compliance statements."""
    reqs = {r.id: r for r in s["requirements"]}
    failing = set(s["check"].failing_claims)
    blocking = {g.requirement_id for g in s["verdict"].blocking}
    fails = {}
    for r in s["check"].results:
        if not r.passed and r.check != "coverage":
            fails.setdefault(r.target_id, []).append(f"{r.check}: {r.detail}")
    ev = {h.evidence.id: h.evidence for ret in s["retrieve"].results for h in ret.hits}
    brief = lambda rid: {"requirement_id": rid, "page": reqs[rid].page if rid in reqs else None,
                         "requirement": reqs[rid].text if rid in reqs else ""}
    q, person = [], []
    for c in s["draft"].claims:
        r = reqs[c.requirement_id]
        risk = "failed_check" if c.id in failing else ("pass_fail" if r.pass_fail else "answer")
        q.append({"id": c.id, "kind": "answer", "risk": risk, **brief(r.id), "answer": c.text, "quote": c.quote,
                  "checks": fails.get(c.id, []),
                  "evidence": [{"id": e, "title": ev[e].title, "text": ev[e].text} for e in c.evidence_ids if e in ev]})
    for g in s["draft"].gaps:
        if g.reason == "human_decides" and g.requirement_id not in blocking:
            person.append({**brief(g.requirement_id), "detail": g.detail})
            continue
        q.append({"id": g.requirement_id, "kind": "gap", "risk": "blocking_gap" if g.requirement_id in blocking else "gap",
                  **brief(g.requirement_id), "reason": g.reason, "detail": g.detail})
    if person:
        q.append({"id": GROUP_PERSON, "kind": "group", "risk": "human_task", "count": len(person), "items": person,
                  "detail": "commercial and format items a person must do or decide (prices, EMD, signatures, uploads)"})
    comply = s["draft"].confirmations
    if comply:
        q.append({"id": GROUP_COMPLY, "kind": "group", "risk": "compliance", "count": len(comply),
                  "statement": comply[0].statement, "items": [brief(k.requirement_id) for k in comply],
                  "detail": "scope duties answered with a standard compliance statement"})
    order = {"failed_check": 0, "blocking_gap": 1, "gap": 2, "pass_fail": 3, "answer": 4, "human_task": 5, "compliance": 6}
    return sorted(q, key=lambda x: order[x["risk"]])


def n_gate_b(s: RunState):
    queue = review_queue(s)
    answer = interrupt({"gate": "B", "queue": queue, "verdict": s["verdict"].model_dump(mode="json")})
    answer = human(answer)
    decisions = answer.get("decisions") or {}
    ids = {x["id"] for x in queue}
    decided = {k: v for k, v in decisions.items() if k in ids and v in ("approve", "reject")}
    who = str(answer.get("reviewer") or "unnamed")[:60]
    return {"gate_b": {"reviewer": who, "decisions": decided},
            "audit": note("gate_b", f"{who} reviewed {len(decided)}/{len(queue)} items: "
                          f"{sum(v == 'approve' for v in decided.values())} approved, {sum(v == 'reject' for v in decided.values())} rejected"
                          + ("; undecided items stay open" if len(decided) < len(queue) else ""))}


# ---------------------------------------------------------------- 6. package
def n_package(s: RunState):
    try:
        report, files = write_outputs(s)
    except Exception as e:                                # noqa: BLE001 - the run must still end with a result
        err = PartError(kind="crash", type=type(e).__name__[:120], message=str(e)[:500] or "package failed")
        return {"report": {"run_id": s.get("run_id", ""), "stopped": s.get("stopped") or "", "package_error": err.message},
                "errors": [err], "audit": note("package", f"writing outputs failed: {err.message}", "error")}
    return {"report": report, "audit": note("package", f"outputs written: {', '.join(files)}; silent misses: "
                                                    f"{report.get('silent_misses_count', '-')}")}


def build_graph(checkpointer=None):
    g = StateGraph(RunState)
    def staged(name, fn):
        def node(s):
            step("workflow", STAGES[name])
            return fn(s)
        return node
    for name, fn in [("extract", n_extract), ("classify", n_classify), ("gate_a", n_gate_a), ("retrieve", n_retrieve),
                     ("judge", n_judge), ("gate_nogo", n_gate_nogo), ("write", n_write), ("check", n_check),
                     ("gate_b", n_gate_b), ("package", n_package)]:
        g.add_node(name, staged(name, fn))
    g.add_edge(START, "extract")
    g.add_conditional_edges("extract", after_extract, {"package": "package", "classify": "classify"})
    g.add_edge("classify", "gate_a")
    g.add_edge("gate_a", "retrieve")
    g.add_edge("retrieve", "judge")
    g.add_conditional_edges("judge", after_judge, {"gate_nogo": "gate_nogo", "write": "write"})
    g.add_conditional_edges("gate_nogo", after_nogo, {"package": "package", "write": "write"})
    g.add_edge("write", "check")
    g.add_conditional_edges("check", after_check, {"write": "write", "gate_b": "gate_b"})
    g.add_edge("gate_b", "package")
    g.add_edge("package", END)
    if checkpointer is None:
        ours = [("bidwit.core.contracts", n) for n in (
            "AuditEvent", "PartError", "ExtractResult", "Clause", "Source", "PageNote", "ClassifyResult", "ClauseLabel",
            "Requirement", "RetrieveResult", "Retrieval", "EvidenceHit", "Evidence", "BlockedDoc", "Verdict", "Gap",
            "Draft", "Claim", "CheckReport", "CheckResult")] + [("datetime", "date")]
        checkpointer = InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=ours))
    return g.compile(checkpointer=checkpointer)
