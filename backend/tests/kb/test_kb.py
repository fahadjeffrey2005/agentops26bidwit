import json
from datetime import date
from pathlib import Path

import pytest

import bidwit.parts.kb as kb
from bidwit.core.contracts import Rejected, RetrieveResult
from bidwit.core.isolation import run_part
from bidwit.parts.kb import Query, RetrieveRequest, run
from bidwit.parts.kb.embed import CachedEmbedder, EmbedError
from bidwit.parts.kb.terms import has_term, required_terms, tokens

DATA = Path(__file__).resolve().parents[3] / "data" / "kb" / "evidence.json"
GOLD = json.loads((Path(__file__).parent / "retrieval_gold.json").read_text())
TODAY = date(2026, 10, 24)
RESTRICTED_TEXT = "1,420 remote network devices"          # only in E-010 (restricted)


def req(*texts, today=TODAY, meaning=False, k=3, cache_dir=None, path=DATA):
    return RetrieveRequest(evidence_path=str(path), today=today, k=k, meaning=meaning, cache_dir=cache_dir,
                           queries=tuple(Query(clause_id=f"R-{i + 1:03d}", text=t) for i, t in enumerate(texts)))


class FakeEmbedder:
    """Deterministic stand-in for Gemini: a few 'concepts' map to fixed directions; records every text it sees."""
    name, dim = "fake/8", 8
    CONCEPTS = [("xyzzy", "transition", "takeover"), ("cabling", "fibre"), ("billing",), ("ipv6",)]

    def __init__(self):
        self.seen: list[str] = []
        self.calls = 0

    def embed(self, texts, task):
        self.calls += 1
        if task == "RETRIEVAL_DOCUMENT":
            self.seen += texts
        out = []
        for t in texts:
            low = t.lower()
            v = [1.0 if any(w in low for w in c) else 0.0 for c in self.CONCEPTS] + [0.0] * 3 + [0.01]
            out.append(v)
        return out


@pytest.fixture
def fake(monkeypatch):
    f = FakeEmbedder()
    monkeypatch.setattr(kb, "make_embedder", lambda cache_dir: f)
    return f


# ---------------------------------------------------------------- the two locks
def test_restricted_record_is_never_indexed_never_embedded_never_returned(fake):
    res = run(req("Experience managing 1,420 remote network devices at 415 branches and 790 links", meaning=True))
    assert ("E-010", "restricted") in [(b.id, b.reason) for b in res.blocked]
    assert not any(h.evidence.id == "E-010" for r in res.results for h in r.hits)
    e010 = next(e for e in json.loads(DATA.read_text()) if e["id"] == "E-010")
    assert not any(RESTRICTED_TEXT in t or e010["text"] in t for t in fake.seen)   # document never sent to the model
    assert len(fake.seen) == 29
    assert res.indexed == 29


def test_expired_record_blocked_today_but_usable_before_expiry():
    q = "ISO/IEC 27001:2013 certified 24x7 NOC information security"
    now = run(req(q))
    assert ("E-005", "expired") in [(b.id, b.reason) for b in now.blocked]
    assert not any(h.evidence.id == "E-005" for h in now.results[0].hits)
    assert "iso 27001" in now.results[0].uncovered_terms                # reported as a gap, not hidden
    before = run(req(q, today=date(2025, 1, 1)))
    assert before.results[0].hits[0].evidence.id == "E-005"
    assert "iso 27001" not in before.results[0].uncovered_terms


# ---------------------------------------------------------------- required terms
def test_required_terms_on_real_tender_wording():
    assert required_terms("ISO 9001/ISO 20000 and ISO 27001:2013 certified 24" + chr(0xD7) + "7 NOC") == ("iso 9001", "iso 20000", "iso 27001", "24x7")
    assert required_terms("Degree Engineer with CCNP and PMP") == ("ccnp", "pmp")
    assert has_term("NOC runs 24x7x365 with NMS", "24x7") and has_term("ISO/IEC 20000-1:2018", "iso 20000")
    assert has_term("registered under the MSME Udyam scheme", "msme") and not has_term("ISO 9001:2015", "iso 27001")


def test_uncovered_term_is_searched_directly_instead_of_reported_as_false_gap():
    res = run(req("The bidder must have following valid Certifications: ISO 9001/ISO 20000 and ISO 27001:2013 certified 24*7 NOC"))
    r = res.results[0]
    assert r.uncovered_terms == ("iso 27001",)                         # 24x7 found in the KB, 27001 truly missing
    assert any(h.found_by == "required_term" and "24x7" not in h.missing_terms for h in r.hits)


def test_tokens():
    assert tokens("The Bidder's Links: 24*7 NOC") == ["bidder", "link", "24x7", "noc"]


# ---------------------------------------------------------------- answer key
def test_keyword_mode_finds_expected_evidence():
    res = run(req(*[g["text"] for g in GOLD]))
    in_results = sum(any(h.evidence.id in g["expected_any"] for h in r.hits) for g, r in zip(GOLD, res.results))
    first = sum(r.hits[0].evidence.id in g["expected_any"] for g, r in zip(GOLD, res.results))
    assert in_results == len(GOLD) and first >= len(GOLD) - 1, (in_results, first)


# ---------------------------------------------------------------- hybrid, fallback, cache
def test_hybrid_mode_uses_meaning_vectors(fake):
    res = run(req("xyzzy", meaning=True))            # no shared keywords: only the meaning vector can find E-030
    assert res.mode == "hybrid" and res.results[0].hits[0].evidence.id == "E-030"
    assert res.results[0].hits[0].meaning_score is not None


def test_gemini_failure_falls_back_to_keyword_with_reason(monkeypatch):
    def broken(cache_dir):
        raise EmbedError("Gemini embedding call failed (ResourceExhausted)")
    monkeypatch.setattr(kb, "make_embedder", broken)
    res = run(req("Bidder should not be blacklisted", meaning=True))
    assert res.mode == "keyword" and "ResourceExhausted" in res.mode_reason
    assert res.results[0].hits[0].evidence.id == "E-029"


def test_missing_api_key_falls_back(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res = run(req("Bidder should not be blacklisted", meaning=True))
    assert res.mode == "keyword" and "GEMINI_API_KEY is not set" in res.mode_reason


def test_cache_avoids_repeat_calls_and_ignores_bad_entries(tmp_path):
    inner = FakeEmbedder()
    c = CachedEmbedder(inner, tmp_path / "e.json")
    c.embed(["a", "b"], "RETRIEVAL_DOCUMENT")
    c2 = CachedEmbedder(inner, tmp_path / "e.json")
    c2.embed(["a", "b"], "RETRIEVAL_DOCUMENT")
    assert inner.calls == 1                                          # second time from disk
    data = json.loads((tmp_path / "e.json").read_text())
    data[next(iter(data))] = [float("nan")] * 3                     # tampered entry: wrong size, not finite
    (tmp_path / "e.json").write_text(json.dumps(data))
    CachedEmbedder(inner, tmp_path / "e.json").embed(["a", "b"], "RETRIEVAL_DOCUMENT")
    assert inner.calls == 2                                          # bad entry recomputed, not trusted
    (tmp_path / "e.json").write_text("{not json")
    assert CachedEmbedder(inner, tmp_path / "e.json").cache == {}    # corrupt file ignored
    CachedEmbedder(inner, tmp_path / "e.json").embed(["confidential phrase here"], "RETRIEVAL_DOCUMENT")
    assert "confidential phrase" not in (tmp_path / "e.json").read_text()   # texts are hashed, not stored


# ---------------------------------------------------------------- bad evidence files
@pytest.mark.parametrize("content,msg", [
    ("not json", "unreadable"),
    ("{}", "non-empty JSON list"),
    ("[]", "non-empty JSON list"),
    (json.dumps([{"id": "E-001"}]), "record invalid"),
    (json.dumps([{"id": "E-1", "doc_id": "x", "title": "t", "text": "x", "confidentiality": "public", "date": "2024-01-01"}]), "record invalid"),
    (json.dumps([{"id": "E-001", "doc_id": "x", "title": "t", "text": "x", "confidentiality": "secret", "date": "2024-01-01"}]), "record invalid"),
    (json.dumps([{"id": "E-001", "doc_id": "x", "title": "t", "text": "x", "confidentiality": "public", "date": "2024-13-01"}]), "record invalid"),
    (json.dumps([{"id": "E-001", "doc_id": "x", "title": "t", "text": "x", "confidentiality": "public", "date": "2024-01-01", "extra": 1}]), "record invalid"),
    (json.dumps([{"id": "E-001", "doc_id": "x", "title": "t", "text": "x", "confidentiality": "public", "date": "2024-01-01"}] * 2), "duplicate ids"),
])
def test_bad_evidence_files_are_refused(tmp_path, content, msg):
    p = tmp_path / "ev.json"
    p.write_text(content)
    with pytest.raises(Rejected, match=msg):
        run(req("anything", path=p))


def test_refusal_through_run_part_is_not_a_crash(tmp_path):
    p = tmp_path / "ev.json"
    p.write_text("[]")
    res, _ = run_part("kb", run, req("x", path=p), RetrieveResult)
    assert not res.ok and res.error.kind == "rejected"


def test_query_with_no_known_words_returns_no_hits_not_an_error():
    res = run(req("qqqq zzzz"))
    assert res.results[0].hits == ()


def test_same_input_same_output():
    assert run(req(*[g["text"] for g in GOLD[:5]])) == run(req(*[g["text"] for g in GOLD[:5]]))
