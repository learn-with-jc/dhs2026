# sentinel_x/phase4_audit/rule_engine.py
"""
Sentinel-X | Phase 4 — Master Rule Engine

Orchestrates all deterministic checks.
Produces the final DecisionRecord.

Sequence:
  1. Check exceptions (may short-circuit all checks)
  2. Classify recipient and sector
  3. Normalize taxonomy
  4. Run threshold checks
  5. Run registration / approval checks
  6. Run public sector checks
  7. Compute status
  8. Emit DecisionRecord
"""

from __future__ import annotations
import logging

from sentinel_x.platform.data_models import (
    PurchaseRequisition, DecisionRecord, VerdictStatus,
    PolicyCheckResult, IncentiveCategory, RecipientType,
)
from sentinel_x.phase3_agentic.state import SentinelState
from sentinel_x.phase4_audit.taxonomy          import resolve_taxonomy
from sentinel_x.phase4_audit.recipient_classifier import classify_recipient
from sentinel_x.phase4_audit.threshold_engine  import (
    check_meal_per_head, check_total_approval, check_gift_threshold,
)
from sentinel_x.phase4_audit.registration_checker import (
    check_gsmm_registration, check_approval_level, check_public_sector_legal,
)
from sentinel_x.phase4_audit.exception_catalog import get_applicable_exceptions

logger = logging.getLogger(__name__)


class AuditRuleEngine:
    """
    Deterministic audit engine.
    Same input always produces same output.
    Every decision maps to a named rule and policy reference.
    """

    def evaluate(
        self,
        pr:             PurchaseRequisition,
        phase3_state:   SentinelState | None = None,
    ) -> DecisionRecord:
        """
        Run the full deterministic audit pipeline.
        Optionally ingests Phase 3 agent output as additional signal.
        """
        decision_log: list[str] = []
        policy_checks: list[PolicyCheckResult] = []
        flags:         list[str] = []

        decision_log.append(f"Audit started for {pr.pr_id}")
        decision_log.append(f"Vendor: {pr.vendor} | Amount: {pr.currency}{pr.total_amount:,.2f}")

        # Step 1: Check exceptions
        exceptions = get_applicable_exceptions(pr)
        if exceptions:
            decision_log.append(f"Exceptions apply: {exceptions} — standard checks bypassed")
            return self._build_compliant_record(pr, exceptions, decision_log)

        # Step 2: Classify recipient and sector
        recipient, sector = classify_recipient(pr)
        decision_log.append(f"Recipient: {recipient.value} | Sector: {sector.value}")

        # Step 3: Normalize taxonomy
        # Merge Phase 3 intent categories + commodity code as signal
        llm_cats    = []
        static_cats = [pr.commodity_code.lower()]

        if phase3_state:
            intent = phase3_state.get("extracted_intent", {})
            llm_cats = [intent.get("inferred_category", "other")]
            decision_log.append(f"Phase 3 category signal: {llm_cats}")

        tax = resolve_taxonomy(llm_cats or [pr.ground_truth_category.value], static_cats)
        primary_cat = tax.primary_category
        decision_log.append(f"Primary category: {primary_cat.value} (confidence={tax.confidence:.2f})")

        # Step 4: Threshold checks
        if primary_cat == IncentiveCategory.MEALS:
            meal_check = check_meal_per_head(pr, recipient, sector)
            policy_checks.append(PolicyCheckResult(
                rule_id       = meal_check.rule_id,
                rule_name     = "Meal Per-Head Threshold",
                passed        = meal_check.passed,
                finding       = meal_check.finding,
                evidence_refs = ["POL-003"],
                severity      = meal_check.severity,
            ))
            total_check = check_total_approval(pr, recipient)
            policy_checks.append(PolicyCheckResult(
                rule_id       = total_check.rule_id,
                rule_name     = "Total Approval Threshold",
                passed        = total_check.passed,
                finding       = total_check.finding,
                evidence_refs = ["POL-003"],
                severity      = total_check.severity,
            ))

        elif primary_cat in (IncentiveCategory.GIFTS, IncentiveCategory.GIFT_CARDS):
            gift_check = check_gift_threshold(pr, recipient, sector)
            policy_checks.append(PolicyCheckResult(
                rule_id       = gift_check.rule_id,
                rule_name     = "Gift Value Threshold",
                passed        = gift_check.passed,
                finding       = gift_check.finding,
                evidence_refs = ["POL-001", "POL-004"],
                severity      = gift_check.severity,
            ))

            # 🛡️ GUARDRAIL: gift cards to public sector = always non-compliant
            if (
                primary_cat == IncentiveCategory.GIFT_CARDS
                and recipient == RecipientType.CUSTOMER_PUBLIC
            ):
                flags.append("GIFT_CARD_PUBLIC_SECTOR_PROHIBITION")
                policy_checks.append(PolicyCheckResult(
                    rule_id       = "POL-004-PUB",
                    rule_name     = "Gift Card Public Sector Prohibition",
                    passed        = False,
                    finding       = "Gift cards/vouchers to public sector are PROHIBITED with no exceptions",
                    evidence_refs = ["POL-004 Section 4"],
                    severity      = "critical",
                ))

        elif primary_cat == IncentiveCategory.SPONSORSHIP:
            gsmm_check = check_gsmm_registration(pr, primary_cat)
            policy_checks.append(gsmm_check)

        # Step 5: Approval level check
        approval_check = check_approval_level(pr, primary_cat)
        if not approval_check.passed:
            policy_checks.append(approval_check)

        # Step 6: Public sector legal review
        ps_check = check_public_sector_legal(pr)
        if ps_check:
            policy_checks.append(ps_check)

        # Step 7: Compute final status
        status = self._compute_status(policy_checks, flags, pr)
        decision_log.append(f"Final status: {status.value}")

        # Step 8: Build reasons and actions
        reasons = [c.finding for c in policy_checks if not c.passed and c.finding]
        actions = self._build_actions(policy_checks, flags, pr)

        return DecisionRecord(
            pr_id            = pr.pr_id,
            status           = status,
            primary_category = primary_cat,
            recipient_type   = recipient,
            sector_level     = sector,
            cost_per_person  = pr.cost_per_person,
            policy_checks    = policy_checks,
            reasons          = reasons,
            actions          = actions,
            flags            = flags,
            evidence_refs    = list({
                ref
                for c in policy_checks
                for ref in c.evidence_refs
            }),
            decision_log     = decision_log,
            provenance       = {
                "taxonomy_source":   tax.priority_winner,
                "exceptions_checked": True,
                "phase3_ingested":    phase3_state is not None,
            },
            phase3_verdict   = None,
        )

    def _compute_status(
        self,
        checks: list[PolicyCheckResult],
        flags:  list[str],
        pr:     PurchaseRequisition,
    ) -> VerdictStatus:
        """Compute final status from all check results."""
        if "GIFT_CARD_PUBLIC_SECTOR_PROHIBITION" in flags:
            return VerdictStatus.NON_COMPLIANT

        if pr.recipient_context.known_public_officials and any(
            c.severity == "critical" for c in checks
        ):
            return VerdictStatus.NON_COMPLIANT

        failed = [c for c in checks if not c.passed]
        if not failed:
            return VerdictStatus.COMPLIANT

        critical = [c for c in failed if c.severity == "critical"]
        if critical:
            return VerdictStatus.NON_COMPLIANT

        return VerdictStatus.FINDING

    def _build_actions(
        self,
        checks: list[PolicyCheckResult],
        flags:  list[str],
        pr:     PurchaseRequisition,
    ) -> list[str]:
        """Build concrete action items from findings."""
        actions = []
        for check in checks:
            if not check.passed:
                if "GSMM" in check.rule_id:
                    actions.append("Complete GSMM registration before proceeding")
                elif "LEGAL" in check.rule_id:
                    actions.append("Submit for Legal review — do not proceed without approval")
                elif "VP" in check.rule_id or "SVP" in check.rule_id:
                    actions.append(f"Obtain {check.rule_name} before any commitment")
                elif "PH" in check.rule_id:
                    actions.append("Reduce per-head spend or obtain prior approval")
                elif "GCT" in check.rule_id or "GIFT" in check.rule_id:
                    actions.append("Review gift value against policy and recipient type")
                else:
                    actions.append(f"Resolve: {check.rule_name}")

        if "GIFT_CARD_PUBLIC_SECTOR_PROHIBITION" in flags:
            actions.insert(0, "IMMEDIATE ACTION: Cancel gift card order — prohibited to public sector")

        return actions

    def _build_compliant_record(
        self,
        pr:         PurchaseRequisition,
        exceptions: list[str],
        decision_log: list[str],
    ) -> DecisionRecord:
        from sentinel_x.platform.data_models import RecipientType, SectorLevel
        return DecisionRecord(
            pr_id            = pr.pr_id,
            status           = VerdictStatus.COMPLIANT,
            primary_category = pr.ground_truth_category,
            recipient_type   = RecipientType.EMPLOYEE,
            sector_level     = SectorLevel.STANDARD,
            cost_per_person  = pr.cost_per_person,
            reasons          = [f"Exception applies: {e}" for e in exceptions],
            actions          = ["Retain exception documentation on file"],
            flags            = [f"EXCEPTION:{e}" for e in exceptions],
            evidence_refs    = [f"Exception Catalog {e}" for e in exceptions],
            decision_log     = decision_log,
            provenance       = {"exception_applied": exceptions},
        )