"""Deterministic signals. Pure functions, no I/O, no AI.

pass/fail = 'the bid is rejected at evaluation if this is not met'. Two of the three signals live here:
  section: the clause sits under an eligibility / pre-qualification / EMD / bid-submission heading
  wording: the clause itself says the bid will be rejected, is mandatory, or is about EMD or the deadline
"""
from __future__ import annotations

import re

SECTION_PF = re.compile(
    r"eligibilit|pre[\s-]?qualif|qualification criteria|earnest money|\bemd\b|bid security"
    r"|submission of (the )?bids?|bids? preparation and submission|instructions to bidders", re.I)

WORDING_PF = re.compile(
    r"\b(will|shall|may|would|is|are|being)\s+(liable\s+to\s+be\s+|be\s+|summarily\s+|outright\s+)*(rejected|disqualified)\b"
    r"|\brejection of (the |his |their )?(bid|offer|proposal)"
    r"|\bdisqualif\w*|\bnon[\s-]?consideration\b|\b(bid|offer|proposal|bidder|tender)s?\b[^.]{0,60}\bnot be considered\b"
    r"|\bnon[\s-]?responsive\b|\bmandatory\b"
    r"|\bearnest money\b|\bemd\b|\bbid security\b"
    r"|\blast date (and time )?(of|for) (the )?submission\b|\bbid due date\b|\bdue date (of|for) submission\b",
    re.I)

# fill-in forms and data tables inside annexures: labelled without AI (they are not requirements to classify)
TEMPLATE_SECTION = re.compile(
    r"link details|format of bank guarantee|integrity pact|covering letter|price bid format|commercial price bid"
    r"|details of bidder.?s profile|compliance statement", re.I)

COMMERCIAL = re.compile(r"\b(emd|earnest money|price|pricing|payment|invoice|penalt\w*|bank guarantee|pbg|tax(es)?|gst|"
                        r"liquidated damages|cost|rate|fee|commercial)\b", re.I)
FORMAT = re.compile(r"\b(submission|submit(ted)?|upload\w*|deadline|last date|signed|stamp\w*|letter ?head|format|"
                    r"page|copies|envelope|portal|online bid)\b", re.I)


def section_signal(section: str | None) -> bool:
    return bool(section and SECTION_PF.search(section))


def wording_signal(text: str) -> bool:
    return bool(WORDING_PF.search(text))


def is_template(section: str | None) -> bool:
    return bool(section and TEMPLATE_SECTION.search(section))


DOCUMENT_TASK = re.compile(r"\b(upload\w*|signed|stamp\w*|signature|letter of authori[sz]ation|self[\s-]?certificat\w*|"
                           r"letter ?head|dated this|duly authori[sz]ed)\b", re.I)


DOC_COLUMN = re.compile(r"document|evidence|proof|submitted|compliance|remark", re.I)


def criterion_text(text: str) -> str:
    """For a table row 'Criteria: ... | Documents to be submitted: ...', drop the documents/proof columns,
    so 'self-declaration on letter head' in the proof column doesn't turn a criterion into paperwork."""
    cells = text.split(" | ")
    kept = [c for c in cells if not (":" in c and DOC_COLUMN.search(c.split(":", 1)[0]))]
    return " | ".join(kept) if kept else text


def rule_category(text: str, section: str | None) -> str:
    """Fallback category when no AI is available. Deliberately simple; reported as rules-based."""
    text = criterion_text(text)
    if DOCUMENT_TASK.search(text):
        return "format"                                  # paperwork for a person, not a company capability
    if section_signal(section) and re.search(r"eligibilit|pre[\s-]?qualif|qualification", section or "", re.I):
        return "eligibility"
    if COMMERCIAL.search(text):
        return "commercial"
    if FORMAT.search(text):
        return "format"
    return "technical"
