"""Part 2: tender PDF -> clauses with page references.

    run(ExtractRequest) -> ExtractResult        (raises Rejected for unsafe or unreadable files)

Steps: safety gate (pypdf, own process) -> read pages (pdfplumber, own process, time limit)
-> clean (headers/footers, unicode, hyphens) -> segment (clauses, sub-items, table rows).
Nothing is filtered: every visible word ends up in a clause or in `removed_lines`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import Field

from bidwit.core.contracts import Clause, ExtractResult, PageNote, Rejected, Source, Strict
from bidwit.core.progress import step

from . import runner
from .clean import clean_pages, normalize
from .segment import segment

PART = "extract"
SCANNED_IMAGE_COVER = 0.5
SCANNED_MAX_CHARS = 60


class ExtractRequest(Strict):
    path: str = Field(min_length=1)
    max_mb: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=500, ge=1, le=2000)


def run(req: ExtractRequest) -> ExtractResult:
    path = Path(req.path)
    if not path.is_file():
        raise Rejected("file not found")
    size = path.stat().st_size
    if size > req.max_mb * 1024 * 1024:
        raise Rejected(f"file is larger than {req.max_mb} MB")
    if size == 0:
        raise Rejected("file is empty")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    step("extract", f"safety check of {path.name} ({size / 1048576:.1f} MB)")
    n_pages = runner.check(path, req.max_pages)
    step("extract", f"reading {n_pages} pages")
    pages = runner.read(path, n_pages)
    step("extract", "cleaning headers/footers and splitting into clauses")

    notes: list[PageNote] = []
    for p in pages:
        if p["error"]:
            notes.append(PageNote(page=p["page"], flag="unreadable", detail=f"page could not be read ({p['error']}); check it by hand"))
        if p["hidden"].strip():
            sample = normalize(p["hidden"])[:300]
            notes.append(PageNote(page=p["page"], flag="hidden_text",
                                  detail=f"invisible text removed (white, tiny or off-page): \"{sample}\""))
    body, removed = clean_pages(pages)
    chars_on = {p["page"]: 0 for p in pages}
    for ln in body:
        chars_on[ln.page] += len(ln.text)
    for p in pages:
        visible = chars_on[p["page"]] + sum(len(" ".join(r)) for t in p["tables"] for r in t["rows"])
        if p["image_cover"] >= SCANNED_IMAGE_COVER and visible < SCANNED_MAX_CHARS:
            notes.append(PageNote(page=p["page"], flag="scanned", detail="page is a scanned image with no text layer; read it by hand"))

    tables = [{**t, "page": p["page"]} for p in pages for t in p["tables"]]
    drafts = segment(body, tables)
    ids: dict[int, str] = {}
    clauses: list[Clause] = []
    for i, d in enumerate(drafts, 1):
        cid = f"R-{i:03d}"
        ids.setdefault(d["key"], cid)
        clauses.append(Clause(
            id=cid, kind=d["kind"], text=d["text"],
            source=Source(file=path.name[:200], page=d["page"], end_page=d["end_page"], clause_no=d["clause_no"]),
            section=d["section"], parent_id=ids.get(d["parent_key"]) if d["parent_key"] is not None else None,
        ))
    step("extract", f"done: {len(clauses)} units, {len(notes)} flags for Gate A")
    if len(clauses) > 9999:
        raise Rejected("more than 9999 text units; split the tender")
    notes.sort(key=lambda n: (n.page, n.flag))
    return ExtractResult(file=path.name[:200], sha256=digest, pages=n_pages, clauses=tuple(clauses),
                         notes=tuple(notes), removed_lines=tuple(removed))
