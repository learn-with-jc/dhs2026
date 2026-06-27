# sentinel_x/observability/metrics.py
"""
Sentinel-X | Observability — Cross-Phase Metrics

Aggregates and compares metrics across all four phases.
Powers the Streamlit metrics dashboard.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field

from sentinel_x.platform.data_models import PurchaseRequisition, RiskLabel
from sentinel_x.phase1_keyword.false_positive_tracker import (
    DetectionMetrics, PhaseComparison,
    compute_phase1_metrics, compute_phase2_metrics,
)

logger = logging.getLogger(__name__)


@dataclass
class SentinelMetrics:
    """Full metrics bundle for all phases."""
    phase1: DetectionMetrics | None = None
    phase2: DetectionMetrics | None = None
    latency_by_phase: dict[str, float] = field(default_factory=dict)

    def to_chart_data(self) -> dict:
        """Format for Streamlit chart rendering."""
        phases   = []
        fpr      = []
        workload = []
        precision = []

        for m in [self.phase1, self.phase2]:
            if m:
                phases.append(m.phase.upper())
                fpr.append(round(m.false_positive_rate * 100, 1))
                workload.append(round(m.analyst_workload_ratio * 100, 1))
                precision.append(round(m.precision * 100, 1))

        return {
            "phases":    phases,
            "fpr":       fpr,
            "workload":  workload,
            "precision": precision,
            "latency":   self.latency_by_phase,
        }