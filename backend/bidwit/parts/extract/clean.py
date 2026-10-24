"""Text cleaning. Pure functions: page data in, cleaned lines out. No file or network access."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

EDGE_ZONE = 0.09            # top/bottom share of the page where headers/footers live
REPEAT_SHARE = 0.4          # a line on more than this share of pages is a header/footer
PAGE_NO = re.compile(r"^\s*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.I)
CONTROL = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\ufeff]")


@dataclass(frozen=True)
class Line:
    page: int
    text: str
    bold: bool
    x0: float
    top: float = 0.0


def normalize(text: str) -> str:
    """Unicode NFKC (ligatures like 'fi' become plain letters), soft-hyphen and pdfium hyphen marks,
    invisible/bidi control characters removed, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\ufffe", "-").replace("\u00ad", "-")
    t = CONTROL.sub("", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def _signature(text: str) -> str:
    """Same header on every page, different page numbers -> same signature."""
    return re.sub(r"\d+", "#", normalize(text).lower())


def find_repeated(pages: list[dict]) -> set[str]:
    """Signatures of lines that sit in the top/bottom zone on many pages."""
    if len(pages) < 3:
        return set()
    seen: Counter[str] = Counter()
    for p in pages:
        h = p["height"] or 1.0
        edge = {_signature(ln["text"]) for ln in p["lines"]
                if ln["top"] < h * EDGE_ZONE or ln["bottom"] > h * (1 - EDGE_ZONE)}
        seen.update(edge)
    return {sig for sig, n in seen.items() if n / len(pages) > REPEAT_SHARE}


def clean_pages(pages: list[dict]) -> tuple[list[Line], list[str]]:
    """Returns (body lines in reading order, removed header/footer lines)."""
    repeated = find_repeated(pages)
    body: list[Line] = []
    removed: dict[str, None] = {}
    for p in pages:
        h = p["height"] or 1.0
        for ln in p["lines"]:
            text = normalize(ln["text"])
            if not text:
                continue
            in_edge = ln["top"] < h * EDGE_ZONE or ln["bottom"] > h * (1 - EDGE_ZONE)
            if in_edge and (_signature(text) in repeated or PAGE_NO.match(text)):
                removed.setdefault(text, None)
                continue
            body.append(Line(page=p["page"], text=text, bold=bool(ln["bold"]), x0=float(ln["x0"]), top=float(ln["top"])))
    return body, list(removed)


def join_lines(parts: list[str]) -> str:
    """Join wrapped lines; repair words split by a hyphen at the line end ('con-' + 'solidated')."""
    out = ""
    for part in parts:
        if not out:
            out = part
        elif re.search(r"[a-z]-$", out) and re.match(r"^[a-z]", part):
            out = out[:-1] + part
        else:
            out = f"{out} {part}"
    return out.strip()
