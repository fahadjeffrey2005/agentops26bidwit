"""Shared data shapes.

Rules:
- Every model is strict (unknown fields rejected) and frozen (cannot be edited after creation).
- Collections are tuples, so nothing inside a model can be changed in place either.
- Domain models (clauses, evidence, claims...) are added here only when the part
  that produces them is built and agreed.
"""
from __future__ import annotations

from datetime import date as date_
from datetime import datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION = "0.6.0"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- part results
ErrorKind = Literal["crash", "bad_output", "bad_input", "rejected"]


class Rejected(Exception):
    """Raised by a part that refuses its input on purpose (e.g. an unsafe file). Not a crash."""


class PartError(Strict):
    kind: ErrorKind
    type: str = Field(max_length=120)              # exception class name
    message: str = Field(max_length=500)           # truncated; never a traceback


T = TypeVar("T")


class PartResult(Strict, Generic[T]):
    """What every part returns through run_part: a value or an error, never an exception."""
    part: str = Field(min_length=1, max_length=40)
    ok: bool
    value: T | None = None
    error: PartError | None = None
    seconds: float = Field(ge=0)


# ---------------------------------------------------------------- audit trail
JsonScalar = str | int | float | bool | None


class AuditEvent(Strict):
    t: datetime = Field(default_factory=utc_now)
    part: str = Field(min_length=1, max_length=40)
    level: Literal["info", "warn", "error"] = "info"
    event: str = Field(min_length=1, max_length=500)
    data: dict[str, JsonScalar] = Field(default_factory=dict)


# ---------------------------------------------------------------- Part 2: extraction
ClauseId = Annotated[str, StringConstraints(pattern=r"^R-\d{3,4}$")]
ClauseKind = Literal["heading", "clause", "sub_item", "table_header", "table_row", "paragraph"]


class Source(Strict):
    file: str = Field(min_length=1, max_length=200)          # file name only, never a full path
    page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    clause_no: str | None = Field(default=None, max_length=30)


class Clause(Strict):
    """One unit of tender text. Extraction keeps every unit; deciding what is a requirement comes later."""
    id: ClauseId
    kind: ClauseKind
    text: str = Field(min_length=1, max_length=6000)
    source: Source
    section: str | None = Field(default=None, max_length=200)
    parent_id: ClauseId | None = None


PageFlag = Literal["scanned", "hidden_text", "unreadable"]


class PageNote(Strict):
    """Something a human must look at, shown at Gate A."""
    page: int = Field(ge=1)
    flag: PageFlag
    detail: str = Field(max_length=400)


class ExtractResult(Strict):
    file: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: int = Field(ge=1)
    clauses: tuple[Clause, ...]
    notes: tuple[PageNote, ...] = ()
    removed_lines: tuple[str, ...] = ()                       # repeated headers/footers that were dropped


# ---------------------------------------------------------------- Part 3: knowledge base
EvidenceId = Annotated[str, StringConstraints(pattern=r"^E-\d{3,4}$")]
Confidentiality = Literal["public", "internal", "restricted"]


class Evidence(Strict):
    """One company evidence record (data/kb/evidence.json)."""
    id: EvidenceId
    doc_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    client: str | None = Field(default=None, max_length=80)
    confidentiality: Confidentiality
    date: date_
    expires_on: date_ | None = None


class BlockedDoc(Strict):
    id: EvidenceId
    title: str = Field(max_length=200)
    reason: Literal["restricted", "expired"]
    detail: str = Field(max_length=200)


class EvidenceHit(Strict):
    evidence: Evidence
    rank: int = Field(ge=1)
    keyword_score: float = Field(ge=0)                 # BM25; 0 = no shared words
    meaning_score: float | None = None                 # cosine similarity; None in keyword-only mode
    missing_terms: tuple[str, ...] = ()                # required terms (ISO 27001, CCNP, 24x7...) not in this evidence
    found_by: Literal["search", "required_term"] = "search"   # required_term: added because it holds a term no top hit had


class Retrieval(Strict):
    clause_id: ClauseId
    required_terms: tuple[str, ...] = ()
    uncovered_terms: tuple[str, ...] = ()              # required terms found in none of the hits: a likely gap
    hits: tuple[EvidenceHit, ...] = ()


class RetrieveResult(Strict):
    mode: Literal["hybrid", "keyword"]
    mode_reason: str = Field(max_length=300)           # why keyword-only, if it is
    indexed: int = Field(ge=0)
    blocked: tuple[BlockedDoc, ...] = ()
    results: tuple[Retrieval, ...] = ()


# ---------------------------------------------------------------- Part 4: classification
Category = Literal["eligibility", "technical", "commercial", "format", "other"]
PassFailSignal = Literal["section", "wording", "ai"]


class ClauseLabel(Strict):
    """What one clause is. pass_fail = the bid is rejected at evaluation if this is not met.
    Any one signal is enough; a human confirms every pass/fail item at Gate A."""
    clause_id: ClauseId
    category: Category
    pass_fail: bool
    signals: tuple[PassFailSignal, ...] = ()
    labelled_by: Literal["ai", "rules", "template"]
    reason: str = Field(default="", max_length=300)


class ClassifyResult(Strict):
    mode: Literal["ai", "rules"]
    mode_reason: str = Field(default="", max_length=400)
    providers: tuple[str, ...] = ()                    # which AI providers actually answered
    ai_calls: int = Field(default=0, ge=0)
    labels: tuple[ClauseLabel, ...] = ()


# ---------------------------------------------------------------- Part 5: agents
ClaimId = Annotated[str, StringConstraints(pattern=r"^C-\d{3,4}$")]


class Requirement(Strict):
    """A clause plus its label, as the agents see it (built by the workflow from Part 2 + Part 4 output)."""
    id: ClauseId
    text: str = Field(min_length=1, max_length=6000)
    section: str | None = Field(default=None, max_length=200)
    page: int = Field(ge=1)
    category: Category
    pass_fail: bool


GapReason = Literal["no_evidence", "missing_terms", "human_decides", "over_draft_limit", "failed_checks", "ai_unavailable"]


class Gap(Strict):
    """A requirement the system could not answer from evidence. Never silent: shown to a human."""
    requirement_id: ClauseId
    reason: GapReason
    detail: str = Field(default="", max_length=300)


class Verdict(Strict):
    decision: Literal["go", "conditional", "no_go"]
    summary: str = Field(max_length=400)
    pass_fail_total: int = Field(ge=0)
    pass_fail_covered: int = Field(ge=0)
    blocking: tuple[Gap, ...] = ()


class Claim(Strict):
    id: ClaimId
    requirement_id: ClauseId
    text: str = Field(min_length=1, max_length=1500)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=600)      # verbatim words from the cited evidence


class Confirmation(Strict):
    """A scope duty answered with a standard compliance statement (no company evidence needed or found).
    Never shown as a cited claim: a person confirms these as one group at Gate B."""
    requirement_id: ClauseId
    statement: str = Field(min_length=1, max_length=300)


class Draft(Strict):
    claims: tuple[Claim, ...] = ()
    gaps: tuple[Gap, ...] = ()
    confirmations: tuple[Confirmation, ...] = ()
    mode: Literal["ai", "none"] = "ai"
    mode_reason: str = Field(default="", max_length=400)
    ai_calls: int = Field(default=0, ge=0)


CheckName = Literal["citation", "quote", "numbers", "overclaim", "blocked_source", "coverage"]


class CheckResult(Strict):
    target_id: str = Field(min_length=1, max_length=20)   # claim id, or requirement id for coverage
    check: CheckName
    passed: bool
    detail: str = Field(default="", max_length=300)


class CheckReport(Strict):
    results: tuple[CheckResult, ...] = ()
    failing_claims: tuple[ClaimId, ...] = ()
    silent_misses: tuple[ClauseId, ...] = ()             # requirements with neither a claim nor a gap: must be empty
