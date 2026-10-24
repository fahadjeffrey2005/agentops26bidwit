"""Shared helpers for Writer/Checker tests: real evidence records and a fake Groq server."""
import json
from pathlib import Path

import httpx

from bidwit.core.contracts import Evidence, EvidenceHit, Requirement, Retrieval
from bidwit.core.llm import LLMClient, parse_chain

DATA = Path(__file__).resolve().parents[2] / "data" / "kb" / "evidence.json"
EV = {e["id"]: Evidence(**e) for e in json.loads(DATA.read_text())}


def req(i, text, cat="eligibility", pf=True):
    return Requirement(id=f"R-{i:03d}", text=text, page=1, category=cat, pass_fail=pf)


def ret(i, *eids, score=12.0, unc=()):
    return Retrieval(clause_id=f"R-{i:03d}", uncovered_terms=unc,
                     hits=tuple(EvidenceHit(evidence=EV[e], rank=n, keyword_score=score) for n, e in enumerate(eids, 1)))


def fake_client(answer_fn, seen, tmp_path):
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        items = json.loads(body["messages"][1]["content"])
        seen.append(items)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer_fn(items))}}]})
    return LLMClient(parse_chain("groq:m1", httpx.MockTransport(handler)), cache_dir=tmp_path, max_calls=50)
