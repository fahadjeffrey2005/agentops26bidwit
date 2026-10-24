"""BM25 as sparse vectors, so Qdrant can rank by keyword relevance.

Document weight per term = idf * tf*(k1+1) / (tf + k1*(1 - b + b*len/avglen)); the query vector
has weight 1 per term, so Qdrant's dot product equals the classic BM25 score.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter

K1, B = 1.2, 0.75


def term_id(token: str) -> int:
    """Stable 32-bit id per token (same on every machine and run)."""
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")


class BM25:
    def __init__(self, docs: list[list[str]]):
        self.n = len(docs)
        self.avg = (sum(map(len, docs)) / self.n) if self.n else 1.0
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        ids = {}
        for t in self.idf:                              # refuse silent hash collisions
            i = term_id(t)
            if i in ids and ids[i] != t:
                raise ValueError(f"token id collision: {ids[i]!r} / {t!r}")
            ids[i] = t

    def doc_vector(self, doc: list[str]) -> tuple[list[int], list[float]]:
        tf = Counter(doc)
        norm = K1 * (1 - B + B * len(doc) / self.avg)
        pairs = sorted((term_id(t), self.idf[t] * f * (K1 + 1) / (f + norm)) for t, f in tf.items() if t in self.idf)
        return [p[0] for p in pairs], [p[1] for p in pairs]

    def query_vector(self, query: list[str]) -> tuple[list[int], list[float]]:
        ids = sorted({term_id(t) for t in query if t in self.idf})
        return ids, [1.0] * len(ids)
