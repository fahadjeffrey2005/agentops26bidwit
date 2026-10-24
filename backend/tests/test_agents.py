import pytest

import bidwit.core.llm as llm
import bidwit.parts.writer as writer
from bidwit.core.contracts import CheckReport, Claim, Draft, Gap
from bidwit.core.isolation import run_part
from bidwit.parts.checker import CheckRequest, run as check
from bidwit.parts.writer import WriteRequest, plan, run as write

from .agents_shared import EV, fake_client, req, ret

TURNOVER = "Should have an average annual turnover of at least Rs. 10 Crores per annum for last three financial years"
BLACKLIST = "Bidder should not be blacklisted by any Government, PSU or Bank within the last 3 years"
TIER1 = "Bidder should have presence at all Tier 1 cities in India"
EMD = "Interest free Earnest Money Deposit of Rs.5,00,000 to be paid by RTGS before submission"
ISO = "The bidder must have valid ISO 27001:2013 certification for its 24x7 NOC"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("BIDWIT_LLM", "on")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def honest(items):
    """Fake writer that answers from the first evidence item, quoting it exactly."""
    out = []
    for x in items:
        ev = x["evidence"][0]
        words = ev["text"].split()
        out.append({"i": x["i"], "text": "Northwind meets this: " + " ".join(words[:18]),
                    "evidence_ids": [ev["id"]], "quote": " ".join(words[2:14])})
    return {"answers": out}


# ---------------------------------------------------------------- Writer: code decides what is drafted
def test_plan_routes_each_requirement():
    reqs = (req(1, TURNOVER), req(2, EMD, cat="commercial"), req(3, TIER1), req(4, ISO), req(5, "Note:"))
    rets = (ret(1, "E-001"), ret(2, "E-001"), ret(3, "E-029", score=3.2), ret(4, "E-003", unc=("iso 27001",)))
    to_draft, gaps = plan(WriteRequest(requirements=reqs, retrievals=rets))
    assert [r.id for r in to_draft] == ["R-001"]
    assert {g.requirement_id: g.reason for g in gaps} == {"R-002": "human_decides", "R-003": "no_evidence", "R-004": "missing_terms"}


def test_draft_limit_keeps_pass_fail_first_and_lists_the_rest():
    reqs = (req(1, TURNOVER, cat="technical", pf=False), req(2, BLACKLIST), req(3, TURNOVER + " again"))
    rets = (ret(1, "E-001", score=30), ret(2, "E-029", score=5), ret(3, "E-001", score=9))
    to_draft, gaps = plan(WriteRequest(requirements=reqs, retrievals=rets, max_drafts=2))
    assert [r.id for r in to_draft] == ["R-003", "R-002"] and gaps[0].reason == "over_draft_limit"


def test_writer_drafts_claims_with_ids_and_citations(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(writer, "make_client", lambda: fake_client(honest, seen, tmp_path))
    d = write(WriteRequest(requirements=(req(1, TURNOVER), req(2, BLACKLIST)), retrievals=(ret(1, "E-001"), ret(2, "E-029"))))
    assert [c.id for c in d.claims] == ["C-001", "C-002"] and d.claims[0].evidence_ids == ("E-001",)
    assert all(e["id"] in ("E-001", "E-029") for batch in seen for x in batch for e in x["evidence"])


def test_ai_off_turns_draftable_requirements_into_gaps_never_silence(monkeypatch):
    monkeypatch.setenv("BIDWIT_LLM", "off")
    d = write(WriteRequest(requirements=(req(1, TURNOVER),), retrievals=(ret(1, "E-001"),)))
    assert d.claims == () and d.gaps[0].reason == "ai_unavailable" and d.mode == "none"


def test_bad_evidence_id_from_ai_becomes_a_gap(monkeypatch, tmp_path):
    bad = lambda items: {"answers": [{"i": 0, "text": "We comply.", "evidence_ids": ["Client-C"], "quote": "x"}]}
    monkeypatch.setattr(writer, "make_client", lambda: fake_client(bad, [], tmp_path))
    d = write(WriteRequest(requirements=(req(1, TURNOVER),), retrievals=(ret(1, "E-001"),)))
    assert d.claims == () and d.gaps[0].reason == "failed_checks"


def test_rewrite_round_only_redoes_failed_claims_with_feedback(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(writer, "make_client", lambda: fake_client(honest, seen, tmp_path))
    first = write(WriteRequest(requirements=(req(1, TURNOVER), req(2, BLACKLIST)), retrievals=(ret(1, "E-001"), ret(2, "E-029"))))
    from bidwit.core.contracts import CheckResult
    fail = (CheckResult(target_id="C-002", check="overclaim", passed=False, detail="goes beyond the evidence: ['led']"),)
    seen.clear()
    second = write(WriteRequest(requirements=(req(1, TURNOVER), req(2, BLACKLIST)), retrievals=(ret(1, "E-001"), ret(2, "E-029")),
                                previous=first, failures=fail))
    assert len(seen) == 1 and len(seen[0]) == 1 and "led" in seen[0][0]["previous_answer_failed_because"]
    assert second.claims[0] == first.claims[0]


# ---------------------------------------------------------------- Checker: every claim verified in code
def claim(text, eids=("E-008",), quote="managing and monitoring 1,150 routers and switches across 310 branches", rid="R-001"):
    return Claim(id="C-001", requirement_id=rid, text=text, evidence_ids=eids, quote=quote)


EXP = "The bidder should have experience managing at least 900 network devices across branches"


def checked(c, rets=None, blocked=()):
    return check(CheckRequest(requirements=(req(1, EXP),), retrievals=rets or (ret(1, "E-008", "E-009"),),
                              draft=Draft(claims=(c,)), blocked_ids=blocked))


def by_check(rep):
    return {r.check: r for r in rep.results if r.target_id == "C-001"}


def test_honest_claim_passes_everything():
    rep = checked(claim("Northwind managed and monitored 1,150 routers and switches across 310 branches for Client-A."))
    assert rep.failing_claims == () and all(r.passed for r in rep.results)


def test_planted_led_instead_of_supported_is_caught():
    c = claim("Northwind led Client-B's onsite NOC covering 960 network devices.", eids=("E-009",),
              quote="Northwind has supported Client-B with an onsite NOC covering 960 network devices")
    rep = checked(c)
    assert "C-001" in rep.failing_claims and not by_check(rep)["overclaim"].passed and "led" in by_check(rep)["overclaim"].detail


def test_invented_number_is_caught():
    rep = checked(claim("Northwind managed 2,500 routers and switches across 310 branches."))
    assert not by_check(rep)["numbers"].passed and "2500" in by_check(rep)["numbers"].detail


def test_number_from_the_requirement_itself_is_allowed():
    rep = checked(claim("Northwind exceeds the 900 device requirement: 1,150 routers and switches across 310 branches."))
    assert by_check(rep)["numbers"].passed


def test_fake_quote_is_caught():
    rep = checked(claim("Northwind managed 1,150 routers.", quote="Northwind is the largest NOC provider in India"))
    assert not by_check(rep)["quote"].passed


def test_citing_evidence_not_found_for_this_requirement_is_caught():
    rep = checked(claim("Northwind managed 1,150 routers.", eids=("E-029",)))
    assert not by_check(rep)["citation"].passed


def test_citing_blocked_evidence_is_caught():
    c = claim("Northwind managed 1,420 remote network devices.", eids=("E-010",),
              quote="managing 1,420 remote network devices")
    rep = checked(c, rets=(ret(1, "E-010"),), blocked=("E-010",))
    assert not by_check(rep)["blocked_source"].passed


def test_coverage_finds_silent_misses():
    rep = check(CheckRequest(requirements=(req(1, EXP), req(2, BLACKLIST), req(3, "Note:")), retrievals=(),
                             draft=Draft(gaps=(Gap(requirement_id="R-001", reason="no_evidence"),))))
    assert rep.silent_misses == ("R-002",)                      # R-003 is a fragment, not a requirement


def test_checker_through_run_part():
    res, _ = run_part("checker", check, CheckRequest(requirements=(), retrievals=(), draft=Draft()), CheckReport)
    assert res.ok and res.value.silent_misses == ()


def test_evidence_records_used_by_tests_are_real():
    assert "supported Client-B" in EV["E-009"].text and EV["E-010"].confidentiality == "restricted"


def test_scope_duties_get_a_compliance_statement_but_named_standards_stay_gaps(monkeypatch):
    monkeypatch.setenv("BIDWIT_LLM", "off")
    duty = "The bidder shall monitor all branch links and raise tickets with the service provider"
    reqs = (req(1, duty, cat="technical", pf=False), req(2, ISO, cat="technical", pf=False), req(3, TURNOVER))
    rets = (ret(1, "E-029", score=1.0), ret(2, "E-003", unc=("iso 27001",)), ret(3, "E-001"))
    d = write(WriteRequest(requirements=reqs, retrievals=rets))
    assert [k.requirement_id for k in d.confirmations] == ["R-001"]
    assert {g.requirement_id: g.reason for g in d.gaps} == {"R-002": "missing_terms", "R-003": "ai_unavailable"}
    rep = check(CheckRequest(requirements=reqs, retrievals=rets, draft=d))
    assert rep.silent_misses == ()
