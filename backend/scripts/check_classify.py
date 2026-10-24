"""Measure Part 4 on tender_main.pdf against Aarushi's gold labels (proxy numbers, see README).

    python scripts/check_classify.py            # uses AI if GROQ_API_KEY / GEMINI_API_KEY are set (cached answers reused)
    python scripts/check_classify.py --fresh    # ignore the answer cache, to measure real AI time
    BIDWIT_LLM=off python scripts/check_classify.py   # rules only

Must-catch (recall): every gold eligibility item, the EMD and the bid deadline must come out pass_fail.
Noise: share of gold 'technical' items (scope duties) flagged pass_fail; lower is better.
Category: agreement with gold categories.
"""
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rapidfuzz import fuzz  # noqa: E402

from bidwit.core.progress import step, use_console  # noqa: E402
from bidwit.parts.classify import ClassifyRequest, run as classify  # noqa: E402
from bidwit.parts.extract import ExtractRequest, run as extract  # noqa: E402


def norm(s):
    s = " | ".join(re.sub(r"^[^:|]{1,60}:\s", "", c.strip()) for c in s.split(" | "))
    s = unicodedata.normalize("NFKC", s).lower().replace("|", " ")
    return re.sub(r"[^a-z0-9%.,:/()-]+", " ", s).strip()


def main():
    use_console()                                   # print every checkpoint while it runs
    if "--fresh" in sys.argv:                       # measure real AI time: answers are not read from or written to the cache
        import bidwit.parts.classify as cl
        from bidwit.core.config import load_settings
        from bidwit.core.llm import LLMClient

        def fresh():
            c = LLMClient.from_settings(load_settings())
            c.cache_dir = None
            return c
        cl.make_client = fresh
    data = ROOT.parent / "data"
    t0 = time.perf_counter()
    ex = extract(ExtractRequest(path=str(data / "tenders" / "tender_main.pdf")))
    t1 = time.perf_counter()
    res = classify(ClassifyRequest(clauses=ex.clauses))
    t2 = time.perf_counter()
    step("check", "scoring against the gold labels")
    labels = {l.clause_id: l for l in res.labels}
    units = [c for c in ex.clauses if c.id in labels]
    texts = [norm(c.text) for c in units]

    gold = json.loads((data / "gold" / "gold_tender_main.json").read_text())
    matched = []
    for g in gold:
        gt = norm(g["text"])
        cand = [i for i, c in enumerate(units) if abs(c.source.page - g["page"]) <= 1]
        if not cand:
            continue
        best = max(cand, key=lambda i: fuzz.partial_ratio(gt, texts[i]) if len(texts[i]) >= len(gt) * 0.6 else fuzz.ratio(gt, texts[i]))
        score = fuzz.partial_ratio(gt, texts[best]) if len(texts[best]) >= len(gt) * 0.6 else fuzz.ratio(gt, texts[best])
        if score >= 90:
            matched.append((g, labels[units[best].id]))

    must = [(g, l) for g, l in matched if g["category"] == "eligibility"
            or re.search(r"earnest money|\bemd\b", g["text"], re.I) or re.search(r"last date for submission", g["text"], re.I)]
    caught = [(g, l) for g, l in must if l.pass_fail]
    tech = [(g, l) for g, l in matched if g["category"] == "technical"]
    noisy = [(g, l) for g, l in tech if l.pass_fail]
    cat_ok = sum(g["category"] == l.category for g, l in matched if l.labelled_by == "ai")
    cat_n = sum(1 for _, l in matched if l.labelled_by == "ai")

    print(f"mode={res.mode} providers={list(res.providers)} ai_calls={res.ai_calls} {res.mode_reason}")
    print(f"units labelled {len(res.labels)} (ai {sum(l.labelled_by == 'ai' for l in res.labels)}, "
          f"rules {sum(l.labelled_by == 'rules' for l in res.labels)}, template {sum(l.labelled_by == 'template' for l in res.labels)}); "
          f"pass_fail flagged {sum(l.pass_fail for l in res.labels)}")
    print(f"gold items matched to a unit: {len(matched)}/{len(gold)}")
    print(f"MUST-CATCH (eligibility + EMD + deadline): {len(caught)}/{len(must)}")
    for g, l in must:
        if not l.pass_fail:
            print(f"   missed: p{g['page']} {g['clause']}: {g['text'][:90]}")
    print(f"NOISE: {len(noisy)}/{len(tech)} technical items flagged pass_fail ({len(noisy) / max(1, len(tech)):.0%})")
    print("   signals on noisy items:", Counter(s for _, l in noisy for s in l.signals).most_common())
    if cat_n:
        print(f"CATEGORY agreement (AI-labelled items): {cat_ok}/{cat_n} ({cat_ok / cat_n:.0%})")
    print(f"TIME extract {t1 - t0:.0f}s, classify {t2 - t1:.0f}s")


if __name__ == "__main__":
    main()
