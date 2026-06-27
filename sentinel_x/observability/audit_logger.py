# sentinel_x/observability/audit_logger.py
"""
Sentinel-X | Observability — Audit Logger

Cross-cutting concern. Records every PR's journey through
the pipeline — which agents ran, what they decided,
how confident, how long.

Used by the Streamlit app's Audit Trail page.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sentinel_x.platform.data_models import (
    Phase1Result, Phase2Result, Phase3Result, DecisionRecord,
    PurchaseRequisition,
)

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Writes structured audit records for every PR processed.
    Each record is self-contained and queryable.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        self._session_log: list[dict] = []

    def log_pr_run(
        self,
        pr:        PurchaseRequisition,
        phase1:    Phase1Result | None     = None,
        phase2:    Phase2Result | None     = None,
        phase3:    dict | None             = None,   # SentinelState dict
        phase4:    DecisionRecord | None   = None,
    ) -> dict:
        """
        Log a complete PR run across all phases.
        Returns the structured audit record.
        """
        record: dict[str, Any] = {
            "audit_id":    f"AUD-{pr.pr_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "pr_id":       pr.pr_id,
            "vendor":      pr.vendor,
            "amount":      pr.total_amount,
            "currency":    pr.currency,
            "timestamp":   datetime.utcnow().isoformat(),
            "ground_truth": pr.risk_label.value,
            "phases":      {},
        }

        if phase1:
            record["phases"]["phase1"] = {
                "flagged":          phase1.flagged,
                "matched_keywords": phase1.matched_keywords,
                "processing_ms":    phase1.processing_time_ms,
            }

        if phase2:
            record["phases"]["phase2"] = {
                "llm_verdict":     phase2.llm_verdict.value,
                "final_verdict":   phase2.final_verdict.value,
                "confidence":      phase2.confidence,
                "guardrails_hit":  [
                    g.guardrail_name for g in phase2.guardrail_results
                    if g.triggered
                ],
                "processing_ms":   phase2.processing_time_ms,
            }

        if phase3:
            record["phases"]["phase3"] = {
                "verdict":          phase3.get("verdict"),
                "confidence":       phase3.get("confidence_score"),
                "retry_count":      phase3.get("retry_count"),
                "escalated":        phase3.get("escalate_to_human"),
                "agents_run":       [
                    t.get("agent_name") if isinstance(t, dict) else t.agent_name
                    for t in phase3.get("trace_log", [])
                ],
            }

        if phase4:
            record["phases"]["phase4"] = {
                "status":          phase4.status.value,
                "category":        phase4.primary_category.value,
                "recipient_type":  phase4.recipient_type.value,
                "findings":        len([c for c in phase4.policy_checks if not c.passed]),
                "audit_hash":      phase4.provenance.get("audit_hash", ""),
            }

        self._session_log.append(record)
        self._write(record)
        return record

    def _write(self, record: dict) -> None:
        fname = self.output_dir / f"{record['audit_id']}.json"
        fname.write_text(json.dumps(record, indent=2))

    def session_summary(self) -> dict:
        """Aggregate stats for the current session."""
        total = len(self._session_log)
        if total == 0:
            return {"total": 0}

        p4_statuses = [
            r["phases"].get("phase4", {}).get("status", "UNKNOWN")
            for r in self._session_log
        ]
        return {
            "total":         total,
            "compliant":     p4_statuses.count("COMPLIANT"),
            "finding":       p4_statuses.count("FINDING"),
            "non_compliant": p4_statuses.count("NON_COMPLIANT"),
        }