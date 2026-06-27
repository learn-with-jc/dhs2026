# sentinel_x/phase2_llm/compliance_filter.py
"""
Sentinel-X | Phase 2 — Compliance Filter (The Inversion Pattern)

The key insight of Phase 2:

In a dataset where <1% of PRs are non-compliant,
asking "is this PR non-compliant?" is the wrong question.

The LLM will produce false positives because ambiguous
language in clean PRs triggers compliance-adjacent patterns.

The inversion: ask "is this PR clearly compliant?"
Route everything that isn't clearly compliant to REVIEW_NEEDED.
This shrinks the review pool far more effectively than
trying to improve violation detection accuracy.

Before inversion: flagging 40% of PRs for review
After inversion:  flagging ~25% of PRs for review
  — with the same or better recall on true violations
"""

from __future__ import annotations
import logging
import time
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from sentinel_x.platform.data_models import (
    PurchaseRequisition, Phase2Result, RiskLabel,
)
from sentinel_x.platform.llm_provider import get_llm
from sentinel_x.phase2_llm.guardrails import GuardrailStack
from sentinel_x.phase2_llm.intent_extractor import (
    IntentExtractor, ExtractedIntent,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# STRUCTURED OUTPUT
# ─────────────────────────────────────────────

class ComplianceFilterOutput(BaseModel):
    is_clearly_compliant: bool  = Field(
        description=(
            "True ONLY if this PR is clearly and unambiguously "
            "compliant with standard procurement policies. "
            "False if there is any doubt or any hospitality/"
            "incentive component present."
        )
    )
    reasoning:        str   = Field(
        description="Brief explanation of why this is or is not clearly compliant"
    )
    identified_items: list[str] = Field(
        description="List of hospitality or incentive items identified"
    )
    confidence:       float = Field(
        description="Confidence in this assessment 0.0-1.0"
    )


# ─────────────────────────────────────────────
# THE INVERSION PROMPT
# This is the architectural shift — note the framing
# ─────────────────────────────────────────────

# ╔══════════════════════════════════════════════════════════════╗
# ║  SNIPPET: PPT-SLIDE-11 | Phase 2 | The Inversion Pattern    ║
# ║  STORY:   We stopped asking "is this non-compliant?"        ║
# ║           We started asking "is this clearly compliant?"    ║
# ║           Everything else becomes the review pool.          ║
# ║  OUTPUT:  is_clearly_compliant boolean — the inverted lens  ║
# ╚══════════════════════════════════════════════════════════════╝

IDENTIFY_COMPLIANT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a compliance pre-screening assistant. \
Your job is NOT to find violations. Your job is to identify \
purchase requisitions that are CLEARLY AND UNAMBIGUOUSLY COMPLIANT \
so they can be cleared from the review queue.

A PR is clearly compliant ONLY if ALL of the following are true:
- It contains NO meals, entertainment, hospitality, or dining components
- It contains NO gifts, hampers, prizes, or non-monetary rewards
- It contains NO sponsorship, event tickets, or hospitality packages
- It contains NO gift cards, vouchers, or prepaid cards
- It contains NO travel incentives or resort/retreat bookings
- It is a standard operational purchase (software, hardware, \
  services, training, logistics)

If there is ANY doubt — return is_clearly_compliant = false.
When in doubt, always route to review. Never assume compliance.

{format_instructions}"""),

    ("human", """Evaluate this purchase requisition:

PR ID:        {pr_id}
Vendor:       {vendor}
Amount:       {currency} {total_amount}
Description:  {description}
Items:        {item_details}
Commodity:    {commodity_code}
Attachments:  {attachment_content}
Intent Analysis: {intent_summary}
"""),
])


# ─────────────────────────────────────────────
# COMPLIANCE FILTER
# ─────────────────────────────────────────────

class ComplianceFilter:
    """
    Phase 2 compliance filter implementing the inversion pattern.
    Identifies clearly compliant PRs to shrink the review pool.
    """

    def __init__(self) -> None:
        self.llm             = get_llm()
        self.parser          = JsonOutputParser(
                                   pydantic_object=ComplianceFilterOutput
                               )
        self.guardrail_stack = GuardrailStack()
        self.intent_extractor = IntentExtractor()

        # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
        self.chain = IDENTIFY_COMPLIANT_PROMPT | self.llm | self.parser #◄
        # └─────────────────────────────────────────────────────────────┘

        logger.info("ComplianceFilter initialised with inversion pattern")

    def evaluate(self, pr: PurchaseRequisition) -> Phase2Result:
        """
        Evaluate a PR using the inversion pattern + guardrails.
        Returns Phase2Result with final verdict.
        """
        start_ms = time.time() * 1000

        # Step 1: Run guardrails first (deterministic)
        guardrail_results = self.guardrail_stack.evaluate(pr)

        # Step 2: Extract intent (LLM — structured)
        try:
            intent = self.intent_extractor.extract(pr)
            intent_summary = (
                f"Type: {intent.pr_type} | "
                f"Category: {intent.inferred_category} | "
                f"Items: {', '.join(intent.incentive_items[:3])} | "
                f"Flags: {', '.join(intent.flags[:2])}"
            )
            model_used = "intent_extractor"
        except Exception as exc:
            logger.warning("Intent extraction failed: %s", exc)
            intent        = None
            intent_summary = "Intent extraction unavailable"
            model_used     = "fallback"

        # Step 3: Apply inversion filter (LLM)
        attachment_text = " | ".join(
            a.simulated_content for a in pr.attachments
        ) or "No attachments"

        try:
            raw: dict[str, Any] = self.chain.invoke({
                "pr_id":               pr.pr_id,
                "vendor":              pr.vendor,
                "currency":            pr.currency,
                "total_amount":        pr.total_amount,
                "description":         pr.description,
                "item_details":        " | ".join(
                                           i.description
                                           for i in pr.item_details
                                       ),
                "commodity_code":      pr.commodity_code,
                "attachment_content":  attachment_text,
                "intent_summary":      intent_summary,
                "format_instructions": self.parser.get_format_instructions(),
            })
            filter_output = ComplianceFilterOutput(**raw)

        except Exception as exc:
            logger.error("Compliance filter LLM call failed: %s", exc)
            # 🛡️ GUARDRAIL: on LLM failure, default to REVIEW_NEEDED
            filter_output = ComplianceFilterOutput(
                is_clearly_compliant = False,
                reasoning            = f"LLM unavailable — defaulting to review: {exc}",
                identified_items     = [],
                confidence           = 0.0,
            )

        # Step 4: Resolve verdict
        llm_verdict = (
            RiskLabel.COMPLIANT
            if filter_output.is_clearly_compliant
            else RiskLabel.REVIEW_NEEDED
        )

        elapsed = (time.time() * 1000) - start_ms

        result = Phase2Result(
            pr_id             = pr.pr_id,
            llm_verdict       = llm_verdict,
            llm_reasoning     = filter_output.reasoning,
            identified_items  = filter_output.identified_items,
            guardrail_results = guardrail_results,
            model_used        = model_used,
            confidence        = filter_output.confidence,
            processing_time_ms = round(elapsed, 2),
        )

        logger.info(
            "Phase2 | %s | llm=%s | final=%s | conf=%.2f | %.0fms",
            pr.pr_id,
            result.llm_verdict.value,
            result.final_verdict.value,
            result.confidence,
            elapsed,
        )
        return result

    def evaluate_batch(
        self,
        prs: list[PurchaseRequisition],
    ) -> list[Phase2Result]:
        return [self.evaluate(pr) for pr in prs]

# SPEAKER NOTE (PPT-SLIDE-11):
#
# WHAT TO SAY (not read):
#   "Here's the prompt that changed everything. We're not asking
#    the LLM to find violations. We're asking it to confirm
#    compliance. The system prompt says: a PR is clearly compliant
#    ONLY IF it has none of these components. If there's any doubt,
#    return false. This means everything ambiguous goes to review —
#    which is exactly what a cautious analyst would do.
#    The review pool shrinks because clean PRs — software licenses,
#    hardware, logistics — get cleared immediately.
#    What's left is actually worth a human's time."
#
# POINT AT:     IDENTIFY_COMPLIANT_PROMPT and the chain assignment
# TRANSITION TO: "Let's look at the numbers — what did this
#                 actually do to our false positive rate?"
# AVOID SAYING: "As you can see in line 7..."