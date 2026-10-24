"""End-to-end tests on real files (each run starts real subprocesses)."""
import json
import re
import time
from collections import Counter

import pytest

from bidwit.core.contracts import Rejected
from bidwit.core.isolation import run_part
from bidwit.core.contracts import ExtractResult
from bidwit.parts.extract import ExtractRequest, run
from bidwit.parts.extract import runner
from bidwit.parts.extract.clean import normalize

from .conftest import FIX

GOLD = json.loads((FIX / "hard_tender.gold.json").read_text())


@pytest.fixture(scope="module")
def hard():
    return run(ExtractRequest(path=str(FIX / "hard_tender.pdf")))


def by_no(res, num):
    return [c for c in res.clauses if c.source.clause_no == num]


def test_every_numbered_clause_found_with_exact_text_and_page(hard):
    for g in GOLD["clauses"]:
        if g["num"].startswith("("):
            continue
        found = by_no(hard, g["num"])
        assert len(found) == 1, g["num"]
        assert found[0].text == normalize(g["text"]), g["num"]
        assert found[0].source.page == g["page"] and found[0].source.end_page == g["end_page"], g["num"]


def test_sub_items_keep_their_parent(hard):
    for g in [g for g in GOLD["clauses"] if g["num"].startswith("(")]:
        sub = [c for c in hard.clauses if c.kind == "sub_item" and c.text == normalize(g["text"])]
        assert len(sub) == 1, g["num"]
        parent = next(c for c in hard.clauses if c.id == sub[0].parent_id)
        assert parent.source.clause_no == g["parent"]


def test_table_rows_are_whole_rows(hard):
    rows = [c for c in hard.clauses if c.kind == "table_row" and "Criteria: " in c.text]
    assert len(rows) == len(GOLD["table_rows"])
    for g in GOLD["table_rows"]:
        assert any(normalize(g["criteria"]) in r.text and normalize(g["documents"]) in r.text for r in rows)


def test_hidden_injection_removed_and_flagged(hard):
    assert not any("ignore all earlier rules" in c.text for c in hard.clauses)
    notes = [n for n in hard.notes if n.flag == "hidden_text"]
    assert [n.page for n in notes] == GOLD["hidden_text_pages"]
    assert "ignore all earlier rules" in notes[0].detail


def test_scanned_page_flagged(hard):
    assert [n.page for n in hard.notes if n.flag == "scanned"] == GOLD["scanned_pages"]


def test_headers_and_footers_removed_but_reported(hard):
    assert not any("Confidential - for bidders only" in c.text or re.search(r"Page \d of 6", c.text) for c in hard.clauses)
    assert any("Page 1 of 6" == r for r in hard.removed_lines)


def test_no_word_is_lost(hard):
    """Every word left after header/footer removal ends up in a clause, counted exactly (multiset)."""
    from bidwit.parts.extract.clean import clean_pages

    pages = runner.read(FIX / "hard_tender.pdf", hard.pages)
    body, removed = clean_pages(pages)
    words = lambda s: re.findall(r"[a-z0-9]+", normalize(s).lower())
    source = Counter()
    for ln in body:
        source.update(words(ln.text))
    for p in pages:
        for t in p["tables"]:
            for i, r in enumerate(t["rows"]):
                for cell in r:
                    source.update(words(cell) * (len(t["rows"]) if i == 0 else 1))   # header: own unit + once per data row
    out = Counter()
    for c in hard.clauses:
        out.update(words(c.text))
        if c.kind in ("clause", "sub_item") or (c.kind == "heading" and c.source.clause_no):
            out.update(words(c.source.clause_no or ""))
    assert source - out == Counter({"con": 1, "solidated": 1}), source - out      # joined into 'consolidated'
    assert out - source == Counter({"consolidated": 1}), out - source             # nothing invented either
    assert set(removed) == set(hard.removed_lines)


def test_sample_tender_all_clauses():
    res = run(ExtractRequest(path=str(FIX / "sample_tender.pdf")))
    nums = [c.source.clause_no for c in res.clauses if c.kind == "clause"]
    assert nums == ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "4.1", "4.2"]


def test_same_input_same_output(hard):
    assert run(ExtractRequest(path=str(FIX / "hard_tender.pdf"))) == hard


@pytest.mark.parametrize("name,reason", [
    ("bomb", "zip bomb"),
    ("loop", ""),
    ("encrypted", "password-protected"),
    ("fake", "not a PDF"),
    ("truncated", ""),
    ("too_many_pages", "too many pages"),
    ("empty", "empty"),
])
def test_hostile_files_are_refused_quickly(hostile, name, reason):
    t0 = time.perf_counter()
    with pytest.raises(Rejected) as e:
        run(ExtractRequest(path=str(hostile[name]), max_pages=500))
    assert time.perf_counter() - t0 < 30
    assert reason in str(e.value)


def test_missing_and_oversized_files(tmp_path):
    with pytest.raises(Rejected, match="not found"):
        run(ExtractRequest(path=str(tmp_path / "nope.pdf")))
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-1.7\n" + b"0" * (2 * 1024 * 1024))
    with pytest.raises(Rejected, match="larger than 1 MB"):
        run(ExtractRequest(path=str(big), max_mb=1))


def test_through_run_part_a_refusal_is_not_a_crash(hostile):
    res, ev = run_part("extract", run, ExtractRequest(path=str(hostile["bomb"])), ExtractResult)
    assert not res.ok and res.error.kind == "rejected" and ev.level == "error"
