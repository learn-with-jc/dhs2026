# sentinel_x/phase4_audit/registration_checker.py
"""
Sentinel-X | Phase 4 — Registration & Approval Checker

Checks whether required registrations and approvals
are in place based on PR type and amount.

GSMM: Global Sponsorship Management & Monitoring
GTE:  Global Third-party Engagement
EAT:  Exception Approval Tool
"""

from __future__ import annotations
import logging

from sentinel_x.platform.data_models import (
    PurchaseRequisition, IncentiveCategory, PolicyCheckResult,
)

logger = logging.getLogger(__name__)


def check_gsmm_registration(
    pr:       PurchaseRequisition,
    category: IncentiveCategory,
) -> PolicyCheckResult:
    """
    🛡️ GUARDRAIL: GSMM registration required for sponsorships >= $5,000.
    """
    from config.settings import SPONSORSHIP_THRESHOLDS
    threshold = SPONSORSHIP_THRESHOLDS["gsmm_required_above"]

    if category != IncentiveCategory.SPONSORSHIP:
        return PolicyCheckResult(
            rule_id  = "POL-002-GSMM",
            rule_name = "GSMM Registration",
            passed   = True,
            finding  = "Not applicable for this category",
        )

    requires_gsmm = pr.total_amount >= threshold

    if requires_gsmm:
        # In production: check GSMM system via API
        # For demo: flag as needing verification
        return PolicyCheckResult(
            rule_id       = "POL-002-GSMM",
            rule_name     = "GSMM Registration",
            passed        = False,
            finding       = (
                f"Sponsorship {pr.currency}{pr.total_amount:,.2f} "
                f">= {pr.currency}{threshold:,.0f} requires "
                f"GSMM registration before commitment"
            ),
            evidence_refs = ["POL-002 Section 4"],
            severity      = "high",
        )

    return PolicyCheckResult(
        rule_id   = "POL-002-GSMM",
        rule_name = "GSMM Registration",
        passed    = True,
        finding   = "Amount below GSMM threshold",
    )


def check_approval_level(
    pr:       PurchaseRequisition,
    category: IncentiveCategory,
) -> PolicyCheckResult:
    """
    Check if the appropriate approval level has been obtained.
    Approval requirements escalate with amount.
    """
    from config.settings import SPONSORSHIP_THRESHOLDS

    amount = pr.total_amount

    if category == IncentiveCategory.SPONSORSHIP:
        if amount >= SPONSORSHIP_THRESHOLDS["svp_legal_approval_above"]:
            required = "SVP + Legal review"
            rule     = "POL-002-SVP"
        elif amount >= SPONSORSHIP_THRESHOLDS["vp_approval_above"]:
            required = "VP approval"
            rule     = "POL-002-VP"
        else:
            required = "Director approval"
            rule     = "POL-002-DIR"
    else:
        if amount >= 5000:
            required = "VP approval"
            rule     = "POL-003-VP"
        elif amount >= 2000:
            required = "Director approval + Compliance log"
            rule     = "POL-003-DIR"
        elif amount >= 500:
            required = "Prior written approval"
            rule     = "POL-003-PWA"
        else:
            return PolicyCheckResult(
                rule_id   = "POL-APPROVAL",
                rule_name = "Approval Level",
                passed    = True,
                finding   = "No elevated approval required",
            )

    # In production: verify approval is on file
    # For demo: flag the requirement
    return PolicyCheckResult(
        rule_id       = rule,
        rule_name     = f"Approval: {required}",
        passed        = False,
        finding       = (
            f"Amount {pr.currency}{amount:,.2f} requires: {required}. "
            f"Verify approval is documented before processing."
        ),
        evidence_refs = ["POL-002 Section 3", "POL-003 Section 3"],
        severity      = "high" if "SVP" in required or "VP" in required else "medium",
    )


def check_public_sector_legal(
    pr: PurchaseRequisition,
) -> PolicyCheckResult | None:
    """
    🛡️ GUARDRAIL: Any engagement with public sector requires Legal review.
    Returns a check result only if public sector is involved.
    """
    ctx = pr.recipient_context
    if not (ctx.includes_public_sector or ctx.known_public_officials):
        return None

    severity = "critical" if ctx.known_public_officials else "high"
    return PolicyCheckResult(
        rule_id       = "POL-005-LEGAL",
        rule_name     = "Legal Review — Public Sector",
        passed        = False,
        finding       = (
            "Public sector recipients detected. "
            "Legal review is mandatory before any engagement. "
            + ("KNOWN PUBLIC OFFICIALS PRESENT — zero-tolerance provisions apply."
               if ctx.known_public_officials else "")
        ),
        evidence_refs = ["POL-005 Section 5"],
        severity      = severity,
    )