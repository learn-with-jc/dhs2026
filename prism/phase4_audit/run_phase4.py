# prism/phase4_audit/run_phase4.py
"""
PRism | Phase 4 — Standalone Runner

Usage:
    python -m prism.phase4_audit.run_phase4
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.settings       import PR_DIR, AUDIT_LOG_DIR, LOG_LEVEL
from config.logging_config import setup_logging, get_logger
from prism.platform.data_models import PurchaseRequisition, DecisionRecord
from prism.platform.observability import PhaseCache
from prism.phase4_audit.rule_engine     import AuditRuleEngine
from prism.phase4_audit.explainability  import (
    format_decision_record, emit_decision_log,
)

logger = get_logger(__name__)


def main() -> None:
    setup_logging(level=LOG_LEVEL)
    logger.info("═" * 60)
    logger.info("PRISM | PHASE 4 | Deterministic Audit Engine")
    logger.info("═" * 60)

    pr_file = PR_DIR / "sample_prs.json"
    raw     = json.loads(pr_file.read_text())
    prs     = [PurchaseRequisition(**p) for p in raw]

    cache      = PhaseCache()
    engine     = AuditRuleEngine()
    statuses   = {"COMPLIANT": 0, "FINDING": 0, "NON_COMPLIANT": 0}
    cache_hits = 0

    for pr in prs:
        pr_data = pr.model_dump(mode="json")
        cached  = cache.get(pr.pr_id, 4, pr_data)
        if cached:
            record = DecisionRecord.model_validate(cached)
            cache_hits += 1
        else:
            record = engine.evaluate(pr)
            cache.set(pr.pr_id, 4, pr_data, record.model_dump(mode="json"))
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
    print(f"  Cache hits          : {cache_hits}/{len(prs)}")
    print("═" * 50)


if __name__ == "__main__":
    main()