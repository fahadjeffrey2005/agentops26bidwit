# BidWit: 3-minute demo

One tender, two bidders, every requirement accounted for. Numbers in **bold** are on screen; don't quote any
that aren't. Totals marked `[run]` come from the live run and are filled in after it.

## Before you start
```
cd ~/Desktop/BidWit
export GROQ_API_KEY=...        # your key; never in a file
bash start.sh                  # backend + UI, opens http://127.0.0.1:5174
```
- Do one practice run of `tender_main.pdf` first: the AI answers are cached afterwards, so the demo is fast.
- Browser at 100% zoom, window maximised. Close other tabs.
- Have `runs/<run_id>/bid_draft.md` open in a second window for the last shot.

## The 20-second version, if you only get one sentence
> A government tender runs to 85 pages and 663 real requirements. Miss one eligibility rule and the bid is
> thrown out before anyone reads it. BidWit reads the tender, finds the rules that can kill the bid, answers
> what the company can prove with a citation, and flags the rest for a person. Nothing goes out on the AI's word.

---

## 0:00-0:20 · The problem, on the landing page
**Screen:** landing page.

> This is a real public tender: 85 pages, 663 requirements. A bid team reads it by hand over days. Miss one
> eligibility rule and the whole bid is rejected before anyone looks at the price.
> BidWit turns that into an evidence-backed draft, with a person signing off at two gates.

**Click:** Start a run.

## 0:20-0:45 · Who is bidding
**Screen:** company picker, then the Northwind page.

> First, who is bidding. Two companies here. Northwind has its own 24x7 operations centre, 640 people,
> Rs 36.9 Cr average turnover. Meridian is smaller: a 12x6 desk, 95 people, Rs 8.8 Cr.

**Click:** Northwind → its page. **Scroll** to the certificates.

> This is everything the company can prove: certificates, past work, people, policies. Two records are
> **blocked before any search** — a client contract marked confidential, and an ISO 27001 certificate that
> expired. Those can never be cited, and the confidential one is never sent to a model at all.
> That limit is enforced in code, not by asking the AI nicely.

**Click:** Bid as Northwind → pick the Network operations centre RFP.

## 0:45-1:15 · The pipeline, running
**Screen:** processing page, nine stages with the live log.

> Nine stages. The PDF is parsed in a sandboxed process. Every piece of text is classified. Then the company's
> evidence is searched, a bid/no-bid call is made in code, answers are drafted and then checked.
> Two of those stages are human gates, marked "you". The run stops and waits.

(If asked about speed: classification is cached; a brand-new tender takes about six minutes on the free AI tier.)

## 1:15-1:45 · Gate A
**Screen:** Gate A.

> Gate A. Out of **785** requirements read, **49** look like must-meet rules: miss one, the bid is rejected
> outright. Each is in plain points, with the proof the tender asks for, and the page it came from.
> A person confirms or downgrades each one. Nothing is searched until this is approved, because the whole
> run hangs off this list.

**Click:** Confirm the remaining → Approve checklist.

## 1:45-2:15 · The judge and the evidence
**Screen:** dashboard. **Click** the Judge tile.

> The verdict: **CONDITIONAL**. **25** of **27** must-meet criteria are backed by evidence. Two are not:
> ISO 27001, where the only certificate expired, and presence in all Tier-1 cities, where there's no evidence
> at all. Both are correct. This is decided in code, not by the model, and a person can override it.

**Click:** More detail, briefly. Then close, and click the **evidence vault** card.

> Every claim is traceable: the document, the exact quote, and which requirement it answers.

## 2:15-2:45 · Gate B, where the honesty is
**Screen:** Gate B.

> **33** decisions, not 663. Riskiest first: failed checks, then blocking gaps, then gaps, then drafted answers.
> The 121 items only a person can do — prices, EMD, signatures — and the 511 standard compliance lines are
> each one click.
> Every drafted answer was verified in code before it got here: does it cite a real document, is the quote
> genuine, is every number in the evidence, does it overclaim. A failing answer is sent back to be rewritten,
> twice at most. Whatever still fails arrives marked.

(If there is a failed check in the run, open it: *"here's one the checker caught".*)

**Click:** approve, submit.

## 2:45-3:00 · The output and the one number that matters
**Screen:** Run complete, then `bid_draft.md`.

> Four files: the bid draft with citations, a compliance matrix, a full report and an audit trail of every step.
> And the number we care about most: **0 silent misses**. Every one of the 663 requirements ends as a cited
> answer, a standard reply, or a gap flagged for a person. None is quietly dropped.

---

## If there's time: the no-go, in 20 seconds
New run → **Meridian** → same tender. **NO-GO**, 21/27 backed, 6 blocking gaps. The run stops and asks a human
before drafting anything.
> Same tender, weaker company, different answer. The system is willing to tell you not to bid.

## Likely questions
- **"Is the AI writing the bid?"** It drafts answers where the evidence is strong. Code decides what may be
  drafted, and code checks every answer afterwards. The bid/no-bid call and all the checks have no AI in them.
- **"What if the AI is unavailable?"** Each part falls back: classification to rules, drafting to flagged gaps.
  We tested it by crashing each part on purpose; every run still finished with a report and no silent miss.
- **"What stops it inventing things?"** Five checks per answer, planted failures in the test suite for each.
  Fabricated numbers, fake quotes and exaggerated verbs are caught and sent back.
- **"Is it tied to one tender?"** No. Two unrelated real tenders are bundled; the second is a security
  operations RFP with a different layout.
- **"What doesn't it do?"** No OCR, so scanned pages are flagged for a person. Adding your own company's
  documents isn't in this build. Paused runs live in memory.
