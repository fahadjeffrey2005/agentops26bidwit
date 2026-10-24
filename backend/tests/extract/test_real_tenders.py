"""Regression tests on the two real tenders in data/tenders (about 25 s)."""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest
from rapidfuzz import fuzz

from bidwit.parts.extract import ExtractRequest, run, runner
from bidwit.parts.extract.clean import clean_pages, normalize

DATA = Path(__file__).resolve().parents[3] / "data"
TENDERS = ["tender_main.pdf", "tender_backup.pdf"]


@pytest.fixture(scope="module")
def results():
    return {name: run(ExtractRequest(path=str(DATA / "tenders" / name))) for name in TENDERS}


def _words(s):
    return re.findall(r"[a-z0-9]+", normalize(s).lower())


@pytest.mark.parametrize("name", TENDERS)
def test_no_word_lost_on_real_tender(results, name):
    res = results[name]
    pages = runner.read(DATA / "tenders" / name, res.pages)
    body, _ = clean_pages(pages)
    src = Counter()
    for ln in body:
        src.update(_words(ln.text))
    for p in pages:
        for t in p["tables"]:
            for r in t["rows"]:
                for c in r:
                    src.update(_words(c or ""))
    out = Counter()
    for c in res.clauses:
        out.update(_words(c.text))
        if c.kind in ("clause", "sub_item", "heading") and c.source.clause_no:
            out.update(_words(c.source.clause_no))
    missing, extra = src - out, out - src
    for w in list(extra.elements()):                 # allowed: hyphenated line-end words joined
        for i in range(1, len(w)):
            if missing[w[:i]] and missing[w[i:]]:
                missing[w[:i]] -= 1
                missing[w[i:]] -= 1
                break
    assert not +missing, (+missing).most_common(20)


def _strip_cols(s):
    return " | ".join(re.sub(r"^[^:|]{1,60}:\s", "", c.strip()) for c in s.split(" | "))


def _norm(s):
    s = unicodedata.normalize("NFKC", _strip_cols(s)).lower().replace("|", " ")
    return re.sub(r"[^a-z0-9%.,:/()-]+", " ", s).strip()


def test_gold_items_recovered_on_main_tender(results):
    """Aarushi's 498 labelled items: at least 97% must come out intact in a single unit,
    and at least 99.5% intact in one unit or across neighbouring units."""
    gold = json.loads((DATA / "gold" / "gold_tender_main.json").read_text())
    units = [_norm(c.text) for c in results["tender_main.pdf"].clauses]
    pages = [c.source.page for c in results["tender_main.pdf"].clauses]
    one = near = 0
    for g in gold:
        gt = _norm(g["text"])
        cand = [i for i, p in enumerate(pages) if abs(p - g["page"]) <= 1]
        score = lambda i: fuzz.partial_ratio(gt, units[i]) if len(units[i]) >= len(gt) * 0.6 else fuzz.ratio(gt, units[i])
        if max(map(score, cand)) >= 90:
            one += 1
        elif fuzz.partial_ratio(gt, " ".join(units[min(cand):max(cand) + 1])) >= 90:
            near += 1
    assert one / len(gold) >= 0.97, (one, near, len(gold))
    assert (one + near) / len(gold) >= 0.995, (one, near, len(gold))


def test_real_tenders_have_no_false_alarms(results):
    """Neither real tender has hidden text or scanned pages; a flag here would be a false alarm at Gate A."""
    for name in TENDERS:
        assert results[name].notes == (), (name, results[name].notes)
