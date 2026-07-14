# sentinel_x/phase4_audit/threshold_engine.py
"""
Sentinel-X | Phase 4 — Threshold Engine

Pure math. No LLM. No inference.
Checks spend amounts against policy thresholds.

This is the layer where compliance becomes binary:
either the number is over the threshold or it isn't.
No model should be making this decision.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass

from sentinel_x.platform.data_models import (
    PurchaseRequisition, IncentiveCategory,
    RecipientType, SectorLevel, PolicyCheckResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ThresholdCheckResult:
    rule_id:          str
    passed:           bool
    threshold:        float
    actual_value:     float
    finding:          str
    severity:         str


def check_meal_per_head(
    pr:            PurchaseRequisition,
    recipient:     RecipientType,
    sector:        SectorLevel,
) -> ThresholdCheckResult:
    """
    Check per-head meal cost against applicable threshold.

    
    """
    from config.settings import THRESHOLDS

    cpp = pr.cost_per_person  # Computed property on PR model

    # Select threshold by recipient type and sector
    if recipient == RecipientType.CUSTOMER_PUBLIC:
        sector_thresholds = THRESHOLDS["customer_public"]
        threshold = sector_thresholds.get(
            sector.value, sector_thresholds["default"]
        )["meal_per_head"]
        # 🛡️ GUARDRAIL: known officials get 50% of country cap
        if pr.recipient_context.known_public_officials:
            threshold = threshold * 0.5
    elif recipient == RecipientType.CUSTOMER_PRIVATE:
        threshold = THRESHOLDS["customer_private"]["meal_per_head"]
    else:
        threshold = THRESHOLDS["employee"]["meal_per_head"]

    # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
    passed = cpp <= threshold                                       #◄
    # └─────────────────────────────────────────────────────────────┘

    finding = (
        f"Cost per person {pr.currency}{cpp:.2f} exceeds "
        f"{recipient.value} threshold of {pr.currency}{threshold:.2f}"
    ) if not passed else ""

    return ThresholdCheckResult(
        rule_id      = "POL-003-PH",
        passed       = passed,
        threshold    = threshold,
        actual_value = cpp,
        finding      = finding,
        severity     = "high" if not passed else "none",
    )


def check_total_approval(
    pr:        PurchaseRequisition,
    recipient: RecipientType,
) -> ThresholdCheckResult:
    """Check if total event cost requires prior written approval."""
    from config.settings import THRESHOLDS

    if recipient == RecipientType.CUSTOMER_PUBLIC:
        threshold = 100.0
    elif recipient == RecipientType.CUSTOMER_PRIVATE:
        threshold = THRESHOLDS["customer_private"]["meal_total_prior_approval"]
    else:
        threshold = THRESHOLDS["employee"]["meal_total_prior_approval"]

    passed  = pr.total_amount <= threshold
    finding = (
        f"Total {pr.currency}{pr.total_amount:,.2f} exceeds "
        f"{pr.currency}{threshold:,.2f} — prior written approval required"
    ) if not passed else ""

    return ThresholdCheckResult(
        rule_id      = "POL-003-TOT",
        passed       = passed,
        threshold    = threshold,
        actual_value = pr.total_amount,
        finding      = finding,
        severity     = "medium" if not passed else "none",
    )


def check_gift_threshold(
    pr:        PurchaseRequisition,
    recipient: RecipientType,
    sector:    SectorLevel,
) -> ThresholdCheckResult:
    """Check per-unit gift value against threshold."""
    from config.settings import THRESHOLDS

    unit_value = pr.total_amount / max(pr.quantity, 1)

    if recipient == RecipientType.CUSTOMER_PUBLIC:
        sector_thresholds = THRESHOLDS["customer_public"]
        threshold = sector_thresholds.get(
            sector.value, sector_thresholds["default"]
        )["single_gift"]
        if pr.recipient_context.known_public_officials:
            threshold = threshold * 0.5
    elif recipient == RecipientType.CUSTOMER_PRIVATE:
        threshold = THRESHOLDS["customer_private"]["single_gift"]
    else:
        threshold = THRESHOLDS["employee"]["single_gift"]

    passed  = unit_value <= threshold
    finding = (
        f"Gift value {pr.currency}{unit_value:.2f}/unit exceeds "
        f"threshold {pr.currency}{threshold:.2f} for {recipient.value}"
    ) if not passed else ""

    return ThresholdCheckResult(
        rule_id      = "POL-001-GIFT",
        passed       = passed,
        threshold    = threshold,
        actual_value = unit_value,
        finding      = finding,
        severity     = "high" if not passed else "none",
    )

