# sentinel_x/phase4_audit/recipient_classifier.py
"""
Sentinel-X | Phase 4 — Recipient Classifier

Determines recipient type and sector level for threshold lookup.
Pure deterministic logic — no LLM.

Recipient type drives which policy thresholds apply:
  employee          → $75/head meals, $150 single gift
  customer_private  → $150/head meals, $150 single gift
  customer_public   → country-specific hard caps
  known_official    → 50% of country cap, zero tolerance on procurement
"""

from __future__ import annotations
import logging

from sentinel_x.platform.data_models import (
    PurchaseRequisition, RecipientType, SectorLevel,
)

logger = logging.getLogger(__name__)

# Country → sector level mapping
COUNTRY_SECTOR_MAP: dict[str, SectorLevel] = {
    "US": SectorLevel.US_LEVEL1,
    "KR": SectorLevel.KR_LEVEL2,
    "IN": SectorLevel.STANDARD,
    "SG": SectorLevel.STANDARD,
}


def classify_recipient(
    pr: PurchaseRequisition,
) -> tuple[RecipientType, SectorLevel]:
    """
    Classify the primary recipient type and sector level.
    Returns (RecipientType, SectorLevel) tuple.
    """
    ctx = pr.recipient_context

    # 🛡️ GUARDRAIL: known public officials → strictest path
    if ctx.known_public_officials:
        sector = COUNTRY_SECTOR_MAP.get(
            ctx.country_code, SectorLevel.STANDARD
        )
        logger.info(
            "Recipient: CUSTOMER_PUBLIC (known official) | sector=%s",
            sector.value,
        )
        return RecipientType.CUSTOMER_PUBLIC, sector

    if ctx.includes_public_sector:
        sector = COUNTRY_SECTOR_MAP.get(
            ctx.country_code, SectorLevel.STANDARD
        )
        logger.info(
            "Recipient: CUSTOMER_PUBLIC | sector=%s", sector.value
        )
        return RecipientType.CUSTOMER_PUBLIC, sector

    if ctx.includes_customers and ctx.external_count > 0:
        logger.info("Recipient: CUSTOMER_PRIVATE")
        return RecipientType.CUSTOMER_PRIVATE, SectorLevel.STANDARD

    if ctx.employee_count > 0 and ctx.external_count == 0:
        logger.info("Recipient: EMPLOYEE (internal only)")
        return RecipientType.EMPLOYEE, SectorLevel.STANDARD

    # Default: treat as employee
    logger.info("Recipient: EMPLOYEE (default)")
    return RecipientType.EMPLOYEE, SectorLevel.STANDARD