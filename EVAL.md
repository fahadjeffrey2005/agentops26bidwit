# BidWit: evaluation

Every number below was measured on the two real public tenders in `data/tenders/` (sources in `SOURCES.md`) and the
synthetic bidder's evidence in `data/kb/evidence.json`. Gold labels: 498 items hand-labelled for `tender_main.pdf`
(`data/gold/`). Commands to reproduce are given per section. Free tiers only (Groq, Gemini).

## Headline

| What | Result |
|---|---|
| Requirements silently missed (no answer and no flag) | **0** on both tenders |
| Pass/fail items caught (19 eligibility criteria + EMD + bid deadline) | **22/22** |
| Tender text kept by extraction (51,877 words, both tenders) | **0 words lost** |
| Gold items extracted intact | **490/498** (98.4%) |
| Restricted or expired evidence ever cited | **0** (blocked in code before search; checked again on every claim) |
| Human review load, main tender (Gate B) | **33 decisions** instead of 663 |
| Automated tests | **178 passing** (`cd backend && python -m pytest`) |

## 1. Extraction (Part 2)
`python -m pytest tests/extract`
- 498 gold items on `tender_main.pdf`: 490 intact in one unit, 7 split across neighbouring units, 1 incomplete (a merged table cell).
- Word-for-word check on both real tenders: every visible word ends up in a unit (51,877 words, 0 lost).
- Synthetic adversarial tender: hidden white/tiny/off-page text is removed and flagged for Gate A; scanned pages are flagged; repeated headers/footers are removed and listed.
- Safety gate: oversized, encrypted, non-PDF and zip-bomb files are refused before parsing (separate process, time and memory limits).

## 2. Evidence search (Part 3)
`python scripts/check_kb.py`
- 17 real requirements from `tender_main.pdf`, keyword mode: right evidence in the results 17/17, ranked first 16/17.
- Expired ISO 27001 certificate (E-005) and the confidential Client-C contract (E-010) are never returned. The confidential record is never indexed or sent to any model.

## 3. Classification (Part 4)
`python scripts/check_classify.py` (proxy against the gold labels)

| | rules only | with AI (Groq) |
|---|---|---|
| must-catch: eligibility + EMD + deadline | 22/22 | 22/22 |
| noise: scope duties flagged pass/fail | 0/417 | 13/417 (3%) |
| category agreement | - | 420/463 (91%) |

- The AI's pass/fail vote counts only when it also calls the item eligibility or technical. Replayed on the AI's cached answers: backup tender Gate A went from 69 to 25 items (schedule rows, annex checklists and form fields removed), main tender must-catch unchanged at 22/22.
- Speed on the free Groq tier (8k tokens/minute per model): 683 s sequential, about 6 min with batches in parallel across three models; a repeat run of the same tender is served from the answer cache in seconds.
- LAYA was tested on 200 labelled items and left out: 0.64 on "mandatory" vs 0.80 for a simple rule.

## 4. Bid / no-bid judge (Part 5a, code only)
- Main tender: **CONDITIONAL**, 25/27 pass/fail criteria backed by evidence. The 2 blocking gaps are the right ones: R-061 (ISO 27001: the only certificate expired) and R-064 (presence in all Tier-1 cities: no evidence).
- Backup tender (rules + keyword search): **CONDITIONAL**, 14/17 backed; blocking R-386 (remote SOC certifications incl. ISO 27001), R-073, R-390.

## 5. Writer and Checker (Parts 5b, 5c)
Live AI run on `tender_main.pdf` (Northwind, Groq for classify and writer, keyword evidence search):

| | |
|---|---|
| answers drafted from evidence | **40** |
| passed every check, round 1 | **40/40** |
| rewrite rounds needed | **0** |
| gaps flagged for a person | 82 |
| standard compliance statements | 458 |
| **silent misses** | **0** |
| AI calls | 46 |
| wall time, cold cache | 738 s |

The judge called it NO-GO (37/49 must-meet criteria backed, 12 blocking gaps); the reviewer overrode it, and the
system drafted the 40 answers it could support. A repeat of the same run replays from the answer cache in seconds.

Checker tests (`tests/test_agents.py`), each planted and caught:
- "led" where the evidence says "supported" → overclaim
- an invented number (2,500 devices) → numbers
- a quote not in the cited evidence → quote
- citing evidence not found for that requirement → citation
- citing restricted evidence → blocked source
- a requirement with neither answer nor gap → silent miss

A failing answer is rewritten at most twice with the checker's reasons; whatever still fails goes to the human, marked.

## 6. Fault isolation (Part 6)
`python -m pytest tests/workflow`
Each part was made to crash on purpose; every run still finished with a report and **no silent miss**:

| Crashed part | Safe fallback |
|---|---|
| classify | wording rules; category checked by a human |
| evidence search | every requirement becomes a flagged gap |
| judge | no-go gate: a human decides |
| writer | every criterion becomes a flagged gap |
| checker | every answer marked unchecked for the human |
| unreadable tender | run ends early, still with a report |

## 7. Security
`pip-audit` (73 pinned packages) and `npm audit`: 0 known vulnerabilities. `bandit`: no real findings.
Manual review fixes, each with a test: cross-site requests blocked, DNS rebinding blocked, body size checked before
parsing, at most 3 active runs, CSV formula injection escaped, HTML in Markdown neutralised, security headers.

## Known limits
- No OCR: scanned pages are flagged for a person, not read.
- The evidence library is a JSON file; there is no screen to add documents.
- Rejecting an answer at Gate B marks it rejected; it does not trigger a rewrite.
- Paused runs live in memory: restarting the server during a gate loses that run (finished runs are kept on disk).
- Free-tier AI limits a brand-new tender to about 6 minutes of classification. The **Use cached data** switch replays
  saved answers instead, with no provider call at all, so a demo cannot be broken by a rate limit.
