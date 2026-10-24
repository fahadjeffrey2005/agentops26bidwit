"""Part 3: company evidence search (Qdrant, local mode, in memory).

    run(RetrieveRequest) -> RetrieveResult

1. Load and validate the evidence file.
2. Lock 1: restricted records are dropped before indexing (never stored, never sent to Gemini).
3. Index keyword vectors (BM25) and, if available, meaning vectors (Gemini). If Gemini fails,
   the run continues keyword-only and `mode_reason` says why.
4. Lock 2: every search filters out records whose expiry date is before `today`.
5. For each clause: top-k evidence, fused ranking, and required terms the evidence lacks.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import Field, ValidationError
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from bidwit.core.progress import step
from bidwit.core.contracts import (BlockedDoc, ClauseId, Evidence, EvidenceHit, Rejected, Retrieval,
                                   RetrieveResult, Strict)

from .bm25 import BM25
from .embed import CachedEmbedder, EmbedError, Embedder, GeminiEmbedder
from .terms import has_term, required_terms, tokens

PART = "kb"
COLLECTION = "evidence"
NO_EXPIRY = 99991231                    # stored for records without an expiry date
MAX_RECORDS = 5000


class Query(Strict):
    clause_id: ClauseId
    text: str = Field(min_length=1, max_length=6000)


class RetrieveRequest(Strict):
    evidence_path: str = Field(min_length=1)
    today: date
    queries: tuple[Query, ...]
    k: int = Field(default=3, ge=1, le=10)
    meaning: bool = True                               # False: keyword-only on purpose
    cache_dir: str | None = None                       # where Gemini vectors are cached


def make_embedder(cache_dir: str | None) -> Embedder:
    """Separate function so tests can swap in a fake embedder."""
    inner = GeminiEmbedder()
    return CachedEmbedder(inner, Path(cache_dir) / "embeddings.json") if cache_dir else inner


def load_evidence(path: Path) -> list[Evidence]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise Rejected(f"evidence file unreadable ({type(e).__name__})") from e
    if not isinstance(raw, list) or not raw:
        raise Rejected("evidence file must be a non-empty JSON list")
    if len(raw) > MAX_RECORDS:
        raise Rejected(f"evidence file has more than {MAX_RECORDS} records")
    try:
        records = [Evidence(**r) for r in raw]
    except (TypeError, ValidationError) as e:
        raise Rejected(f"evidence record invalid: {str(e).splitlines()[0][:150]}") from e
    ids = [r.id for r in records]
    if len(set(ids)) != len(ids):
        raise Rejected("evidence file has duplicate ids")
    return records


def _ymd(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def run(req: RetrieveRequest) -> RetrieveResult:
    records = load_evidence(Path(req.evidence_path))
    blocked: list[BlockedDoc] = []
    usable: list[Evidence] = []
    for r in records:
        if r.confidentiality == "restricted":                       # lock 1
            blocked.append(BlockedDoc(id=r.id, title=r.title, reason="restricted",
                                      detail="restricted document: never indexed, never sent to any model"))
        else:
            if r.expires_on is not None and r.expires_on < req.today:
                blocked.append(BlockedDoc(id=r.id, title=r.title, reason="expired",
                                          detail=f"expired on {r.expires_on.isoformat()}"))
            usable.append(r)                                        # expired ones are indexed; lock 2 filters them
    by_id = {r.id: r for r in usable}

    docs = [tokens(f"{r.title} {r.text}") for r in usable]
    bm25 = BM25(docs)

    mode, reason, emb, dense = "keyword", "meaning search switched off", None, None
    if req.meaning:
        try:
            step("kb", f"meaning vectors for {len(usable)} evidence records")
            emb = make_embedder(req.cache_dir)
            dense = emb.embed([f"{r.title}\n{r.text}" for r in usable], "RETRIEVAL_DOCUMENT")
            mode, reason = "hybrid", ""
        except EmbedError as e:
            mode, reason, emb, dense = "keyword", f"meaning search unavailable: {e}", None, None

    client = QdrantClient(":memory:")
    try:
        vectors = {"dense": qm.VectorParams(size=emb.dim, distance=qm.Distance.COSINE)} if dense else {}
        client.create_collection(COLLECTION, vectors_config=vectors,
                                 sparse_vectors_config={"bm25": qm.SparseVectorParams()})
        points = []
        for i, (r, d) in enumerate(zip(usable, docs)):
            idx, val = bm25.doc_vector(d)
            vec = {"bm25": qm.SparseVector(indices=idx, values=val)}
            if dense:
                vec["dense"] = dense[i]
            points.append(qm.PointStruct(id=i, vector=vec, payload={
                "eid": r.id, "expires": _ymd(r.expires_on) if r.expires_on else NO_EXPIRY,
                "confidentiality": r.confidentiality}))
        if points:
            client.upsert(COLLECTION, points)

        not_expired = qm.Filter(must=[qm.FieldCondition(key="expires", range=qm.Range(gte=_ymd(req.today))),
                                      qm.FieldCondition(key="confidentiality", match=qm.MatchAny(any=["public", "internal"]))])
        step("kb", f"searching {len(req.queries)} requirements")
        qvecs = []
        if dense and req.queries:
            try:
                qvecs = emb.embed([q.text for q in req.queries], "RETRIEVAL_QUERY")
            except EmbedError as e:                      # quota died mid-run: finish on keyword search
                mode, reason, dense = "keyword", f"meaning search unavailable: {e}", None
        results = []
        for qi, q in enumerate(req.queries):
            terms = required_terms(q.text)
            q_idx, q_val = bm25.query_vector(tokens(q.text))
            sparse_q = qm.SparseVector(indices=q_idx, values=q_val)
            if dense:
                found = client.query_points(COLLECTION, prefetch=[
                    qm.Prefetch(query=sparse_q, using="bm25", limit=20, filter=not_expired),
                    qm.Prefetch(query=qvecs[qi], using="dense", limit=20, filter=not_expired)],
                    query=qm.FusionQuery(fusion=qm.Fusion.RRF), limit=req.k, with_payload=True).points
            elif q_idx:
                found = client.query_points(COLLECTION, query=sparse_q, using="bm25", query_filter=not_expired,
                                            limit=req.k, with_payload=True).points
            else:
                found = []
            hits = []
            for rank, p in enumerate(found, 1):
                ev = by_id[p.payload["eid"]]
                i = usable.index(ev)
                d_idx, d_val = bm25.doc_vector(docs[i])
                kw = sum(v for t, v in zip(d_idx, d_val) if t in set(q_idx))
                ms = sum(a * b for a, b in zip(dense[i], qvecs[qi])) if dense else None
                hits.append(EvidenceHit(evidence=ev, rank=rank, keyword_score=round(kw, 4),
                                        meaning_score=round(ms, 4) if ms is not None else None,
                                        missing_terms=tuple(t for t in terms if not has_term(f"{ev.title} {ev.text}", t))))
            covered = {t for h in hits for t in terms if t not in h.missing_terms}
            for t in [t for t in terms if t not in covered]:     # look for each uncovered term directly
                live = [(i, r) for i, r in enumerate(usable) if (r.expires_on is None or r.expires_on >= req.today)
                        and r.id not in {h.evidence.id for h in hits} and has_term(f"{r.title} {r.text}", t)]
                if not live:
                    continue
                q_set = set(q_idx)
                def kw_of(i: int) -> float:
                    d_idx, d_val = bm25.doc_vector(docs[i])
                    return sum(v for x, v in zip(d_idx, d_val) if x in q_set)
                i, ev = max(live, key=lambda iv: kw_of(iv[0]))
                ms = sum(a * b for a, b in zip(dense[i], qvecs[qi])) if dense else None
                hits.append(EvidenceHit(evidence=ev, rank=len(hits) + 1, keyword_score=round(kw_of(i), 4),
                                        meaning_score=round(ms, 4) if ms is not None else None, found_by="required_term",
                                        missing_terms=tuple(x for x in terms if not has_term(f"{ev.title} {ev.text}", x))))
                covered |= {x for x in terms if has_term(f"{ev.title} {ev.text}", x)}
            results.append(Retrieval(clause_id=q.clause_id, required_terms=terms,
                                     uncovered_terms=tuple(t for t in terms if t not in covered), hits=tuple(hits)))
    finally:
        client.close()
    return RetrieveResult(mode=mode, mode_reason=reason[:300], indexed=len(usable),
                          blocked=tuple(blocked), results=tuple(results))
