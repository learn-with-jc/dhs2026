# app/pages/04_metrics_dashboard.py
"""
PRism | Page 4 — Metrics Dashboard

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


def _get_cache():
    if "sx_cache" not in st.session_state:
        from prism.platform.observability import PhaseCache
        st.session_state.sx_cache = PhaseCache()
    return st.session_state.sx_cache


cache = _get_cache()

col_run, col_clear = st.columns([3, 1])
with col_run:
    run_clicked = st.button("▶ Run Batch Evaluation (all 30 PRs)", type="primary")
with col_clear:
    clear_clicked = st.button("🗑 Clear Cache", help="Force re-run of Phase 2 for all 30 PRs")

if clear_clicked:
    from config.settings import PR_DIR
    raw = json.loads((PR_DIR / "sample_prs.json").read_text())
    for p in raw:
        cache.invalidate(p["pr_id"])
    st.toast("Cache cleared for all 30 PRs", icon="🗑")

if run_clicked:
    from config.settings import PR_DIR
    from prism.platform.data_models     import PurchaseRequisition, Phase2Result, DecisionRecord
    from prism.phase1_keyword.keyword_engine import KeywordEngine
    from prism.phase2_llm.compliance_filter  import ComplianceFilter
    from prism.phase4_audit.rule_engine      import AuditRuleEngine
    from prism.phase1_keyword.false_positive_tracker import (
        compute_phase1_metrics, compute_phase2_metrics, compute_phase4_metrics, PhaseComparison,
    )

    raw  = json.loads((PR_DIR / "sample_prs.json").read_text())
    prs  = [PurchaseRequisition(**p) for p in raw]

    with st.spinner("Phase 1: keyword scan..."):
        p1_engine  = KeywordEngine()
        p1_results = p1_engine.evaluate_batch(prs)
        p1_metrics = compute_phase1_metrics(prs, p1_results)

    with st.spinner("Phase 2: LLM filter... (cached PRs are instant)"):
        p2_filter  = ComplianceFilter()
        p2_results = []
        p2_cache_hits = 0
        for pr in prs:
            pr_data = pr.model_dump(mode="json")
            cached  = cache.get(pr.pr_id, 2, pr_data)
            if cached:
                p2_results.append(Phase2Result.model_validate(cached))
                p2_cache_hits += 1
            else:
                result = p2_filter.evaluate(pr)
                cache.set(pr.pr_id, 2, pr_data, result.model_dump(mode="json"))
                p2_results.append(result)
        p2_metrics = compute_phase2_metrics(prs, p2_results)
    st.caption(f"📦 Phase 2 cache: {p2_cache_hits}/{len(prs)} hits")

    with st.spinner("Phase 4: deterministic audit... (cached PRs are instant)"):
        p4_engine  = AuditRuleEngine()
        p4_results = []
        p4_cache_hits = 0
        for pr in prs:
            pr_data = pr.model_dump(mode="json")
            cached  = cache.get(pr.pr_id, 4, pr_data)
            if cached:
                p4_results.append(DecisionRecord.model_validate(cached))
                p4_cache_hits += 1
            else:
                result = p4_engine.evaluate(pr)
                cache.set(pr.pr_id, 4, pr_data, result.model_dump(mode="json"))
                p4_results.append(result)
        p4_metrics = compute_phase4_metrics(prs, p4_results)
    st.caption(f"📦 Phase 4 cache: {p4_cache_hits}/{len(prs)} hits")

    # Metrics cards
    st.markdown("---")
    st.markdown("### Phase Comparison")
    st.caption(
        "Phase 3 is excluded here on purpose — it only processes the subset of PRs "
        "already escalated by Phase 2, so it isn't measured against all 30 PRs the "
        "same way. See the Agent Graph page for its per-PR escalation behaviour."
    )

    col1, col2, col3 = st.columns(3)
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

    with col3:
        st.markdown("#### Phase 4 — Deterministic")
        fpr_delta4 = -(p2_metrics.false_positive_rate - p4_metrics.false_positive_rate)
        wl_delta4  = -(p2_metrics.analyst_workload_ratio - p4_metrics.analyst_workload_ratio)
        st.metric("False Positive Rate",
                  f"{p4_metrics.false_positive_rate:.1%}",
                  delta=f"{fpr_delta4:.1%}", delta_color="inverse")
        st.metric("Analyst Workload",
                  f"{p4_metrics.analyst_workload_ratio:.1%}",
                  delta=f"{wl_delta4:.1%}", delta_color="inverse")
        st.metric("Precision", f"{p4_metrics.precision:.1%}")
        st.metric("Recall",    f"{p4_metrics.recall:.1%}")

    # Bar chart
    st.markdown("---")
    st.markdown("### False Positive Rate by Phase")
    import pandas as pd
    chart_data = pd.DataFrame({
        "Phase":   ["Phase 1\nKeyword", "Phase 2\nLLM Filter", "Phase 4\nDeterministic"],
        "FPR (%)": [
            round(p1_metrics.false_positive_rate * 100, 1),
            round(p2_metrics.false_positive_rate * 100, 1),
            round(p4_metrics.false_positive_rate * 100, 1),
        ],
    }).set_index("Phase")
    st.bar_chart(chart_data)

    # Confusion summary
    st.markdown("---")
    st.markdown("### PR Classification Detail")
    detail_rows = []
    for pr, r1, r2, r4 in zip(prs, p1_results, p2_results, p4_results):
        detail_rows.append({
            "PR ID":     pr.pr_id,
            "Vendor":    pr.vendor[:20],
            "Actual":    pr.risk_label.value,
            "Phase 1":   "FLAG" if r1.flagged else "CLEAR",
            "Phase 2":   r2.final_verdict.value,
            "P2 Conf":   f"{r2.confidence:.2f}",
            "Phase 4":   r4.status.value,
            "P1 Match":  "✓" if (pr.risk_label.value!="COMPLIANT") == r1.flagged else "✗",
            "P2 Match":  "✓" if (pr.risk_label.value!="COMPLIANT") == (r2.final_verdict.value!="COMPLIANT") else "✗",
            "P4 Match":  "✓" if (pr.risk_label.value!="COMPLIANT") == (r4.status.value!="COMPLIANT") else "✗",
        })
    st.dataframe(pd.DataFrame(detail_rows), use_container_width=True)