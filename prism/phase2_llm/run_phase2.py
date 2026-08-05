# prism/phase2_llm/run_phase2.py
"""
PRism | Phase 2 — Standalone Runner

Usage:
    python -m prism.phase2_llm.run_phase2
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.settings       import PR_DIR, LOG_LEVEL
from config.logging_config import setup_logging, get_logger
from prism.platform.data_models import PurchaseRequisition, Phase2Result
from prism.platform.observability import PhaseCache
from prism.phase2_llm.compliance_filter import ComplianceFilter
from prism.phase1_keyword.keyword_engine import KeywordEngine
from prism.phase1_keyword.false_positive_tracker import (
    compute_phase1_metrics,
    compute_phase2_metrics,
    PhaseComparison,
)

logger = get_logger(__name__)


def main() -> None:
    setup_logging(level=LOG_LEVEL)
    logger.info("═" * 60)
    logger.info("PRISM | PHASE 2 | LLM Compliance Filter")
    logger.info("═" * 60)

    pr_file = PR_DIR / "sample_prs.json"
    raw     = json.loads(pr_file.read_text())
    prs     = [PurchaseRequisition(**p) for p in raw]

    # Phase 1 baseline
    p1_engine  = KeywordEngine()
    p1_results = p1_engine.evaluate_batch(prs)
    p1_metrics = compute_phase1_metrics(prs, p1_results)

    # Phase 2 (cached per PR — set() only on success, so a failed
    # LLM call is retried next run instead of being frozen)
    logger.info("Running Phase 2 compliance filter on %d PRs...", len(prs))
    cache      = PhaseCache()
    p2_filter  = ComplianceFilter()
    p2_results = []
    cache_hits = 0
    for pr in prs:
        pr_data = pr.model_dump(mode="json")
        cached  = cache.get(pr.pr_id, 2, pr_data)
        if cached:
            p2_results.append(Phase2Result.model_validate(cached))
            cache_hits += 1
        else:
            result = p2_filter.evaluate(pr)
            cache.set(pr.pr_id, 2, pr_data, result.model_dump(mode="json"))
            p2_results.append(result)
    logger.info("Phase 2 cache: %d/%d hits", cache_hits, len(prs))
    p2_metrics = compute_phase2_metrics(prs, p2_results)

    # Print results
    print("\n" + "─" * 75)
    print(f"  {'PR ID':<15} {'Vendor':<22} {'P1':^8} {'P2':^8} {'Actual':<15} {'Conf'}")
    print("─" * 75)

    for pr, r1, r2 in zip(prs, p1_results, p2_results):
        p1_str = "FLAG" if r1.flagged else "CLEAR"
        p2_str = r2.final_verdict.value[:5]
        actual = pr.risk_label.value[:12]
        match  = "✓" if (
            (pr.risk_label.value != "COMPLIANT") ==
            (r2.final_verdict.value != "COMPLIANT")
        ) else "✗"
        print(
            f"  {pr.pr_id:<15} {pr.vendor[:20]:<22} "
            f"{p1_str:^8} {p2_str:^8} {actual:<15} "
            f"{r2.confidence:.2f} {match}"
        )
    print("─" * 75)

    # Phase comparison
    comparison = PhaseComparison()
    comparison.add(p1_metrics)
    comparison.add(p2_metrics)
    comparison.print_comparison()

    improvement = comparison.improvement("phase1", "phase2")
    print(f"  FPR reduction:      {improvement.get('fpr_reduction', 0):.1%}")
    print(f"  Workload reduction: {improvement.get('workload_reduction', 0):.1%}")
    print(f"  Precision gain:     {improvement.get('precision_gain', 0):.1%}")
    print()

    # Show guardrail activity
    triggered_any = [
        (pr, r) for pr, r in zip(prs, p2_results)
        if any(g.triggered for g in r.guardrail_results)
    ]
    if triggered_any:
        print(f"  GUARDRAILS TRIGGERED ({len(triggered_any)} PRs):")
        for pr, r in triggered_any:
            fired = [g.guardrail_name for g in r.guardrail_results if g.triggered]
            print(f"  ⚠  {r.pr_id} | {pr.vendor[:30]} | {fired}")
    print()


if __name__ == "__main__":
    main()