"""Measure evidence search on the 17-question answer key, keyword-only vs hybrid (Gemini).

    export GEMINI_API_KEY=...        # in your terminal only; never in code, chat or git
    python scripts/check_kb.py

Needs network for the hybrid run. Embeddings are cached in runs/cache/ so a re-run costs no API calls.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bidwit.parts.kb import Query, RetrieveRequest, run  # noqa: E402

gold = json.loads((ROOT / "tests" / "kb" / "retrieval_gold.json").read_text())
queries = tuple(Query(clause_id=f"R-{i + 1:03d}", text=g["text"]) for i, g in enumerate(gold))
for meaning in (False, True):
    res = run(RetrieveRequest(evidence_path=str(ROOT.parent / "data" / "kb" / "evidence.json"), today=date.today(),
                              queries=queries, meaning=meaning, cache_dir=str(ROOT.parent / "runs" / "cache")))
    first = sum(r.hits[0].evidence.id in g["expected_any"] for g, r in zip(gold, res.results) if r.hits)
    anyk = sum(any(h.evidence.id in g["expected_any"] for h in r.hits) for g, r in zip(gold, res.results))
    print(f"{'hybrid ' if meaning else 'keyword'} mode={res.mode:<7} first={first}/{len(gold)} in-results={anyk}/{len(gold)}"
          f"  blocked={[b.id for b in res.blocked]} {res.mode_reason}")
    for g, r in zip(gold, res.results):
        if not r.hits or r.hits[0].evidence.id not in g["expected_any"]:
            print(f"    not first: {g['label'][:45]:<45} expected {g['expected_any']} got {[h.evidence.id for h in r.hits]}")
