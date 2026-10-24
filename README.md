# BidWit

Multi-agent system that turns an IT infrastructure tender into a compliant, evidence-backed bid draft.
Every requirement ends as a cited answer or a flagged gap. Humans approve at gates.
AgentOps'26 (MIT Bengaluru × CGI), domain: **IT Infrastructure**. Team: Fahad Jeffrey, Aarushi Gupta.

## Layout
```
backend/   Python 3.13: parts, workflow (LangGraph), API (FastAPI)
  bidwit/core/    shared contracts, settings, run_part isolation wrapper
  bidwit/parts/   one folder per part; parts never import each other
  bidwit/workflow LangGraph: joins the parts, pauses at the human gates, writes the outputs
  bidwit/api      FastAPI: upload, poll, answer gates, download (talks only to the workflow)
  tests/
frontend/  React + TypeScript + Tailwind dashboard
data/
  tenders/  two real public tenders (sources in SOURCES.md)
  kb/       one folder per mock bidder (northwind, meridian) + companies.json
  gold/     498 hand-labelled items for tender_main.pdf, plus contradictions found in it
```

## Rules every part follows
1. Its own folder in `backend/bidwit/parts/`, its own tests in `backend/tests/<part>/`.
2. Typed input and output (strict, frozen models from `bidwit/core/contracts.py`).
3. Imports only `bidwit.core`, never another part (a test enforces this).
4. Runs through `run_part`: a crash or a wrong-shaped output becomes a flagged item for a human, never a dead run.

## Parts
| Part | Folder | In | Out | Status |
|---|---|---|---|---|
| 2 Extraction | `parts/extract` | tender PDF path | `ExtractResult`: clauses with page refs, page notes, removed headers | done |
| 4 Classification | `parts/classify` | clauses | `ClassifyResult`: category and pass/fail per clause, with the signals that fired | done |
| 3 Evidence search | `parts/kb` | evidence file, today's date, clause texts | `RetrieveResult`: top evidence per clause, missing required terms, blocked documents, search mode | done |
| 5a Judge | `parts/judge` | requirements, evidence found | `Verdict`: go / conditional / no_go and the blocking gaps (code only, no AI) | done |
| 5b Writer | `parts/writer` | requirements, evidence found, checker failures | `Draft`: cited claims and gaps | done |
| 5c Checker | `parts/checker` | requirements, evidence, draft | `CheckReport`: per-claim checks, silent misses (code only, no AI) | done |
| 6 Workflow | `workflow/` | tender PDF | gates A / no-go / B, then `runs/<run_id>/` outputs | done |
| 7 API | `api/` | HTTP | JSON, output files | done |
| 8 UI | `frontend/` | the API | bento dashboard, live progress, Gate A / no-go / Gate B screens, downloads | done |

### Part 2: extraction
1. **Safety gate** (pypdf, separate process): must be a real PDF, at most 20 MB and 500 pages, not password-protected, and no stream may inflate past 75 MB (zip bombs). A bad file is refused with a reason.
2. **Read** (pdfplumber, separate process, time limit): lines, tables, hidden characters and image coverage per page. One unreadable page does not lose the others.
3. **Clean**: Unicode normalised (ligatures, invisible characters), repeated headers/footers and page numbers removed (and listed), hyphenated line breaks joined.
4. **Segment**: headings, numbered clauses (1.1, 2.3.4), sub-items ((a), (iv)), table rows (each row with its column names), paragraphs. Clauses can span pages.
5. **Flags for Gate A**: hidden text (white, tiny or off-page: removed from the text and shown to a human), scanned pages (no text layer: read by hand), unreadable pages.

Nothing is filtered: tests check word for word that every visible word ends up in a unit, on the synthetic tender and on both real tenders (51,877 words, 0 lost).

Measured on `tender_main.pdf` against Aarushi's 498 gold items: 490 come out intact in one unit (98.4%), 7 are split across neighbouring units, 1 is incomplete (a merged table cell, see below).

Known limits:
- No OCR: scanned pages are flagged, not read.
- Text drawn in invisible render mode is not detected (white, tiny and off-page text is).
- A merged table cell spanning several rows is attached to the first row only.
- A word hyphenated at a line end is always joined ("e-" + "procurement" becomes "eprocurement").
- Words the PDF itself splits inside table cells stay split ("Mediu m").

### Bidding companies
Two mock bidders share the same evidence format (`data/kb/<id>/evidence.json`, listed in `data/kb/companies.json`):
Northwind IT (Bengaluru, own 24x7 NOC, 30 records) and Meridian Netserve (Pune, 12x6 desk, 18 records).
A run picks one; `GET /api/companies` and `GET /api/companies/{id}` serve the picker and the profile screen
(restricted text is never sent). On `tender_main.pdf`: Northwind is CONDITIONAL (25/27 backed, 2 blocking),
Meridian is NO-GO (21/27, 6 blocking), so the no-go gate can be demonstrated on the same tender.

### Part 3: evidence search
- **Vector database:** Qdrant (local mode, in memory, rebuilt from `data/kb/evidence.json` at start; no server).
- **Hybrid search:** keyword vectors (BM25, computed by our code) + meaning vectors (Gemini `gemini-embedding-001`, 768 dimensions), fused by rank (RRF). If Gemini is unavailable (no key, quota, offline) search continues keyword-only and the result says why.
- **Lock 1:** restricted records are never indexed and never sent to any model.
- **Lock 2:** every search filters out records whose expiry date has passed.
- **Required terms:** standards (ISO 27001), certifications (CCNP), 24x7, data-centre tier, MSME. Each hit lists the terms it lacks; a term no evidence covers is reported as `uncovered_terms` (a likely gap), after a direct search for it.
- **Cache:** Gemini vectors are cached in `runs/cache/` by hash (texts are not stored), so restarts cost no API calls. Corrupt or tampered entries are ignored.
- Measured (keyword mode) on 17 real requirements from `tender_main.pdf`: right evidence in the results 17/17, ranked first 16/17. Hybrid: run `python scripts/check_kb.py` with `GEMINI_API_KEY` set.

### AI layer (`core/llm.py`)
- One client for every part. Providers are tried in order: Groq `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, then Gemini `gemini-3.6-flash` (change with `BIDWIT_LLM_CHAIN`). A provider that is out of quota, missing its key, unknown or overloaded is skipped for the rest of the run.
- Every answer is validated against a schema; anything that doesn't match is retried, then the next provider is used.
- Answers are cached in `runs/cache/llm/` (by hash of the question, not the provider), so replays cost no calls.
- Groq calls are paced to stay under the free 8k tokens/minute per model (`BIDWIT_GROQ_TPM`, default 7000), and batches rotate across the Groq models so their limits add up. A per-day limit moves to the next provider.
- A call budget per run (`BIDWIT_LLM_MAX_CALLS`, default 150). `BIDWIT_LLM=off` disables AI entirely; parts then use their rules.
- Keys come only from the environment: `GROQ_API_KEY`, `GEMINI_API_KEY`. Never put them in a file in this repository.

### Part 4: classification
- **pass/fail** = the bid is rejected at evaluation if this is not met. Set if any one signal fires: **section** (under an eligibility / EMD / bid-submission heading), **wording** (rejected, disqualified, mandatory, EMD, submission deadline) or **ai** (the model says the bid would be rejected *and* calls the item eligibility or technical; its other votes were schedule rows, annex checklists and form fields: on the backup tender this cut Gate A from 69 to 25 items, with must-catch on the main tender unchanged). A human confirms every pass/fail item at Gate A, so over-flagging is acceptable and missing one is not.
- **category** (eligibility / technical / commercial / format / other) comes from the AI; rules if no AI is available. Only real criteria (6+ words) are sent to the AI. A batch the AI can't answer is labelled by rules on its own; the other batches keep their AI labels.
- Annex forms and data tables (link inventory, integrity pact text, bank guarantee format, price bid form) are labelled `template` without AI.
- Measured on `tender_main.pdf` (proxy, against Aarushi's labels), `python scripts/check_classify.py`:

  | | rules only | with AI (Groq) |
  |---|---|---|
  | must-catch (19 eligibility criteria + EMD + deadline) | 22/22 | 22/22 |
  | noise: scope duties flagged pass/fail | 0/417 | 13/417 (3%, all from the AI signal) |
  | category agreement | - | 420/463 (91%) |
  | time (free Groq tier, 32 calls, paced) | 0 s | 683 s; a re-run hits the cache: seconds |
- Why not LAYA: tested on 200 labelled items. As shipped it scored 0.64 on "mandatory" vs 0.80 for a simple rule, and 0.73 vs 0.79 (Groq) on category. Kept out of the pipeline.

### Part 5: Judge, Writer, Checker
- One shared rule decides "strong evidence" (`core/evidence.py`): keyword score >= 4 or meaning score >= 0.70, and no missing required term. Fragments and titles (fewer than 6 words, or ending in ":") are not criteria.
- **Judge** (code): only pass/fail eligibility and technical criteria count. 0 gaps: GO; up to 3: CONDITIONAL; more: NO-GO.
- **Writer** (AI): code first decides what may be drafted. Commercial and format items go to a person (`human_decides`); no strong evidence becomes a gap (the AI is never asked); at most 40 drafts per run, pass/fail first. The AI sees only strong evidence and must cite ids and quote verbatim.
- **Compliance matrix:** scope duties (technical, not pass/fail) that are not drafted get a standard statement ("Complied. Northwind will meet this requirement as specified.") instead of a gap. A missing named standard or certification always stays a gap.
- **Checker** (code): every claim is checked for citation (evidence found for that requirement), blocked source (restricted or expired), quote (fuzzy >= 90), numbers (only numbers in the evidence or the requirement), overclaim (led, guarantee, always, ...). Coverage: every criterion ends as a claim or a gap; anything else is a silent miss.
- A failed claim is sent back to the Writer with the reasons, at most 2 rewrite rounds; what still fails goes to the human, marked.

### Part 6: workflow (LangGraph)
```
extract -> classify -> GATE A -> evidence search -> judge -> [NO-GO gate] -> write <-> check (max 2 rewrites) -> GATE B -> package
```
- Every part runs through `run_part`. A crashing part gets a safe fallback and is recorded: classify -> wording rules; evidence search -> every item a gap; judge -> no-go gate (a human decides); writer -> every criterion a gap; checker -> every answer marked unchecked. Only an unreadable tender ends the run early, still with a report.
- Gates pause the run (LangGraph `interrupt`) and resume with the human's answer. At the no-go gate anything but an explicit "continue" stops.
- Gate B, riskiest first: failed checks, blocking gaps, other gaps, pass/fail answers, other answers, then two groups decided with one click each: tasks for a person (`G-PERSON`: prices, EMD, signatures) and compliance statements (`G-COMPLY`). On `tender_main.pdf` this is 33 decisions instead of 663.
- Outputs in `runs/<run_id>/`: `report.json`, `compliance.csv`, `bid_draft.md` (approved answers with citations, then every gap), `audit.jsonl`.
- Run state is kept in memory; finished runs are read back from disk after a restart.

### Demo mode: cached answers
The tender screen has a **Use cached data / Live AI** switch (`cached=true` on `POST /api/runs`). In cached mode the
AI client serves answers from `runs/cache/llm/` and **never calls a provider**: a question that is not cached falls
back to the part's rules path instead of reaching the network. A run finishes in seconds and cannot be broken by a
rate limit or a dead free tier. `GET /api/health` reports how many answers are cached.

### Part 7: API (FastAPI)
`uvicorn bidwit.api:app --host 127.0.0.1 --port 8000`, docs at `/api/docs`.
`GET /api/health`, `GET /api/evidence` (restricted text never sent), `POST /api/runs` (PDF upload or `sample=tender_main`), `GET /api/runs`, `GET /api/runs/{id}` (status, waiting gate, live audit), `POST /api/runs/{id}/gates/{A|no_go|B}`, `GET /api/runs/{id}/files/{name}`.
Uploads: PDF only, size-limited, stored as `runs/<run_id>/tender.pdf`. Gate answers are validated strictly.

## Security
- Runs locally only: the API binds to 127.0.0.1 and serves only requests addressed to localhost (blocks DNS rebinding).
- Every POST needs the header `X-BidWit: 1`; with the strict CORS policy, other websites can't start runs or answer gates.
- Request bodies are size-checked before parsing (uploads: the configured limit; JSON: 1 MB). PDF only, checked by magic bytes, then the extraction safety gate (separate process, page/size/zip-bomb limits).
- At most 3 runs work at once; more get HTTP 429.
- Outputs are safe to open: CSV cells that would run as spreadsheet formulas are escaped; raw HTML in Markdown is neutralised.
- Security headers on every response (nosniff, no framing, no referrer, no caching, CSP).
- Keys only from the environment, never logged or returned (`/api/health` reports only whether a key is set). Restricted evidence is never indexed, sent to a model, or returned by `/api/evidence`.
- Checkpoints use LangGraph's msgpack serializer limited to our own types (no pickle).
- Checked: `pip-audit` (73 pinned packages) and `npm audit`: 0 known vulnerabilities; `bandit`: no real findings.

## Quick start
```
export GROQ_API_KEY=...      # optional: without it the AI parts fall back to rules and flagged gaps
bash start.sh                # first run installs everything; opens http://127.0.0.1:5174; Ctrl+C stops it
```
Results and how they were measured: [EVAL.md](EVAL.md).

## Setup (macOS, Python 3.13)
```
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.txt
python -m pytest
```
Every dependency is pinned with checksums (see the header of `requirements.txt`).

Run the API:
```
export GROQ_API_KEY=...        # optional; without it AI parts fall back to rules / gaps
uvicorn bidwit.api:app --host 127.0.0.1 --port 8000
```

UI (second terminal; the dev server forwards `/api` to the backend on port 8000):
```
cd frontend
npm ci
npm run dev
```
Open http://127.0.0.1:5174. Start a run (drop a PDF or pick a bundled tender), watch every stage live, approve at Gate A, review at Gate B, download the outputs.
