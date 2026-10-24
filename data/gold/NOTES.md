# Gold labels for tender_main.pdf (by Aarushi Gupta)

`gold_tender_main.json`: 498 items, each `{clause, page, text, mandatory, category}`.

## Labelling notes
- Table cells are joined with " | " in reading order. The PDF itself splits some words across lines inside cells (e.g. "Mediu m").
- The mandatory rule used here leaves out many obligations: about 360 items use "should", "will" or "has to" and are marked not mandatory even when they read as obligations.
- Two staffing rows are both numbered "3", so they are labelled by role. Two sections are numbered 3.3; the second is labelled "3.3 (Problem Management)". Repeated Annexure 2/3 notes are kept once. The 11 bullets after "2.5 Billing" are labelled "2.5 bullet n".

## Contradictions and errors found in the tender (useful for clarification questions)
- Uptime targets conflict: p.45 says 99.5% dual-link / 98% single-link; Table G on p.46 reverses them (98% dual, 99% single); p.40 says 99% for MPLS and 98% for all others.
- Link count: 255 links (p.22) vs 261 in the price bid (p.67).
- Bank guarantee: refers to "Annexure - 8" but the format is Annexure 9; validity is 30 days beyond the contract (p.55) vs 60 days (guarantee paragraph).
- ISO version: asks for ISO 27001:2013 (superseded); p.17 cites "ISO27001:2021", which does not exist.
- Contract period: 2+1 years ending March 2027 (p.16) vs "3 years" (p.21) vs "renewal period" (p.55).
- Transition: 30 days (p.34) vs liquidated damages only after 3 months (4.1 F).
- Criterion 10 ("No penalties, amounting to up to 10%") can be read two ways.
- Technical evaluation criterion 3 gives no score for 1,001-1,200 links.
- Device thresholds: Annexure 1 asks for experience with 500 network devices; Criterion 4 requires 900.
