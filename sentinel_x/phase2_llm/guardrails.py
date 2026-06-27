# sentinel_x/phase2_llm/guardrails.py
"""
Sentinel-X | Phase 2 — Guardrails Layer

Deterministic checks that run BEFORE and AROUND the LLM.
Not everything should be an LLM decision.

Guardrails encode business rules that are:
  - Binary (either/or, no nuance needed)
  - High-stakes (cannot risk LLM getting it wrong)
  - Lookup-based (flagged suppliers, user history)
  - Mathematical (cost thresholds)

Architecture principle:
  Guardrails run first. If any trigger, the PR goes to
  REVIEW_NEEDED regardless of LLM output.
  The LLM cannot override a guardrail.
"""

from __future__ import annotations
import logging

from sentinel_x.platform.data_models import (
    PurchaseRequisition, GuardrailResult,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FLAGGED DATA (simulated lookups)
# In production: loaded from security systems
# ─────────────────────────────────────────────

FLAGGED_VENDORS = {
    "luxury gifts international",
    "prepaidcardhub",
    "eventpro experiences",
    "globalevents & hospitality",
    "globalevents and hospitality",
}

HIGH_RISK_COMMODITY_CODES = {
    "GIFTS-GOVT",
    "GIFT-CARDS",
}

# Simulated user history — repeat flagging pattern
USER_FLAG_HISTORY: dict[str, int] = {
    "thomas.black@acme.com":    2,
    "stephanie.cole@acme.com":  1,
}


# ─────────────────────────────────────────────
# INDIVIDUAL GUARDRAIL CHECKS
# ─────────────────────────────────────────────

def check_cost_threshold(pr: PurchaseRequisition) -> GuardrailResult:
    """
    🛡️ GUARDRAIL: Flag PRs above a hard cost threshold.
    Very high-value PRs warrant review regardless of
    what the LLM infers about their nature.
    """
    HARD_THRESHOLD = 10_000.0
    triggered = pr.total_amount > HARD_THRESHOLD
    return GuardrailResult(
        triggered      = triggered,
        guardrail_name = "cost_threshold",
        reason         = (
            f"Total amount {pr.currency} {pr.total_amount:,.2f} "
            f"exceeds hard review threshold of {pr.currency} {HARD_THRESHOLD:,.0f}"
        ) if triggered else "Amount within threshold",
        severity       = "high" if triggered else "none",
    )


def check_flagged_vendor(pr: PurchaseRequisition) -> GuardrailResult:
    """
    🛡️ GUARDRAIL: Check vendor against flagged vendor list.
    Known high-risk vendors trigger review regardless of
    purchase description.
    """
    vendor_lower = pr.vendor.lower().strip()
    triggered    = vendor_lower in FLAGGED_VENDORS
    return GuardrailResult(
        triggered      = triggered,
        guardrail_name = "flagged_vendor",
        reason         = (
            f"Vendor '{pr.vendor}' is on the flagged vendor list"
        ) if triggered else "Vendor not flagged",
        severity       = "high" if triggered else "none",
    )


def check_public_official(pr: PurchaseRequisition) -> GuardrailResult:
    """
    🛡️ GUARDRAIL: Known public officials trigger mandatory review.
    Zero-tolerance provision — no LLM inference needed.
    """
    triggered = pr.recipient_context.known_public_officials
    return GuardrailResult(
        triggered      = triggered,
        guardrail_name = "public_official",
        reason         = (
            "Known public officials are listed as recipients — "
            "mandatory compliance review required"
        ) if triggered else "No known public officials",
        severity       = "critical" if triggered else "none",
    )


def check_high_risk_commodity(pr: PurchaseRequisition) -> GuardrailResult:
    """
    🛡️ GUARDRAIL: Certain commodity codes are always high-risk.
    """
    triggered = pr.commodity_code in HIGH_RISK_COMMODITY_CODES
    return GuardrailResult(
        triggered      = triggered,
        guardrail_name = "high_risk_commodity",
        reason         = (
            f"Commodity code '{pr.commodity_code}' is a high-risk category"
        ) if triggered else "Commodity code standard risk",
        severity       = "medium" if triggered else "none",
    )


def check_user_history(pr: PurchaseRequisition) -> GuardrailResult:
    """
    🛡️ GUARDRAIL: Repeat submitters with prior flags get extra scrutiny.
    Past behaviour is a signal independent of current PR content.
    """
    prior_flags = USER_FLAG_HISTORY.get(pr.submitted_by, 0)
    triggered   = prior_flags >= 2
    return GuardrailResult(
        triggered      = triggered,
        guardrail_name = "user_history",
        reason         = (
            f"Submitter {pr.submitted_by} has {prior_flags} "
            f"prior compliance flags"
        ) if triggered else "No concerning submitter history",
        severity       = "medium" if triggered else "none",
    )


# ─────────────────────────────────────────────
# GUARDRAIL STACK
# ─────────────────────────────────────────────

class GuardrailStack:
    """
    Runs all guardrail checks and returns consolidated results.
    Any triggered guardrail overrides the LLM verdict.

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  SNIPPET: PPT-SLIDE-12 | Phase 2 | Guardrail Stack          ║
    # ║  STORY:   Some decisions should never be left to the LLM.   ║
    # ║           Guardrails run first. They cannot be overridden.  ║
    # ║  OUTPUT:  List of triggered guardrails — deterministic       ║
    # ║           safety net around LLM inference                   ║
    # ╚══════════════════════════════════════════════════════════════╝
    """

    CHECKS = [
        check_cost_threshold,
        check_flagged_vendor,
        check_public_official,
        check_high_risk_commodity,
        check_user_history,
    ]

    def evaluate(
        self, pr: PurchaseRequisition
    ) -> list[GuardrailResult]:
        """Run all guardrail checks. Return all results."""
        results = []
        for check_fn in self.CHECKS:
            result = check_fn(pr)
            if result.triggered:
                logger.info(
                    "Guardrail TRIGGERED | %s | %s | %s",
                    pr.pr_id, result.guardrail_name, result.severity,
                )
            results.append(result)

        # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
        triggered = [r for r in results if r.triggered]               #◄
        # └─────────────────────────────────────────────────────────────┘

        # 🛡️ GUARDRAIL: log aggregate — any trigger = mandatory review
        if triggered:
            logger.warning(
                "%s | %d guardrail(s) triggered: %s",
                pr.pr_id,
                len(triggered),
                [r.guardrail_name for r in triggered],
            )
        return results

# SPEAKER NOTE (PPT-SLIDE-12):
#
# WHAT TO SAY (not read):
#   "These five checks run before the LLM sees the PR and
#    their result cannot be overridden by the LLM verdict.
#    Known public officials? Always review — no inference needed.
#    Flagged vendor? Always review. Amount over $10,000?
#    Always review. The LLM is powerful but it's also stochastic.
#    For binary, high-stakes, lookup-based decisions we use
#    deterministic code. This is the architectural principle
#    that carries all the way through to Phase 4."
#
# POINT AT:     triggered = [r for r in results if r.triggered]
# TRANSITION TO: "Now let's see the inversion pattern —
#                 the insight that actually moved the needle
#                 on false positives..."
# AVOID SAYING: "As you can see in line 7..."