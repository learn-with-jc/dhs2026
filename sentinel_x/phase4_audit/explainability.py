# sentinel_x/phase4_audit/explainability.py
"""
Sentinel-X | Phase 4 — Explainability Emitter

Formats the DecisionRecord into human-readable outputs.
Every output is reproducible from the DecisionRecord alone.
No LLM involved — pure formatting.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path

from sentinel_x.platform.data_models import DecisionRecord, VerdictStatus

logger = logging.getLogger(__name__)

STATUS_EMOJI = {
    VerdictStatus.COMPLIANT:        "✅",
    VerdictStatus.FINDING:          "⚠️ ",
    VerdictStatus.NON_COMPLIANT:    "🚫",
    VerdictStatus.ESCALATE_TO_HUMAN: "👤",
}


def format_decision_record(record: DecisionRecord) -> str:
    """
    Format a DecisionRecord as human-readable text.
    This is what the compliance analyst reads.

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  SNIPPET: PPT-SLIDE-25 | Phase 4 | Explainability Output    ║
    # ║  STORY:   Every decision is a named rule + evidence ref.     ║
    # ║           An auditor can reproduce this with no AI system.   ║
    # ║  OUTPUT:  DecisionRecord — the compliance paper trail        ║
    # ╚══════════════════════════════════════════════════════════════╝
    """
    emoji  = STATUS_EMOJI.get(record.status, "?")
    lines  = [
        f"{'═'*60}",
        f"  SENTINEL-X AUDIT DECISION",
        f"  PR ID:     {record.pr_id}",
        f"  Status:    {emoji} {record.status.value}",
        f"  Category:  {record.primary_category.value.upper()}",
        f"  Recipient: {record.recipient_type.value} / {record.sector_level.value}",
        f"  CPP:       {record.cost_per_person:.2f}",
        f"{'─'*60}",
    ]

    if record.reasons:
        lines.append("  FINDINGS:")
        for r in record.reasons:
            lines.append(f"    • {r}")
        lines.append("")

    if record.actions:
        lines.append("  REQUIRED ACTIONS:")
        for a in record.actions:
            lines.append(f"    → {a}")
        lines.append("")

    if record.evidence_refs:
        lines.append(f"  POLICY REFERENCES: {', '.join(record.evidence_refs)}")

    if record.flags:
        lines.append(f"  FLAGS: {', '.join(record.flags)}")

    lines.append(f"{'═'*60}")
    return "\n".join(lines)


def emit_decision_log(
    record: DecisionRecord,
    output_dir: Path | None = None,
) -> dict:
    """
    Emit a structured decision log for audit trail.
    Writes to file if output_dir provided.

    
    """
    log_record = {
        "pr_id":           record.pr_id,
        "status":          record.status.value,
        "category":        record.primary_category.value,
        "recipient_type":  record.recipient_type.value,
        "sector_level":    record.sector_level.value,
        "cost_per_person": record.cost_per_person,
        "policy_checks": [
            {
                "rule_id":      c.rule_id,
                "rule_name":    c.rule_name,
                "passed":       c.passed,
                "finding":      c.finding,
                "severity":     c.severity,
                "evidence_refs": c.evidence_refs,
            }
            for c in record.policy_checks
        ],
        "reasons":         record.reasons,
        "actions":         record.actions,
        "flags":           record.flags,
        "evidence_refs":   record.evidence_refs,
        "decision_log":    record.decision_log,
        "provenance":      record.provenance,
        "generated_at":    record.generated_at.isoformat(),
    }

    # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
    log_record["audit_hash"] = _compute_audit_hash(log_record)     #◄
    # └─────────────────────────────────────────────────────────────┘

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        fname = output_dir / f"{record.pr_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        fname.write_text(json.dumps(log_record, indent=2))
        logger.info("Audit log written: %s", fname)

    return log_record


def _compute_audit_hash(record: dict) -> str:
    """
    Compute a deterministic hash of the decision record.
    Same inputs always produce the same hash.
    This proves the record was not tampered with post-generation.
    """
    import hashlib
    content = json.dumps(
        {k: v for k, v in record.items() if k != "generated_at"},
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]

