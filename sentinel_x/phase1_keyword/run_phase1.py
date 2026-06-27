# sentinel_x/phase1_keyword/run_phase1.py
"""
Sentinel-X | Phase 1 — Standalone Runner

Run this script to see Phase 1 keyword detection in action.
Loads all 30 synthetic PRs, evaluates each, prints metrics.

Usage:
    python -m sentinel_x.phase1_keyword.run_phase1
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.settings        import PR_DIR, LOG_LEVEL
from config.logging_config  import setup_logging, get_logger
from sentinel_x.platform.data_models import PurchaseRequisition
from sentinel_x.phase1_keyword.keyword_engine import KeywordEngine
from sentinel_x.phase1_keyword.false_positive_tracker import (
    compute_phase1_metrics, PhaseComparison,
)

logger = get_logger(__name__)


def load_prs(pr_file: Path) -> list[PurchaseRequisition]:
    raw = json.loads(pr_file.read_text(encoding="utf-8"))
    return [PurchaseRequisition(**pr) for pr in raw]


def main() -> None:
    setup_logging(level=LOG_LEVEL)
    logger.info("═" * 60)
    logger.info("SENTINEL-X | PHASE 1 | Keyword Detection")
    logger.info("═" * 60)

    # Load PRs
    pr_file = PR_DIR / "sample_prs.json"
    prs     = load_prs(pr_file)
    logger.info("Loaded %d purchase requisitions", len(prs))

    # Run keyword engine
    engine  = KeywordEngine()
    results = engine.evaluate_batch(prs)

    # Print individual results
    print("\n" + "─" * 70)
    print(f"  {'PR ID':<15} {'Vendor':<25} {'Flagged':<10} {'Keywords'}")
    print("─" * 70)
    for pr, r in zip(prs, results):
        flag_str = "⚠  YES" if r.flagged else "✓  NO"
        kw_str   = ", ".join(r.matched_keywords[:4])
        if len(r.matched_keywords) > 4:
            kw_str += f" (+{len(r.matched_keywords)-4} more)"
        print(f"  {r.pr_id:<15} {pr.vendor:<25} {flag_str:<10} {kw_str}")
    print("─" * 70)

    # Compute and display metrics
    metrics = compute_phase1_metrics(prs, results)
    print(metrics)

    # Show false positive examples (the problem made visible)
    fp_cases = [
        (pr, r) for pr, r in zip(prs, results)
        if r.flagged and pr.risk_label.value == "COMPLIANT"
    ]
    if fp_cases:
        print(f"\n  FALSE POSITIVES ({len(fp_cases)} clean PRs incorrectly flagged):")
        print("  " + "─" * 60)
        for pr, r in fp_cases[:5]:
            print(f"  ✗ {r.pr_id} | {pr.vendor}")
            print(f"    Keywords matched: {', '.join(r.matched_keywords[:3])}")
            print(f"    Actual category:  {pr.ground_truth_category.value}")
            print(f"    Why it's clean:   {pr.ground_truth_reason[:80]}...")
            print()

    # Comparison scaffold (Phase 2+ will add to this)
    comparison = PhaseComparison()
    comparison.add(metrics)
    logger.info(
        "Phase 1 complete | FPR=%.1f%% | analyst_load=%.1f%%",
        metrics.false_positive_rate * 100,
        metrics.analyst_workload_ratio * 100,
    )


if __name__ == "__main__":
    main()