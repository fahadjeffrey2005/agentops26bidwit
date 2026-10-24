"""Turn cleaned lines and tables into clauses. Pure functions, no I/O.

Rule that matters most: no text is ever dropped. A line that does not start a new
unit is appended to the current one; text before the first clause becomes a paragraph;
table header rows are kept as units too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .clean import Line, join_lines, normalize

MAX_CLAUSE_CHARS = 6000
# 2.1  2.1.3  4.10.2.  1.g.4.   (letters allowed after the first level)
NUMBERED = re.compile(r"^(\d{1,2}(?:\.(?:\d{1,3}|[a-z])){1,4})\.?\s+(\S.*)$")
HEADING = re.compile(r"^(\d{1,2})\.?\s+([A-Z][^.]{2,80})$")                        # "3 Scope of Work"
# Annex / section headings need an identifier after the keyword ("Annexure - 2 - ...", "Section III", "Part B",
# "Form 3"), so sentences that merely start with "part of ...", "form, by ..." or "Schedule implemented ..." are not headings.
_DASHES = "".join(map(chr, (0x2013, 0x2014)))
PART_HEADING = re.compile(r"^(annexure|annex|appendix|schedule|section|chapter|part|form|volume)(?![a-z])[\s\-" + _DASHES + r":.]*"
                          r"(\d{1,3}|[ivxlc]{1,6}|[a-z])(?![a-z0-9])", re.I)
LABELS = frozenset({"note", "notes", "nb", "n.b", "remark", "remarks", "important", "please note", "example", "examples"})
# (a) (iv) (A) (1)   a) iv) A)   a. iv. A.      -- a dot or bracket must be followed by a space
SUBITEM = re.compile(r"^(\((?:[a-zA-Z]|[ivxIVX]{1,5}|\d{1,2})\)|(?:[a-zA-Z]|[ivxIVX]{1,5})[.)]|\d{1,2}\))\s+(\S.*)$")
LIST_NUM = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")                                   # "1. The bidder shall ..."
# bullets, including private-use glyphs from Symbol/Wingdings fonts that PDFs often contain
_BULLET_CODES = (0x2022, 0x2023, 0x2043, 0x2219, 0x25AA, 0x25AB, 0x25CF, 0x25E6, 0x25A0, 0x25A1, 0x27A2, 0x2794,
                 0x2713, 0x2714, 0xF0A7, 0xF0B7, 0xF0D8, 0xF076, 0xF0FC, 0xF0A8, 0xF0D2)   # last 7: Symbol/Wingdings
BULLET = re.compile("^(?:[" + re.escape("".join(map(chr, _BULLET_CODES))) + r"]\s*(\S.*)|[-*]\s+(\S.*))$")


def _tuple(num: str) -> tuple[int, ...]:
    return tuple(int(x) if x.isdigit() else ord(x) - 96 for x in num.split("."))


def plausible_next(prev: tuple[int, ...] | None, cand: tuple[int, ...]) -> bool:
    """Is `cand` a believable next clause number after `prev`? Stops '99.982 percent' at a line start
    from being read as clause 99.982. Numbering restarts at 1.1 / 1 are allowed (new section)."""
    if cand in {(1,), (1, 1)}:
        return True
    if prev is None:
        return cand[0] <= 3
    if cand <= prev:
        return False
    if cand[0] - prev[0] > 3:                          # a section may be skipped (missing, or on a scanned page)
        return False
    for i, (a, b) in enumerate(zip(prev, cand)):       # first differing level may only step forward a little
        if a != b:
            return b - a <= 3 and all(x <= 3 for x in cand[i + 1:])
    return len(cand) > len(prev) and all(x <= 3 for x in cand[len(prev):])   # deeper child of prev


@dataclass
class _Draft:
    kind: str
    clause_no: str | None
    page: int
    end_page: int
    section: str | None
    parent_key: int | None = None
    parts: list[str] = field(default_factory=list)

    def add(self, text: str, page: int) -> None:
        self.parts.append(text)
        self.end_page = page


def _is_heading_line(text: str, bold: bool) -> bool:
    return (bold or len(text) < 60) and not text.rstrip().endswith((".", ";", ",", ":"))


def _bold_title(text: str, bold: bool) -> bool:
    """Unnumbered bold title such as 'ELIGIBILITY CRITERIA (Documents to be Submitted Online)' or 'Termination Clause'."""
    t = text.strip()
    return (bold and 3 <= len(t) <= 90 and t[0].isupper() and not t.endswith((".", ";", ","))
            and t.rstrip(":").strip().lower() not in LABELS)


def split_long(text: str, limit: int = MAX_CLAUSE_CHARS) -> list[str]:
    """Split at the last sentence end (or space) before the limit; never cut a word, never drop text."""
    out = []
    while len(text) > limit:
        cut = max(text.rfind(". ", 0, limit), text.rfind("; ", 0, limit))
        cut = cut + 1 if cut > limit // 2 else text.rfind(" ", 0, limit)
        cut = cut if cut > 0 else limit
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


PARA_GAP = 1.8           # a vertical gap this many times the normal line spacing starts a new paragraph


def line_pitch(lines: list[Line]) -> float:
    """Typical distance between consecutive lines (median), used to spot blank-line paragraph breaks."""
    gaps = sorted(b.top - a.top for a, b in zip(lines, lines[1:]) if a.page == b.page and 4 < b.top - a.top < 40)
    return gaps[len(gaps) // 2] if gaps else 14.0


def segment(lines: list[Line], tables: list[dict]) -> list[dict]:
    """Returns drafts as dicts (ids are assigned by the caller, in order)."""
    pitch = line_pitch(lines)
    prev: Line | None = None
    drafts: list[_Draft] = []
    section: str | None = None
    last_num: tuple[int, ...] | None = None
    last_numbered_idx: int | None = None
    pending = sorted(tables, key=lambda t: (t["page"], t["top"]))   # tables wait for their place in reading order
    carry: dict = {"page": None, "header": None, "clean": False}     # header of the last table, for a direct continuation

    def flush_tables(page: int, top: float) -> None:
        while pending and (pending[0]["page"], pending[0]["top"]) < (page, top):
            drafts.extend(_table_rows(pending.pop(0), section, carry))

    def new(kind: str, no: str | None, text: str, ln: Line, parent: int | None = None) -> None:
        d = _Draft(kind, no, ln.page, ln.page, section, parent_key=parent)
        d.add(text, ln.page)
        drafts.append(d)

    for ln in lines:
        flush_tables(ln.page, ln.top)                   # tables above this line come first
        carry["clean"] = False                          # body text after a table: the next table is not its continuation
        gap_break = prev is not None and prev.page == ln.page and ln.top - prev.top > PARA_GAP * pitch
        prev = ln
        text = ln.text
        m_num = NUMBERED.match(text)
        m_head = HEADING.match(text)
        if m_num and plausible_next(last_num, _tuple(m_num.group(1))):
            last_num = _tuple(m_num.group(1))
            new("clause", m_num.group(1), m_num.group(2), ln)
            last_numbered_idx = len(drafts) - 1
        elif m_head and _is_heading_line(text, ln.bold) and plausible_next(last_num, (int(m_head.group(1)),)):
            last_num = (int(m_head.group(1)),)
            section = normalize(text)[:200]
            last_numbered_idx = None
            new("heading", m_head.group(1), m_head.group(2), ln)
        elif PART_HEADING.match(text) and len(text) <= 100 and not text.rstrip().endswith((";", ",")):
            section = normalize(text)[:200]               # new annex/section: numbering may restart
            last_num = None
            last_numbered_idx = None
            new("heading", None, text, ln)
        elif m := (SUBITEM.match(text) or LIST_NUM.match(text)):
            new("sub_item", m.group(1), m.group(2), ln, parent=last_numbered_idx)
        elif m := BULLET.match(text):
            new("sub_item", "-", m.group(1) or m.group(2), ln, parent=last_numbered_idx)
        elif _bold_title(text, ln.bold):
            section = normalize(text)[:200]               # bold title: new section, numbering continues
            last_numbered_idx = None
            new("heading", None, text, ln)
        elif drafts and drafts[-1].kind not in ("table_row", "table_header", "heading") and not gap_break:
            drafts[-1].add(text, ln.page)               # continuation of the current unit (also across pages)
        elif drafts and gap_break and drafts[-1].kind not in ("table_row", "table_header", "heading"):
            new("paragraph", None, text, ln, parent=last_numbered_idx)   # new paragraph, still under its clause
        else:
            new("paragraph", None, text, ln)
    flush_tables(10**9, 0.0)

    out = []
    for i, d in enumerate(drafts):
        for chunk in split_long(join_lines(d.parts)):   # very long blocks are split, never truncated
            out.append({"kind": d.kind, "text": chunk, "clause_no": d.clause_no, "page": d.page,
                        "end_page": d.end_page, "section": d.section, "parent_key": d.parent_key, "key": i})
    return out


SERIAL = re.compile(r"^\(?(?:\d{1,3}(?:\.\d{1,3})*|[ivxIVX]{1,5}|[a-zA-Z])[.)]?\)?$")   # 5  6.2  (iv)  a)


def _header_like(row: list[str]) -> bool:
    """Column titles: at least two short cells, each with a real word, no sentence punctuation,
    and the first cell is not a serial number (5, 6.2, (iv), a))."""
    cells = [c for c in row if c]
    return (len(cells) >= 2
            and all(len(c) <= 60 and (not c.endswith((".", ";")) or len(c) <= 5) and re.search(r"[A-Za-z]{2}", c)
                    for c in cells)                     # short abbreviations like 'SI.' / 'Sr.' / 'No.' are fine
            and not SERIAL.match(row[0] or ""))


SUBHEAD_LABEL = re.compile(r"^\(?[A-Z]\)?$")             # "(A)", "(B)", "B": a lettered block inside a table


def _sub_header(row: list[str]) -> bool:
    """'(B) | Criteria | Documents to be submitted' inside a table: starts a new block with its own column names."""
    return bool(row and SUBHEAD_LABEL.match(row[0] or "")) and _header_like(["Block"] + row[1:])


def _table_rows(t: dict, section: str | None, carry: dict) -> list[_Draft]:
    rows = [[normalize((c or "").replace("\n", " ")) for c in r] for r in t["rows"]]
    width = max(len(r) for r in rows)
    continuation = carry["clean"] and carry["page"] is not None and t["page"] == carry["page"] + 1
    header = carry["header"] if continuation and carry["header"] and len(carry["header"]) == width else None
    out = []
    first = True
    for r in rows:
        if not any(r):
            continue
        # only a table's first row can be its header; in a continuation it must repeat the carried header exactly
        is_header = (first and _header_like(r) and (header is None or r == header)) or _sub_header(r)
        first = False
        if is_header:
            header = r
            d = _Draft("table_header", None, t["page"], t["page"], section)
            d.add(" | ".join(c for c in r if c), t["page"])          # header rows are kept as units too
        else:
            d = _Draft("table_row", None, t["page"], t["page"], section)
            names = header if header and len(header) == len(r) else [""] * len(r)
            d.add(" | ".join(f"{h}: {v}" if h else v for h, v in zip(names, r) if v), t["page"])
        out.append(d)
    carry.update(page=t["page"], header=header, clean=True)
    return out
