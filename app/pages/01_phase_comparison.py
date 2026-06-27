# app/pages/01_phase_comparison.py
"""
Sentinel-X | Page 1 — Phase Comparison

Runs the same PR through all 4 phases and shows
outputs side by side. The evolution made visible.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components.pr_selector  import pr_selector_widget
from app.components.verdict_card import verdict_card

st.title("📊 Phase Comparison")
st.markdown(
    "Run the same Purchase Requisition through all four phases "
    "and compare outputs side-by-side."
)
st.markdown("---")

pr = pr_selector_widget("Select a PR to analyse")

if pr and st.button("▶ Run All Phases", type="primary"):
    st.markdown("---")

    # Phase 1
    with st.spinner("Phase 1: Keyword detection..."):
        from sentinel_x.phase1_keyword.keyword_engine import KeywordEngine
        engine  = KeywordEngine()
        r1      = engine.evaluate(pr)

    # Phase 2
    with st.spinner("Phase 2: LLM compliance filter..."):
        from sentinel_x.phase2_llm.compliance_filter import ComplianceFilter
        p2      = ComplianceFilter()
        r2      = p2.evaluate(pr)

    # Phase 4 (deterministic — always runs)
    with st.spinner("Phase 4: Deterministic audit..."):
        from sentinel_x.phase4_audit.rule_engine    import AuditRuleEngine
        from sentinel_x.phase4_audit.explainability import format_decision_record
        engine4 = AuditRuleEngine()
        r4      = engine4.evaluate(pr)

    st.markdown("## Results")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 🔤 Phase 1")
        st.markdown("*Keyword Detection*")
        verdict_card(
            verdict     = "FLAGGED" if r1.flagged else "CLEAR",
            phase_label = "Pattern Matching",
            extra       = f"Keywords: {', '.join(r1.matched_keywords[:3]) or 'none'}",
        )
        if r1.matched_keywords:
            st.caption(f"Matched {len(r1.matched_keywords)} keyword(s)")

    with col2:
        st.markdown("### 🤖 Phase 2")
        st.markdown("*LLM Filter (Inversion)*")
        verdict_card(
            verdict     = r2.final_verdict.value,
            confidence  = r2.confidence,
            phase_label = "Prompt Engineering",
        )
        guardrails_hit = [g.guardrail_name for g in r2.guardrail_results if g.triggered]
        if guardrails_hit:
            st.warning(f"⚡ Guardrails: {', '.join(guardrails_hit)}")
        with st.expander("LLM Reasoning"):
            st.write(r2.llm_reasoning)

    with col3:
        st.markdown("### 📋 Phase 4")
        st.markdown("*Deterministic Audit*")
        verdict_card(
            verdict     = r4.status.value,
            phase_label = "Rule Engine",
        )
        if r4.reasons:
            st.markdown("**Findings:**")
            for reason in r4.reasons:
                st.caption(f"• {reason}")
        if r4.actions:
            st.markdown("**Actions:**")
            for action in r4.actions:
                st.caption(f"→ {action}")

    st.markdown("---")
    st.markdown("### 📄 Ground Truth")
    col_gt1, col_gt2 = st.columns(2)
    with col_gt1:
        st.metric("Actual Risk Label", pr.risk_label.value)
        st.metric("Category", pr.ground_truth_category.value)
    with col_gt2:
        st.info(f"**Ground truth reason:** {pr.ground_truth_reason}")