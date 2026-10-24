"""Runs in a separate, short-lived process. Never imported by the server.

    python -I worker.py gate <pdf> <max_pages>   -> JSON {"ok": bool, "reason": str, "pages": int}
    python -I worker.py read <pdf>               -> JSON {"pages": [PageData, ...]}

If a malformed PDF crashes or hangs this process, only this process dies;
the parent kills it on timeout and reports a rejection.
"""
from __future__ import annotations

import json
import sys

MAX_STREAM_BYTES = 75_000_000        # pypdf's own per-stream inflate cap
MAX_TOTAL_BYTES = 400_000_000        # whole-document inflate budget
HIDDEN_MAX_SIZE = 2.5                # characters smaller than this (pt) are treated as hidden
MEMORY_CAP_BYTES = 2 * 1024**3      # Linux enforces this; macOS ignores RLIMIT_AS (the parent's time limit still applies)
WHITE = {(1,), (1, 1, 1), (0, 0, 0, 0), (1.0,), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 0.0)}


def gate(path: str, max_pages: int) -> dict:
    from pypdf import PdfReader
    from pypdf.errors import LimitReachedError

    with open(path, "rb") as fh:
        if not fh.read(1024).lstrip().startswith(b"%PDF-"):
            return {"ok": False, "reason": "not a PDF file", "pages": 0}
    try:
        reader = PdfReader(path, strict=False)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"unreadable PDF ({type(e).__name__})", "pages": 0}
    if reader.is_encrypted:
        return {"ok": False, "reason": "PDF is password-protected", "pages": 0}
    try:
        n = len(reader.pages)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"broken page tree ({type(e).__name__})", "pages": 0}
    if n == 0:
        return {"ok": False, "reason": "PDF has no pages", "pages": 0}
    if n > max_pages:
        return {"ok": False, "reason": f"too many pages ({n} > {max_pages})", "pages": n}
    total = 0
    try:
        for page in reader.pages:                 # inflate every content stream once, under limits
            contents = page.get_contents()
            if contents is not None:
                total += len(contents.get_data())
            res = page.get("/Resources")
            res = res.get_object() if res is not None else None
            xobjs = res.get("/XObject") if res is not None else None
            if xobjs is not None:
                for ref in xobjs.get_object().values():
                    x = ref.get_object()
                    if x.get("/Subtype") == "/Form":     # forms are parsed as text; images are not decoded
                        total += len(x.get_data())
            if total > MAX_TOTAL_BYTES:
                return {"ok": False, "reason": "content inflates beyond the safe limit (possible zip bomb)", "pages": n}
    except LimitReachedError:
        return {"ok": False, "reason": "a stream inflates beyond the safe limit (possible zip bomb)", "pages": n}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"corrupt content stream ({type(e).__name__})", "pages": n}
    return {"ok": True, "reason": "", "pages": n}


def _is_hidden(c: dict, w: float, h: float) -> bool:
    color = c.get("non_stroking_color")
    color = tuple(color) if isinstance(color, (list, tuple)) else color
    off_page = c["x1"] < 0 or c["x0"] > w or c["bottom"] < 0 or c["top"] > h
    return c["size"] < HIDDEN_MAX_SIZE or color in WHITE or off_page


def _table_settings(page) -> dict | None:
    """Only thin or stroked rectangles and real lines count as table borders. Many PDFs paint a filled
    background box behind every text line; treating those as borders splits each line into its own row."""
    objs = [r for r in page.rects if r.get("stroke") or min(r["width"], r["height"]) <= 2] + list(page.lines)
    v = [o for o in objs if o["width"] <= 2 or (o.get("stroke") and o["width"] > 2)]
    h = [o for o in objs if o["height"] <= 2 or (o.get("stroke") and o["height"] > 2)]
    if not v or not h:
        return None
    return {"vertical_strategy": "explicit", "horizontal_strategy": "explicit",
            "explicit_vertical_lines": v, "explicit_horizontal_lines": h,
            "snap_tolerance": 3, "intersection_tolerance": 4}


def read(path: str) -> dict:
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            try:
                w, h = float(p.width), float(p.height)
                hidden = "".join(c["text"] for c in p.chars if _is_hidden(c, w, h))
                visible = p.filter(lambda o: not (o.get("object_type") == "char" and _is_hidden(o, w, h)))
                tables, boxes = [], []
                settings = _table_settings(visible)
                for t in (visible.find_tables(settings) if settings else []):
                    rows = [r for r in t.extract() if any((c or "").strip() for c in r)]
                    if rows and max(len(r) for r in rows) >= 2:
                        tables.append({"top": float(t.bbox[1]), "rows": [[(c or "").strip() for c in r] for r in rows]})
                        boxes.append(t.bbox)
                body = visible
                for b in boxes:
                    body = body.outside_bbox(b)
                lines = []
                for ln in body.extract_text_lines(return_chars=True, strip=True):
                    if not ln["text"]:
                        continue
                    bold = sum("Bold" in (c.get("fontname") or "") for c in ln["chars"]) > len(ln["chars"]) / 2
                    lines.append({"text": ln["text"], "top": float(ln["top"]), "bottom": float(ln["bottom"]),
                                  "x0": float(ln["x0"]), "bold": bold})
                img_area = sum(max(0.0, (im["x1"] - im["x0"])) * max(0.0, (im["bottom"] - im["top"])) for im in p.images)
                pages.append({"page": i, "height": h, "lines": lines, "tables": tables, "hidden": hidden[:2000],
                              "image_cover": min(1.0, img_area / (w * h)) if w and h else 0.0, "error": ""})
            except Exception as e:  # noqa: BLE001 - one bad page must not lose the others
                pages.append({"page": i, "height": 0.0, "lines": [], "tables": [], "hidden": "",
                              "image_cover": 0.0, "error": f"{type(e).__name__}"[:80]})
    return {"pages": pages}


def _limit_memory() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_BYTES, MEMORY_CAP_BYTES))
    except (ImportError, ValueError, OSError):
        pass


def main() -> None:
    _limit_memory()
    mode, path = sys.argv[1], sys.argv[2]
    out = gate(path, int(sys.argv[3])) if mode == "gate" else read(path)
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
