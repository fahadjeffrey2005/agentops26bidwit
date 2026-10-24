"""Part 5c: the Checker. Verifies every claim in code (no AI). Nothing passes on the Writer's word.

    run(CheckRequest) -> CheckReport

Per claim:
  citation        every cited evidence id is among the evidence found for that requirement
  blocked_source  no cited evidence is restricted or expired
  quote           the quote really appears in a cited evidence text (fuzzy match >= 90, after normalising)
  numbers         every number in the claim appears in the cited evidence or in the requirement itself
  overclaim       no inflated word (led, guarantee, always, best, ...) that the cited evidence doesn't contain
Coverage: every requirement the Writer was given ends as a claim, a gap or a compliance statement; anything else is a silent miss.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from bidwit.core.contracts import CheckReport, CheckResult, Draft, EvidenceId, Requirement, Retrieval, Strict
from bidwit.core.evidence import is_criterion

PART = "checker"
QUOTE_MIN = 90
OVERCLAIM = ("led", "lead", "leading", "guarantee", "guaranteed", "guarantees", "always", "never", "best",
             "world-class", "unparalleled", "unmatched", "largest", "fully", "completely", "100%", "zero downtime")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
QUOTES = str.maketrans({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'})


class CheckRequest(Strict):
    requirements: tuple[Requirement, ...]
    retrievals: tuple[Retrieval, ...]
    draft: Draft
    blocked_ids: tuple[EvidenceId, ...] = ()


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t).lower()
    t = t.translate(QUOTES)                       # curly quotes -> straight
    return re.sub(r"\s+", " ", t).strip()


def _numbers(t: str) -> set[str]:
    out = set()
    for n in NUMBER.findall(t):
        n = n.rstrip("%").replace(",", "")
        n = n.rstrip(".")
        if n:
            out.add(n.lstrip("0") or "0")
    return out


def _words(t: str) -> set[str]:
    return set(re.findall(r"[a-z0-9%-]+", _norm(t))) | ({"zero downtime"} if "zero downtime" in _norm(t) else set())


def run(req: CheckRequest) -> CheckReport:
    rets = {r.clause_id: r for r in req.retrievals}
    reqs = {r.id: r for r in req.requirements}
    blocked = set(req.blocked_ids)
    results: list[CheckResult] = []
    failing: list[str] = []

    for c in req.draft.claims:
        hits = {h.evidence.id: h.evidence for h in (rets[c.requirement_id].hits if c.requirement_id in rets else ())}
        cited = [hits[e] for e in c.evidence_ids if e in hits]
        checks = []
        unknown = [e for e in c.evidence_ids if e not in hits]
        checks.append(CheckResult(target_id=c.id, check="citation", passed=not unknown and c.requirement_id in reqs,
                                  detail=f"cites evidence not found for this requirement: {unknown}" if unknown else ""))
        bad = [e for e in c.evidence_ids if e in blocked]
        checks.append(CheckResult(target_id=c.id, check="blocked_source", passed=not bad,
                                  detail=f"cites blocked evidence {bad}" if bad else ""))
        best = max((fuzz.partial_ratio(_norm(c.quote), _norm(e.text)) for e in cited), default=0)
        checks.append(CheckResult(target_id=c.id, check="quote", passed=best >= QUOTE_MIN,
                                  detail="" if best >= QUOTE_MIN else f"quote not found in cited evidence (best match {best:.0f}%)"))
        allowed = set().union(*[_numbers(e.text) for e in cited], _numbers(reqs[c.requirement_id].text) if c.requirement_id in reqs else set())
        extra = sorted(_numbers(c.text) - allowed)
        checks.append(CheckResult(target_id=c.id, check="numbers", passed=not extra,
                                  detail=f"numbers not in the evidence: {extra}"[:300] if extra else ""))
        ev_words = set().union(*[_words(e.text) for e in cited]) if cited else set()
        inflated = [w for w in OVERCLAIM if w in _words(c.text) and w not in ev_words]
        checks.append(CheckResult(target_id=c.id, check="overclaim", passed=not inflated,
                                  detail=f"goes beyond the evidence: {inflated}" if inflated else ""))
        results += checks
        if not all(x.passed for x in checks):
            failing.append(c.id)

    answered = ({c.requirement_id for c in req.draft.claims} | {g.requirement_id for g in req.draft.gaps}
                | {k.requirement_id for k in req.draft.confirmations})
    expected = [r for r in req.requirements if is_criterion(r.text) and r.category != "other"]
    silent = [r.id for r in expected if r.id not in answered]
    for r in expected:
        results.append(CheckResult(target_id=r.id, check="coverage", passed=r.id in answered,
                                   detail="" if r.id in answered else "requirement has neither an answer nor a flagged gap"))
    return CheckReport(results=tuple(results), failing_claims=tuple(failing), silent_misses=tuple(silent))
