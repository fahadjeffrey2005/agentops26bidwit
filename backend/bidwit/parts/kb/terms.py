"""Tokens for keyword search, and 'required terms' a matching piece of evidence must contain.

Required terms are things a requirement can't be met without: a standard number (ISO 27001),
a named certification (CCNP), 24x7 operation, a data-centre tier. Evidence that lacks one is
reported with `missing_terms`, never silently treated as a match.
"""
from __future__ import annotations

import re
import unicodedata

STOP = frozenset("""a an and are as at be been by can for from has have in is it its of on or shall should
the their this to was were will with within which who must any all per such than that these those""".split())

CERTS = ("ccna", "ccnp", "ccie", "pmp", "itil", "cissp", "cisa", "cism", "ceh", "prince2", "togaf", "rhce", "mcse")
ISO_NUM = re.compile(r"\b(?:iso|iec)\b[\s/:\-]*(?:iec\b[\s/:\-]*)?(\d{4,5})(?:-\d)?")
ISO_LIST = re.compile(r"\b(?:iso|iec)\b[\s/:\-]*(?:iec\b[\s/:\-]*)?\d{4,5}(?:-\d)?(?:\s*[:/]\s*\d{4})?((?:\s*(?:/|,|and|or)\s*\d{4,5}(?:-\d)?)+)")
H24 = re.compile(r"\b24\s*[x*/\u00d7]\s*7(?![0-9])|round[\s-]the[\s-]clock")   # 24x7 24*7 24/7 24\u00d77 24x7x365
TIER = re.compile(r"\btier[\s-]*(iii|iv|3|4)\b")
SYNONYMS = {"msme": ("msme", "udyam"), "24x7": ("24x7", "24/7", "24*7", "24 x 7", "round-the-clock", "round the clock")}


def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def tokens(text: str) -> list[str]:
    """Lowercase words and numbers; '24x7' stays one token; simple plural folding (links -> link)."""
    t = H24.sub(" 24x7 ", norm(text))
    out = []
    for w in re.findall(r"[a-z0-9]+", t):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss") and not w.isdigit():
            w = w[:-1]
        out.append(w)
    return out


def required_terms(text: str) -> tuple[str, ...]:
    t = norm(text)
    found: list[str] = []
    for m in ISO_NUM.finditer(t):
        found.append(f"iso {m.group(1)}")
    for m in ISO_LIST.finditer(t):                      # "ISO 9001/20000 and 27001"
        found += [f"iso {n}" for n in re.findall(r"\d{4,5}", m.group(1))]
    found += [c for c in CERTS if re.search(rf"\b{c}\b", t)]
    if H24.search(t):
        found.append("24x7")
    if m := TIER.search(t):
        found.append(f"tier {m.group(1).replace('iii', '3').replace('iv', '4')}")
    if re.search(r"\bmsme\b", t):
        found.append("msme")
    return tuple(dict.fromkeys(found))                  # unique, in order


def has_term(evidence_text: str, term: str) -> bool:
    t = norm(evidence_text)
    if term.startswith("iso "):
        num = term[4:]
        return any(m.group(1) == num for m in ISO_NUM.finditer(t)) or any(
            num in re.findall(r"\d{4,5}", m.group(1)) for m in ISO_LIST.finditer(t))
    if term.startswith("tier "):
        m = TIER.search(t)
        return bool(m) and m.group(1).replace("iii", "3").replace("iv", "4") == term[5:]
    if term in SYNONYMS:
        return any(s in t for s in SYNONYMS[term]) or (term == "24x7" and bool(H24.search(t)))
    return bool(re.search(rf"\b{re.escape(term)}\b", t))
