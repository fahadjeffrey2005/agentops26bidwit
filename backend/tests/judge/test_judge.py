from datetime import date

from bidwit.core.contracts import Evidence, EvidenceHit, Requirement, Retrieval, Verdict
from bidwit.core.isolation import run_part
from bidwit.parts.judge import JudgeRequest, is_criterion, run

EV = Evidence(id="E-001", doc_id="d", title="t", text="x", confidentiality="public", date=date(2024, 1, 1))


def req(i, cat="eligibility", pf=True, text="The bidder must hold a valid certificate for this work"):
    return Requirement(id=f"R-{i:03d}", text=text, page=1, category=cat, pass_fail=pf)


def ret(i, score=None, unc=(), meaning=None):
    hits = () if score is None else (EvidenceHit(evidence=EV, rank=1, keyword_score=score, meaning_score=meaning),)
    return Retrieval(clause_id=f"R-{i:03d}", hits=hits, uncovered_terms=unc)


def test_go_when_every_pass_fail_requirement_is_backed():
    v = run(JudgeRequest(requirements=(req(1), req(2)), retrievals=(ret(1, 10.0), ret(2, 5.0))))
    assert v.decision == "go" and v.pass_fail_covered == 2 and v.blocking == ()


def test_reasons_for_each_kind_of_gap():
    v = run(JudgeRequest(requirements=(req(1), req(2), req(3)),
                         retrievals=(ret(1), ret(2, 20.0, unc=("iso 27001",)), ret(3, 1.5))))
    reasons = {g.requirement_id: g.reason for g in v.blocking}
    assert reasons == {"R-001": "no_evidence", "R-002": "missing_terms", "R-003": "no_evidence"}
    assert "iso 27001" in next(g.detail for g in v.blocking if g.requirement_id == "R-002")
    assert v.decision == "conditional"


def test_no_go_above_the_limit_and_limit_is_configurable():
    reqs = tuple(req(i) for i in range(1, 6))
    rets = tuple(ret(i) for i in range(1, 6))
    assert run(JudgeRequest(requirements=reqs, retrievals=rets)).decision == "no_go"
    assert run(JudgeRequest(requirements=reqs, retrievals=rets, conditional_max=5)).decision == "conditional"


def test_strong_meaning_match_counts_in_hybrid_mode():
    v = run(JudgeRequest(requirements=(req(1),), retrievals=(ret(1, 1.0, meaning=0.82),)))
    assert v.decision == "go"


def test_only_pass_fail_eligibility_and_technical_count():
    reqs = (req(1, cat="commercial"), req(2, cat="format"), req(3, pf=False), req(4, cat="technical"))
    v = run(JudgeRequest(requirements=reqs, retrievals=(ret(4, 9.0),)))
    assert v.pass_fail_total == 1 and v.decision == "go"


def test_fragments_and_titles_are_not_criteria():
    assert not is_criterion("Note:") and not is_criterion("Guidelines to be followed prior to submitting an application-")
    assert not is_criterion("Dated this day (Signature)") and is_criterion("Bidder should have presence at all Tier 1 cities in India")


def test_missing_retrieval_is_a_gap_not_a_crash():
    v = run(JudgeRequest(requirements=(req(1),), retrievals=()))
    assert v.blocking[0].reason == "no_evidence"


def test_through_run_part():
    res, _ = run_part("judge", run, JudgeRequest(requirements=(req(1),), retrievals=(ret(1, 9.0),)), Verdict)
    assert res.ok and res.value.decision == "go"
