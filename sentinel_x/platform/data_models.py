# sentinel_x/platform/data_models.py
"""
Sentinel-X | Core Data Models
All Pydantic v2 models used across all four phases.
Single source of truth for data structures.
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────

class RiskLabel(str, Enum):
    COMPLIANT             = "COMPLIANT"
    REVIEW_NEEDED         = "REVIEW_NEEDED"
    NON_COMPLIANT         = "NON_COMPLIANT"
    ESCALATE_TO_HUMAN     = "ESCALATE_TO_HUMAN"

class IncentiveCategory(str, Enum):
    MEALS                 = "meals"
    GIFTS                 = "gifts"
    SPONSORSHIP           = "sponsorship"
    GIFT_CARDS            = "gift_cards"
    TRAVEL                = "travel"
    OTHER                 = "other"

class RecipientType(str, Enum):
    EMPLOYEE              = "employee"
    CONTRACTOR            = "contractor"
    CUSTOMER_PRIVATE      = "customer_private"
    CUSTOMER_PUBLIC       = "customer_public"
    PARTNER               = "partner"
    UNKNOWN               = "unknown"

class SectorLevel(str, Enum):
    US_LEVEL1             = "US_Level1"
    KR_LEVEL2             = "KR_Level2"
    STANDARD              = "standard"
    UNKNOWN               = "unknown"

class VerdictStatus(str, Enum):
    COMPLIANT             = "COMPLIANT"
    FINDING               = "FINDING"
    NON_COMPLIANT         = "NON_COMPLIANT"
    ESCALATE_TO_HUMAN     = "ESCALATE_TO_HUMAN"


# ─────────────────────────────────────────────
# PR SUB-MODELS
# ─────────────────────────────────────────────

class ItemDetail(BaseModel):
    description: str
    amount: float
    quantity: int = 1

class Attachment(BaseModel):
    filename: str
    file_type: str = Field(
        description="quote | invoice | contract | other"
    )
    simulated_content: str = Field(
        description="Synthetic text content standing in for real attachment"
    )

class RecipientContext(BaseModel):
    includes_customers:     bool  = False
    includes_public_sector: bool  = False
    employee_count:         int   = 0
    external_count:         int   = 0
    known_public_officials: bool  = False
    country_code:           str   = "US"


# ─────────────────────────────────────────────
# CORE PR MODEL
# ─────────────────────────────────────────────

class PurchaseRequisition(BaseModel):
    """
    A Purchase Requisition (PR) submitted for compliance review.
    NOTE: PR = Purchase Requisition throughout Sentinel-X.
          This is NOT a code pull request.
    """
    pr_id:              str
    submitted_by:       str
    submission_date:    date
    vendor:             str
    total_amount:       float
    currency:           str             = "USD"
    quantity:           int             = 1
    description:        str
    commodity_code:     str
    short_name:         str
    item_details:       list[ItemDetail]
    attachments:        list[Attachment] = Field(default_factory=list)
    recipient_context:  RecipientContext = Field(
                            default_factory=RecipientContext
                        )

    # Ground truth — used for evaluation and metrics only
    risk_label:             RiskLabel
    ground_truth_category:  IncentiveCategory
    ground_truth_reason:    str

    @model_validator(mode="after")
    def validate_amount(self) -> PurchaseRequisition:
        if self.total_amount <= 0:
            raise ValueError("total_amount must be positive")
        return self

    @property
    def cost_per_person(self) -> float:
        total_people = (
            self.recipient_context.employee_count
            + self.recipient_context.external_count
        )
        if total_people > 0:
            return round(self.total_amount / total_people, 2)
        return self.total_amount

    @property
    def full_text(self) -> str:
        """Concatenated text for keyword/LLM analysis."""
        parts = [
            self.short_name,
            self.description,
            self.commodity_code,
            self.vendor,
            " ".join(i.description for i in self.item_details),
            " ".join(a.simulated_content for a in self.attachments),
        ]
        return " ".join(parts)


# ─────────────────────────────────────────────
# POLICY MODELS
# ─────────────────────────────────────────────

class PolicyChunk(BaseModel):
    chunk_id:       str
    policy_id:      str
    policy_name:    str
    section:        str
    content:        str
    category:       IncentiveCategory
    version:        str     = "1.0"
    effective_date: date    = Field(default_factory=date.today)
    keywords:       list[str] = Field(default_factory=list)

class PolicyDocument(BaseModel):
    policy_id:      str
    policy_name:    str
    version:        str
    effective_date: date
    category:       IncentiveCategory
    content:        str
    chunks:         list[PolicyChunk] = Field(default_factory=list)


# ─────────────────────────────────────────────
# PRECEDENT MODEL
# ─────────────────────────────────────────────

class Precedent(BaseModel):
    precedent_id:   str
    pr_summary:     str
    decision:       RiskLabel
    policy_refs:    list[str]
    rationale:      str
    reviewer:       str
    decision_date:  date
    category:       IncentiveCategory
    amount:         float
    recipient_type: RecipientType = RecipientType.UNKNOWN


# ─────────────────────────────────────────────
# PHASE 1 OUTPUT
# ─────────────────────────────────────────────

class Phase1Result(BaseModel):
    pr_id:              str
    matched_keywords:   list[str]
    flagged:            bool
    flag_reason:        str = ""
    processing_time_ms: float = 0.0


# ─────────────────────────────────────────────
# PHASE 2 OUTPUT
# ─────────────────────────────────────────────

class GuardrailResult(BaseModel):
    triggered:      bool
    guardrail_name: str
    reason:         str
    severity:       str = "medium"

class Phase2Result(BaseModel):
    pr_id:              str
    llm_verdict:        RiskLabel
    llm_reasoning:      str
    identified_items:   list[str]    = Field(default_factory=list)
    guardrail_results:  list[GuardrailResult] = Field(default_factory=list)
    model_used:         str          = ""
    confidence:         float        = 0.0
    processing_time_ms: float        = 0.0
    final_verdict:      RiskLabel    = RiskLabel.REVIEW_NEEDED

    @model_validator(mode="after")
    def resolve_final_verdict(self) -> Phase2Result:
        """
        Guardrail override: if any guardrail triggers,
        escalate regardless of LLM verdict.
        """
        if any(g.triggered for g in self.guardrail_results):
            self.final_verdict = RiskLabel.REVIEW_NEEDED
        else:
            self.final_verdict = self.llm_verdict
        return self


# ─────────────────────────────────────────────
# PHASE 3 — AGENT TRACE EVENT
# ─────────────────────────────────────────────

class TraceEvent(BaseModel):
    agent_name:     str
    timestamp:      datetime = Field(default_factory=datetime.utcnow)
    input_summary:  str
    output_summary: str
    confidence:     float   = 0.0
    tokens_used:    int     = 0
    duration_ms:    float   = 0.0
    notes:          str     = ""

class RetrievedChunk(BaseModel):
    chunk_id:       str
    policy_id:      str
    content:        str
    dense_score:    float = 0.0
    sparse_score:   float = 0.0
    rerank_score:   float = 0.0
    is_cited:       bool  = False


# ─────────────────────────────────────────────
# PHASE 3 OUTPUT
# ─────────────────────────────────────────────

class Phase3Result(BaseModel):
    pr_id:                  str
    extracted_intent:       dict[str, Any]  = Field(default_factory=dict)
    matched_policies:       list[str]       = Field(default_factory=list)
    retrieved_chunks:       list[RetrievedChunk] = Field(default_factory=list)
    initial_reasoning:      str             = ""
    critique_output:        str             = ""
    confidence_score:       float           = 0.0
    retry_count:            int             = 0
    verdict:                RiskLabel       = RiskLabel.REVIEW_NEEDED
    evidence:               list[RetrievedChunk] = Field(default_factory=list)
    recommendation:         str             = ""
    escalated_to_human:     bool            = False
    trace_log:              list[TraceEvent] = Field(default_factory=list)


# ─────────────────────────────────────────────
# PHASE 4 OUTPUT
# ─────────────────────────────────────────────

class PolicyCheckResult(BaseModel):
    rule_id:        str
    rule_name:      str
    passed:         bool
    finding:        str = ""
    evidence_refs:  list[str] = Field(default_factory=list)
    severity:       str = "medium"

class DecisionRecord(BaseModel):
    """
    The final, fully explainable output of the Sentinel-X pipeline.
    Every field maps to a named rule or evidence source.
    Designed to be reproducible: same input always produces same output.
    """
    pr_id:              str
    status:             VerdictStatus
    primary_category:   IncentiveCategory
    recipient_type:     RecipientType
    sector_level:       SectorLevel
    cost_per_person:    float
    policy_checks:      list[PolicyCheckResult] = Field(default_factory=list)
    reasons:            list[str]               = Field(default_factory=list)
    actions:            list[str]               = Field(default_factory=list)
    flags:              list[str]               = Field(default_factory=list)
    evidence_refs:      list[str]               = Field(default_factory=list)
    decision_log:       list[str]               = Field(default_factory=list)
    provenance:         dict[str, Any]          = Field(default_factory=dict)
    phase3_verdict:     RiskLabel | None        = None
    generated_at:       datetime = Field(default_factory=datetime.utcnow)

    def is_clean(self) -> bool:
        return self.status == VerdictStatus.COMPLIANT