# app/pages/04_metrics_dashboard.py
"""
Sentinel-X | Page 4 — Metrics Dashboard

Runs all 30 PRs through Phase 1 and Phase 2 and
shows the improvement in false positive rate and
analyst workload.
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.title("📈 Metrics Dashboard")
st.markdown(
    "Phase-over-phase improvement in false positive rate "
    "and analyst review workload."
)

if st.button("▶ Run Batch Evaluation (all 30 PRs)", type="primary"):
    from config.settings import PR_DIR
    from sentinel_x.platform.data_models     import PurchaseRequisition
    from sentinel_x.phase1_keyword.keyword_engine import KeywordEngine
    from sentinel_x.phase2_llm.compliance_filter  import ComplianceFilter
    from sentinel_x.phase1_keyword.false_positive_tracker import (
        compute_phase1_metrics, compute_phase2_metrics, PhaseComparison,
    )

    raw  = json.loads((PR_DIR / "sample_prs.json").read_text())
    prs  = [PurchaseRequisition(**p) for p in raw]

    with st.spinner("Phase 1: keyword scan..."):
        p1_engine  = KeywordEngine()
        p1_results = p1_engine.evaluate_batch(prs)
        p1_metrics = compute_phase1_metrics(prs, p1_results)

    with st.spinner("Phase 2: LLM filter... (may take 1-2 minutes)"):
        p2_filter  = ComplianceFilter()
        p2_results = p2_filter.evaluate_batch(prs)
        p2_metrics = compute_phase2_metrics(prs, p2_results)

    # Metrics cards
    st.markdown("---")
    st.markdown("### Phase Comparison")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Phase 1 — Keyword")
        st.metric("False Positive Rate",
                  f"{p1_metrics.false_positive_rate:.1%}")
        st.metric("Analyst Workload",
                  f"{p1_metrics.analyst_workload_ratio:.1%}")
        st.metric("Precision", f"{p1_metrics.precision:.1%}")
        st.metric("Recall",    f"{p1_metrics.recall:.1%}")

    with col2:
        st.markdown("#### Phase 2 — LLM Filter")
        fpr_delta = -(p1_metrics.false_positive_rate - p2_metrics.false_positive_rate)
        wl_delta  = -(p1_metrics.analyst_workload_ratio - p2_metrics.analyst_workload_ratio)
        st.metric("False Positive Rate",
                  f"{p2_metrics.false_positive_rate:.1%}",
                  delta=f"{fpr_delta:.1%}", delta_color="inverse")
        st.metric("Analyst Workload",
                  f"{p2_metrics.analyst_workload_ratio:.1%}",
                  delta=f"{wl_delta:.1%}", delta_color="inverse")
        st.metric("Precision", f"{p2_metrics.precision:.1%}")
        st.metric("Recall",    f"{p2_metrics.recall:.1%}")

    # Bar chart
    st.markdown("---")
    st.markdown("### False Positive Rate by Phase")
    import pandas as pd
    chart_data = pd.DataFrame({
        "Phase":   ["Phase 1\nKeyword", "Phase 2\nLLM Filter"],
        "FPR (%)": [
            round(p1_metrics.false_positive_rate * 100, 1),
            round(p2_metrics.false_positive_rate * 100, 1),
        ],
    }).set_index("Phase")
    st.bar_chart(chart_data)

    # Confusion summary
    st.markdown("---")
    st.markdown("### PR Classification Detail")
    detail_rows = []
    for pr, r1, r2 in zip(prs, p1_results, p2_results):
        detail_rows.append({
            "PR ID":     pr.pr_id,
            "Vendor":    pr.vendor[:20],
            "Actual":    pr.risk_label.value,
            "Phase 1":   "FLAG" if r1.flagged else "CLEAR",
            "Phase 2":   r2.final_verdict.value[:8],
            "P2 Conf":   f"{r2.confidence:.2f}",
            "P1 Match":  "✓" if (pr.risk_label.value!="COMPLIANT") == r1.flagged else "✗",
            "P2 Match":  "✓" if (pr.risk_label.value!="COMPLIANT") == (r2.final_verdict.value!="COMPLIANT") else "✗",
        })
    st.dataframe(pd.DataFrame(detail_rows), use_container_width=True)