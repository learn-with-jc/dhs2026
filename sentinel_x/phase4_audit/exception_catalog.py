# sentinel_x/phase4_audit/exception_catalog.py
"""
Sentinel-X | Phase 4 — Exception Catalog

Manages approved exceptions that override standard policy rules.
Exceptions are strictly enumerated — not inferred.

EXC-003: Dowlis platform charitable donation vouchers
EXC-007: Mobility devices with HR-documented medical need
"""

from __future__ import annotations
import logging

from sentinel_x.platform.data_models import PurchaseRequisition

logger = logging.getLogger(__name__)


def check_dowlis_exception(pr: PurchaseRequisition) -> bool:
    """
    EXC-003: Dowlis charitable vouchers are exempt from
    gift card restrictions. Check vendor name and commodity.
    """
    from config.settings import APPROVED_EXCEPTION_VENDORS
    vendor_lower = pr.vendor.lower()
    is_dowlis    = any(v in vendor_lower for v in APPROVED_EXCEPTION_VENDORS)
    has_charity_keyword = any(
        kw in pr.description.lower()
        for kw in ["charitable", "charity", "donation", "dowlis"]
    )
    applies = is_dowlis and has_charity_keyword
    if applies:
        logger.info("EXC-003 applies to %s", pr.pr_id)
    return applies


def check_mobility_device_exception(pr: PurchaseRequisition) -> bool:
    """
    EXC-007: Mobility devices with documented medical need are exempt.
    """
    has_mobility  = any(
        kw in (pr.description + " ".join(
            i.description for i in pr.item_details
        )).lower()
        for kw in ["mobility device", "ergonomic", "medical", "accommodation"]
    )
    is_medisupply = "medisupply" in pr.vendor.lower()
    applies = has_mobility and (is_medisupply or "mobility" in pr.commodity_code.lower())
    if applies:
        logger.info("EXC-007 applies to %s", pr.pr_id)
    return applies


def get_applicable_exceptions(pr: PurchaseRequisition) -> list[str]:
    """
    Return list of applicable exception IDs for a PR.
    Exceptions short-circuit standard policy checks.
    """
    exceptions = []
    if check_dowlis_exception(pr):
        exceptions.append("EXC-003")
    if check_mobility_device_exception(pr):
        exceptions.append("EXC-007")
    return exceptions