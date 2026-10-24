"""Part 5a: the Judge. Go / conditional / no-go, decided by code (no AI), every reason listed.

    run(JudgeRequest) -> Verdict

Only pass/fail requirements count. Among them:
- eligibility / technical ones need company evidence: a strong match with no missing required term.
  Without it they are BLOCKING gaps.
- format / commercial ones (deadline, EMD payment, documents to upload) are actions for a person,
  not evidence questions; they never block the decision but are listed as human tasks elsewhere.
Decision: 0 blocking gaps -> go; 1..conditional_max -> conditional; more -> no_go (a human confirms a no-go).
"""
from __future__ import annotations

from pydantic import Field

from bidwit.core.contracts import Requirement, Retrieval, Strict, Verdict
from bidwit.core.evidence import evidence_gap, is_criterion  # noqa: F401  (re-exported for tests)

PART = "judge"


class JudgeRequest(Strict):
    requirements: tuple[Requirement, ...]
    retrievals: tuple[Retrieval, ...]
    conditional_max: int = Field(default=3, ge=0, le=50)


def run(req: JudgeRequest) -> Verdict:
    rets = {r.clause_id: r for r in req.retrievals}
    needs_evidence = [r for r in req.requirements if r.pass_fail and r.category in ("eligibility", "technical")
                      and is_criterion(r.text)]
    blocking = [g for r in needs_evidence if (g := evidence_gap(r, rets.get(r.id))) is not None]
    covered = len(needs_evidence) - len(blocking)
    if not blocking:
        decision = "go"
    elif len(blocking) <= req.conditional_max:
        decision = "conditional"
    else:
        decision = "no_go"
    ids = ", ".join(g.requirement_id for g in blocking[:8]) + (" ..." if len(blocking) > 8 else "")
    summary = (f"{covered}/{len(needs_evidence)} pass/fail requirements backed by company evidence"
               + (f"; {len(blocking)} blocking gap(s): {ids}" if blocking else ""))
    return Verdict(decision=decision, summary=summary[:400], pass_fail_total=len(needs_evidence),
                   pass_fail_covered=covered, blocking=tuple(blocking))
