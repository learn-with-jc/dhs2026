# sentinel_x/phase3_agentic/run_phase3.py
"""
Sentinel-X | Phase 3 — Standalone Runner

Runs REVIEW_NEEDED PRs (from Phase 2) through the
LangGraph multi-agent reasoning pipeline.

Usage:
    python -m sentinel_x.phase3_agentic.run_phase3
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.settings       import PR_DIR, LOG_LEVEL
from config.logging_config import setup_logging, get_logger
from sentinel_x.platform.data_models import PurchaseRequisition, RiskLabel
from sentinel_x.phase3_agentic.graph.orchestrator import run_pr_through_graph

logger = get_logger(__name__)


def main() -> None:
    setup_logging(level=LOG_LEVEL)
    logger.info("═" * 60)
    logger.info("SENTINEL-X | PHASE 3 | Agentic Reasoning")
    logger.info("═" * 60)

    pr_file = PR_DIR / "sample_prs.json"
    raw     = json.loads(pr_file.read_text())
    all_prs = [PurchaseRequisition(**p) for p in raw]

    # Phase 3 processes REVIEW_NEEDED PRs from Phase 2
    review_prs = [
        p for p in all_prs
        if p.risk_label in (RiskLabel.REVIEW_NEEDED, RiskLabel.NON_COMPLIANT)
    ]
    logger.info(
        "Processing %d REVIEW_NEEDED PRs through agent graph",
        len(review_prs),
    )

    for pr in review_prs[:5]:   # limit for demo speed
        print(f"\n{'═'*65}")
        print(f"  Processing: {pr.pr_id} | {pr.vendor}")
        print(f"  Amount: {pr.currency}{pr.total_amount:,.2f}")
        print(f"{'═'*65}")

        final = run_pr_through_graph(pr.model_dump(), verbose=True)

        print(f"\n  VERDICT:    {final.get('verdict', 'UNKNOWN')}")
        print(f"  CONFIDENCE: {final.get('confidence_score', 0):.2f}")
        print(f"  ESCALATED:  {final.get('escalate_to_human', False)}")
        print(f"\n  RECOMMENDATION:")
        rec = final.get("recommendation", "")
        for line in rec.split("\n")[:15]:
            print(f"    {line}")

        trace = final.get("trace_log", [])
        print(f"\n  AGENT TRACE ({len(trace)} steps):")
        for event in trace:
            name = event.agent_name if hasattr(event, "agent_name") else event.get("agent_name","")
            conf = event.confidence if hasattr(event, "confidence") else event.get("confidence", 0)
            dur  = event.duration_ms if hasattr(event, "duration_ms") else event.get("duration_ms", 0)
            print(f"    [{name:<28}] conf={conf:.2f} | {dur:.0f}ms")


if __name__ == "__main__":
    main()