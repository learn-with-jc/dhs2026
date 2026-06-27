# sentinel_x/phase1_keyword/false_positive_tracker.py
"""
Sentinel-X | False Positive Tracker

Computes and compares detection metrics across phases.
The core tension in Sentinel-X:
  - False Positives  = analyst time wasted
  - False Negatives  = compliance risk

In a dataset where <1% of PRs are non-compliant,
even a 10% FPR means analysts spend 90% of their
review time on clean PRs.

This tracker is used across all four phases to show
the improvement narrative.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Literal

from sentinel_x.platform.data_models import (
    PurchaseRequisition, RiskLabel,
    Phase1Result, Phase2Result,
)

logger = logging.getLogger(__name__)

PhaseLabel = Literal["phase1", "phase2", "phase3", "phase4"]


@dataclass
class DetectionMetrics:
    """
    Binary classification metrics focused on the
    analyst workload and compliance risk trade-off.
    """
    phase:              PhaseLabel
    total_prs:          int   = 0
    true_positives:     int   = 0   # Correctly flagged non-compliant
    false_positives:    int   = 0   # Clean PRs incorrectly flagged
    true_negatives:     int   = 0   # Correctly cleared as compliant
    false_negatives:    int   = 0   # Missed non-compliant PRs

    @property
    def false_positive_rate(self) -> float:
        """FPR = FP / (FP + TN) — proportion of clean PRs wasted."""
        denom = self.false_positives + self.true_negatives
        return round(self.false_positives / denom, 4) if denom else 0.0

    @property
    def false_negative_rate(self) -> float:
        """FNR = FN / (FN + TP) — proportion of violations missed."""
        denom = self.false_negatives + self.true_positives
        return round(self.false_negatives / denom, 4) if denom else 0.0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return round(self.true_positives / denom, 4) if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return round(self.true_positives / denom, 4) if denom else 0.0

    @property
    def analyst_workload_ratio(self) -> float:
        """
        Proportion of total PRs that land in the review queue.
        Lower is better — fewer PRs for analysts to manually review.
        """
        flagged = self.true_positives + self.false_positives
        return round(flagged / self.total_prs, 4) if self.total_prs else 0.0

    def summary(self) -> dict:
        return {
            "phase":                   self.phase,
            "total_prs":               self.total_prs,
            "flagged_for_review":      self.true_positives + self.false_positives,
            "true_positives":          self.true_positives,
            "false_positives":         self.false_positives,
            "true_negatives":          self.true_negatives,
            "false_negatives":         self.false_negatives,
            "false_positive_rate":     self.false_positive_rate,
            "false_negative_rate":     self.false_negative_rate,
            "precision":               self.precision,
            "recall":                  self.recall,
            "analyst_workload_ratio":  self.analyst_workload_ratio,
        }

    def __str__(self) -> str:
        s = self.summary()
        return (
            f"\n{'─'*50}\n"
            f"  Phase: {s['phase'].upper()}\n"
            f"  Total PRs:              {s['total_prs']}\n"
            f"  Flagged for review:     {s['flagged_for_review']}\n"
            f"  True Positives:         {s['true_positives']}\n"
            f"  False Positives:        {s['false_positives']}\n"
            f"  False Positive Rate:    {s['false_positive_rate']:.1%}\n"
            f"  False Negative Rate:    {s['false_negative_rate']:.1%}\n"
            f"  Precision:              {s['precision']:.1%}\n"
            f"  Recall:                 {s['recall']:.1%}\n"
            f"  Analyst Workload Ratio: {s['analyst_workload_ratio']:.1%}\n"
            f"{'─'*50}"
        )


# ─────────────────────────────────────────────
# METRIC COMPUTATION HELPERS
# ─────────────────────────────────────────────

def _ground_truth_is_violation(pr: PurchaseRequisition) -> bool:
    """
    A PR is a true violation if it is REVIEW_NEEDED or NON_COMPLIANT.
    COMPLIANT PRs are the true negatives.
    """
    return pr.risk_label in (
        RiskLabel.REVIEW_NEEDED,
        RiskLabel.NON_COMPLIANT,
    )


def compute_phase1_metrics(
    prs:     list[PurchaseRequisition],
    results: list[Phase1Result],
) -> DetectionMetrics:
    """
    Compute detection metrics for Phase 1 keyword engine output.
    """
    # ╔══════════════════════════════════════════════════════════════╗
    # ║  SNIPPET: PPT-SLIDE-09 | Phase 1 | False Positive Rate      ║
    # ║  STORY:   The single number that made us build Phase 2.      ║
    # ║           In a <1% non-compliant dataset, FPR is everything. ║
    # ║  OUTPUT:  FPR % — the analyst pain number                    ║
    # ╚══════════════════════════════════════════════════════════════╝

    metrics = DetectionMetrics(phase="phase1", total_prs=len(prs))

    for pr, result in zip(prs, results):
        is_violation  = _ground_truth_is_violation(pr)
        was_flagged   = result.flagged

        if is_violation and was_flagged:
            metrics.true_positives  += 1
        elif not is_violation and was_flagged:
            metrics.false_positives += 1
        elif not is_violation and not was_flagged:
            metrics.true_negatives  += 1
        else:
            metrics.false_negatives += 1

    # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
    fpr = metrics.false_positive_rate                               #◄
    # └─────────────────────────────────────────────────────────────┘

    logger.info(
        "Phase1 metrics | FPR=%.1f%% | FNR=%.1f%% | workload=%.1f%%",
        fpr * 100,
        metrics.false_negative_rate * 100,
        metrics.analyst_workload_ratio * 100,
    )
    return metrics

# SPEAKER NOTE (PPT-SLIDE-09):
#
# WHAT TO SAY (not read):
#   "This number — the false positive rate — is the one that
#    forced every architectural decision that follows.
#    When fewer than 1% of your PRs are actually non-compliant,
#    even a 40% false positive rate means analysts spend most
#    of their time reviewing clean PRs. The system was technically
#    working — it was catching violations — but it was creating
#    more work than it was saving. That's the moment we moved
#    to Phase 2."
#
# POINT AT:     fpr = metrics.false_positive_rate
# TRANSITION TO: "So in Phase 2 we made a counterintuitive call.
#                 Instead of getting better at finding violations,
#                 we tried to get better at finding clean PRs."
# AVOID SAYING: "As you can see in line 7..."


def compute_phase2_metrics(
    prs:     list[PurchaseRequisition],
    results: list[Phase2Result],
) -> DetectionMetrics:
    """Compute detection metrics for Phase 2 LLM output."""
    metrics = DetectionMetrics(phase="phase2", total_prs=len(prs))

    for pr, result in zip(prs, results):
        is_violation = _ground_truth_is_violation(pr)
        was_flagged  = result.final_verdict != RiskLabel.COMPLIANT

        if is_violation and was_flagged:
            metrics.true_positives  += 1
        elif not is_violation and was_flagged:
            metrics.false_positives += 1
        elif not is_violation and not was_flagged:
            metrics.true_negatives  += 1
        else:
            metrics.false_negatives += 1

    return metrics


# ─────────────────────────────────────────────
# CROSS-PHASE COMPARISON
# ─────────────────────────────────────────────

@dataclass
class PhaseComparison:
    """Side-by-side comparison of metrics across phases."""
    metrics: list[DetectionMetrics] = field(default_factory=list)

    def add(self, m: DetectionMetrics) -> None:
        self.metrics.append(m)

    def print_comparison(self) -> None:
        print("\n" + "═" * 70)
        print("  SENTINEL-X | PHASE-OVER-PHASE METRICS COMPARISON")
        print("═" * 70)
        headers = [
            "Metric", *[m.phase.upper() for m in self.metrics]
        ]
        rows = [
            ["FP Rate",        *[f"{m.false_positive_rate:.1%}"    for m in self.metrics]],
            ["FN Rate",        *[f"{m.false_negative_rate:.1%}"    for m in self.metrics]],
            ["Precision",      *[f"{m.precision:.1%}"              for m in self.metrics]],
            ["Recall",         *[f"{m.recall:.1%}"                 for m in self.metrics]],
            ["Analyst Load",   *[f"{m.analyst_workload_ratio:.1%}" for m in self.metrics]],
            ["Flagged",        *[str(m.true_positives + m.false_positives) for m in self.metrics]],
        ]
        col_w = 16
        print("  " + "  ".join(h.ljust(col_w) for h in headers))
        print("  " + "─" * (col_w * (len(headers) + 1)))
        for row in rows:
            print("  " + "  ".join(str(v).ljust(col_w) for v in row))
        print("═" * 70 + "\n")

    def improvement(
        self,
        from_phase: PhaseLabel,
        to_phase:   PhaseLabel,
    ) -> dict:
        """Compute improvement in key metrics between two phases."""
        from_m = next((m for m in self.metrics if m.phase == from_phase), None)
        to_m   = next((m for m in self.metrics if m.phase == to_phase),   None)
        if not from_m or not to_m:
            return {}
        return {
            "fpr_reduction":     round(from_m.false_positive_rate - to_m.false_positive_rate, 4),
            "workload_reduction": round(from_m.analyst_workload_ratio - to_m.analyst_workload_ratio, 4),
            "precision_gain":    round(to_m.precision - from_m.precision, 4),
        }