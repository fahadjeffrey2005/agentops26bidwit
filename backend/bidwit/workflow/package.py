"""Final step: write the run's outputs. Works on whatever the run reached, even if it stopped early.

  report.json         everything a reviewer or the UI needs (verdict, counts, every item, errors, gates)
  compliance.csv      one row per requirement: answered / complied / gap / skipped (not a criterion) / not_drafted, evidence, decision
  bid_draft.md        approved answers with citations, then every gap (nothing hidden)
  audit.jsonl         one line per event, in order
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from bidwit.core.contracts import SCHEMA_VERSION
from bidwit.core.evidence import is_criterion

GROUP_COMPLY, GROUP_PERSON = "G-COMPLY", "G-PERSON"           # same ids as the Gate B queue


def _dump(x: Any) -> Any:
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else x


def build_report(s: dict) -> dict:
    reqs = s.get("requirements") or []
    draft, check, verdict = s.get("draft"), s.get("check"), s.get("verdict")
    decisions = (s.get("gate_b") or {}).get("decisions") or {}
    claims = {c.requirement_id: c for c in (draft.claims if draft else ())}
    gaps = {g.requirement_id: g for g in (draft.gaps if draft else ())}
    comply = {k.requirement_id: k for k in (draft.confirmations if draft else ())}
    failing = set(check.failing_claims) if check else set()
    rows = []
    for r in reqs:
        c, g = claims.get(r.id), gaps.get(r.id)
        k = comply.get(r.id)
        if c or g or k:
            status = "answered" if c else ("gap" if g else "complied")
        elif not is_criterion(r.text) or r.category == "other":
            status = "skipped"                            # fragment, title or general information: not a criterion
        else:
            status = "not_drafted"                        # only when the run stopped before writing
        if c:
            decision = decisions.get(c.id, "")
        elif k:
            decision = decisions.get(GROUP_COMPLY, "")
        elif g and g.reason == "human_decides":
            decision = decisions.get(r.id) or decisions.get(GROUP_PERSON, "")
        else:
            decision = decisions.get(r.id, "")
        rows.append({"requirement_id": r.id, "requirement": r.text[:400], "page": r.page, "section": r.section or "", "category": r.category,
                     "pass_fail": r.pass_fail, "status": status, "claim_id": c.id if c else "",
                     "answer": c.text if c else (k.statement if k else ""), "evidence_ids": list(c.evidence_ids) if c else [],
                     "checks_passed": (c.id not in failing) if c else None,
                     "gap_reason": g.reason if g else "", "gap_detail": g.detail if g else "",
                     "human_decision": decision})
    x = s.get("extract")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": s.get("run_id", ""),
        "tender": {"file": x.file, "sha256": x.sha256, "pages": x.pages, "units": len(x.clauses),
                   "flags": [_dump(n) for n in x.notes]} if x else None,
        "stopped": s.get("stopped") or "",
        "verdict": _dump(verdict) if verdict else None,
        "modes": {"classify": s["labels"].mode if s.get("labels") else ("fallback" if reqs else None),
                  "retrieve": s["retrieve"].mode if s.get("retrieve") else None,
                  "writer": draft.mode if draft else None},
        "counts": {"requirements": len(reqs), "pass_fail": sum(r.pass_fail for r in reqs),
                   "answered": len(claims), "gaps": len(gaps), "complied": len(comply),
                   "skipped": sum(x["status"] == "skipped" for x in rows), "failed_checks": len(failing),
                   "rewrite_rounds": s.get("rewrites", 0),
                   "approved": sum(v == "approve" for v in decisions.values()),
                   "rejected": sum(v == "reject" for v in decisions.values())},
        "ai_calls": (s["labels"].ai_calls if s.get("labels") else 0) + (draft.ai_calls if draft else 0),
        "rounds": list(s.get("rounds") or []),
        "final": bool(s.get("report")) or bool(s.get("gate_b")) or bool(s.get("stopped")),
        "silent_misses_count": len(check.silent_misses) if check else None,
        "silent_misses": list(check.silent_misses) if check else [],
        "blocked_evidence": [_dump(b) for b in s["retrieve"].blocked] if s.get("retrieve") else [],
        "gate_a": s.get("gate_a"), "gate_b": s.get("gate_b"),
        "errors": [_dump(e) for e in s.get("errors") or []],
        "seconds": round(time.time() - s["started"], 1) if s.get("started") else None,
        "items": rows,
    }


def _markdown(rep: dict, s: dict) -> str:
    ev = {h.evidence.id: h.evidence.title for ret in (s["retrieve"].results if s.get("retrieve") else ())
          for h in ret.hits}
    v = rep["verdict"] or {}
    out = [f"# Bid draft: {rep['tender']['file'] if rep['tender'] else 'tender not read'}", "",
           f"Company: Northwind IT Infrastructure Services. Run {rep['run_id']}.", ""]
    if rep["stopped"]:
        out += [f"**Run stopped:** {rep['stopped']}", ""]
    if v:
        out += [f"**Bid decision: {v['decision'].upper().replace('_', '-')}.** {v['summary']}", ""]
    approved = [r for r in rep["items"] if r["status"] == "answered" and r["human_decision"] == "approve"]
    pending = [r for r in rep["items"] if r["status"] == "answered" and r["human_decision"] == ""]
    out += ["## Approved answers", ""]
    for r in approved:
        cites = ", ".join(f"{e} ({ev.get(e, '?')})" for e in r["evidence_ids"])
        out += [f"**{r['requirement_id']}** (page {r['page']}): {r['answer']}", f"  - Evidence: {cites}", ""]
    if not approved:
        out += ["None yet.", ""]
    if pending:
        out += ["## Answers awaiting review", ""] + [f"- {r['requirement_id']}: {r['answer']}" for r in pending] + [""]
    comp = [r for r in rep["items"] if r["status"] == "complied"]
    if comp:
        state = {"approve": "confirmed by the reviewer", "reject": "REJECTED by the reviewer"}.get(comp[0]["human_decision"],
                                                                                                  "awaiting review")
        out += [f"## Compliance statements ({len(comp)}, {state})", "",
                f"{comp[0]['answer']} Applies to: " + ", ".join(r["requirement_id"] for r in comp) + ".", ""]
    gaps = [r for r in rep["items"] if r["status"] == "gap"]
    out += ["## Gaps (need a person)", ""]
    out += [f"- {r['requirement_id']} (page {r['page']}, {r['gap_reason']}): {r['gap_detail']}" for r in gaps] or ["None."]
    out += ["", f"Silent misses: {rep['silent_misses_count'] if rep['silent_misses_count'] is not None else 'not checked'}"]
    return "\n".join(out) + "\n"


def write_outputs(s: dict) -> tuple[dict, list[str]]:
    rep = build_report(s)
    out = Path(s["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    cols = ["requirement_id", "requirement", "page", "section", "category", "pass_fail", "status", "claim_id", "evidence_ids",
            "checks_passed", "gap_reason", "gap_detail", "human_decision", "answer"]
    with (out / "compliance.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rep["items"]:
            w.writerow({**r, "evidence_ids": " ".join(r["evidence_ids"])})
    (out / "bid_draft.md").write_text(_markdown(rep, s), encoding="utf-8")
    with (out / "audit.jsonl").open("w", encoding="utf-8") as f:
        for e in s.get("audit") or []:
            f.write(e.model_dump_json() + "\n")
    return rep, ["report.json", "compliance.csv", "bid_draft.md", "audit.jsonl"]
