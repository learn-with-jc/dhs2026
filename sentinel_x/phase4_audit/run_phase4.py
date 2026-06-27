# sentinel_x/phase4_audit/run_phase4.py
"""
Sentinel-X | Phase 4 — Standalone Runner

Usage:
    python -m sentinel_x.phase4_audit.run_phase4
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.settings       import PR_DIR, AUDIT_LOG_DIR, LOG_LEVEL
from config.logging_config import setup_logging, get_logger
from sentinel_x.platform.data_models import PurchaseRequisition
from sentinel_x.phase4_audit.rule_engine     import AuditRuleEngine
from sentinel_x.phase4_audit.explainability  import (
    format_decision_record, emit_decision_log,
)

logger = get_logger(__name__)


def main() -> None:
    setup_logging(level=LOG_LEVEL)
    logger.info("═" * 60)
    logger.info("SENTINEL-X | PHASE 4 | Deterministic Audit Engine")
    logger.info("═" * 60)

    pr_file = PR_DIR / "sample_prs.json"
    raw     = json.loads(pr_file.read_text())
    prs     = [PurchaseRequisition(**p) for p in raw]

    engine   = AuditRuleEngine()
    statuses = {"COMPLIANT": 0, "FINDING": 0, "NON_COMPLIANT": 0}

    for pr in prs:
        record = engine.evaluate(pr)
        statuses[record.status.value] = statuses.get(record.status.value, 0) + 1

        # Print decision for interesting cases
        if record.status.value != "COMPLIANT" or pr.risk_label.value != "COMPLIANT":
            print(format_decision_record(record))

        # Emit audit log
        emit_decision_log(record, AUDIT_LOG_DIR)

    # Summary
    print("\n" + "═" * 50)
    print("  PHASE 4 AUDIT SUMMARY")
    print("─" * 50)
    for status, count in statuses.items():
        print(f"  {status:<20}: {count}")
    print("═" * 50)


if __name__ == "__main__":
    main()