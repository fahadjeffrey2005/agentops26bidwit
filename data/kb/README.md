# Company evidence (synthetic)

`evidence.json`: 30 evidence records for the fictional bidder **Northwind IT Infrastructure Services**, written to match `tender_main.pdf`. Client names are placeholders (Client-A ... Client-M).

Fields: `id`, `doc_id`, `title`, `text`, `client`, `confidentiality` (public | internal | restricted), `date`, `expires_on`.

Built-in traps: `E-005` ISO 27001 certificate expired on 2025-10-31; `E-010` is a restricted client contract that must never reach the model or the bid.
