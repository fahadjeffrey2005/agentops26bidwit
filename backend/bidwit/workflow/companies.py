"""The bidding companies whose evidence can be searched. One folder per company under data/kb/.

data/kb/companies.json lists them; each entry points at that company's evidence file. A company id is
never used as a path: it is looked up in that list, so a bad id can't reach another folder.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

DEFAULT = "northwind"


@lru_cache(maxsize=8)
def _load(data_dir: str) -> list[dict]:
    try:
        rows = json.loads((Path(data_dir) / "kb" / "companies.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("evidence"), str)]



def companies(data_dir: Path) -> list[dict]:
    return list(_load(str(data_dir)))


def find(data_dir: Path, company: str | None) -> dict | None:
    wanted = company or DEFAULT
    return next((c for c in _load(str(data_dir)) if c["id"] == wanted), None)


def evidence_file(data_dir: Path, company: str | None) -> str:
    """The evidence file for this company. Falls back to the old single-library path."""
    c = find(data_dir, company)
    if c is None:
        return str(Path(data_dir) / "kb" / "evidence.json")
    return str(Path(data_dir) / "kb" / c["evidence"])


def profile(data_dir: Path, company: str, today: date) -> dict | None:
    """What this company can prove, grouped for the picker screen. Restricted text is never included."""
    c = find(data_dir, company)
    if c is None:
        return None
    try:
        rows = json.loads(Path(evidence_file(data_dir, company)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    iso = today.isoformat()
    docs = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        restricted = r.get("confidentiality") == "restricted"
        expired = bool(r.get("expires_on")) and str(r["expires_on"]) < iso
        text = None if restricted else r.get("text")
        kind = ("certificate" if "cert" in str(r.get("doc_id")) else
                "case study" if "case_study" in str(r.get("doc_id")) or "contract" in str(r.get("doc_id")) else
                "people" if "profile_" in str(r.get("doc_id")) or "staff" in str(r.get("doc_id")) else
                "policy" if "policy" in str(r.get("doc_id")) or "declaration" in str(r.get("doc_id")) else "company")
        docs.append({k: r.get(k) for k in ("id", "title", "client", "confidentiality", "date", "expires_on")} |
                    {"text": text, "kind": kind, "usable": not restricted and not expired,
                     "blocked_reason": "restricted" if restricted else ("expired" if expired else "")})
    return {**{k: c.get(k) for k in ("id", "name", "city", "founded", "blurb")}, "facts": c.get("facts") or [],
            "documents": docs,
            "counts": {"total": len(docs), "usable": sum(d["usable"] for d in docs),
                       "blocked": sum(not d["usable"] for d in docs),
                       **{k: sum(d["kind"] == k for d in docs) for k in ("certificate", "case study", "people", "policy", "company")}}}
