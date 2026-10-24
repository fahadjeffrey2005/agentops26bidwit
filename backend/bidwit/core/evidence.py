"""Shared rule for 'is this requirement backed by company evidence?'. Used by the Judge and the Writer,
so they can never disagree about it."""
from __future__ import annotations

from .contracts import EvidenceHit, Gap, Requirement, Retrieval

STRONG_KEYWORD = 4.0          # BM25 score of a hit that counts as real support
STRONG_MEANING = 0.70         # cosine similarity that counts as real support (hybrid mode)
MIN_WORDS = 6                 # shorter units ("Note:", signature lines) are not criteria; a human still sees them


def is_criterion(text: str) -> bool:
    """Real criteria only: not a fragment ('Note:', signature lines) and not a title that introduces a list."""
    t = text.strip()
    return len(t.split()) >= MIN_WORDS and not t.endswith((":", "-"))


def strong(hit: EvidenceHit) -> bool:
    return hit.keyword_score >= STRONG_KEYWORD or (hit.meaning_score is not None and hit.meaning_score >= STRONG_MEANING)


def evidence_gap(req: Requirement, ret: Retrieval | None) -> Gap | None:
    """Why this requirement is not backed by evidence, or None if it is."""
    if ret is None or not ret.hits:
        return Gap(requirement_id=req.id, reason="no_evidence", detail="no company evidence found")
    if ret.uncovered_terms:
        return Gap(requirement_id=req.id, reason="missing_terms",
                   detail=f"no valid evidence for: {', '.join(ret.uncovered_terms)}"[:300])
    if not any(strong(h) for h in ret.hits):
        best = ret.hits[0]
        return Gap(requirement_id=req.id, reason="no_evidence",
                   detail=f"only weak matches (best {best.evidence.id}, keyword score {best.keyword_score})"[:300])
    return None
