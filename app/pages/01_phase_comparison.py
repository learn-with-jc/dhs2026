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


# ─────────────────────────────────────────────
# Provider status banner
# ─────────────────────────────────────────────

def _provider_status() -> tuple[str, str]:
    """Returns (status, message) where status is 'ok'|'warning'|'error'."""
    from config.settings import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL, MODELS
    model = MODELS.get(LLM_PROVIDER, "unknown")

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-...") or len(OPENAI_API_KEY) < 10:
            return "error", "OpenAI API key not configured — Phases 2 & 3 will not produce real results. Set OPENAI_API_KEY in .env"
        return "ok", f"LLM provider: OpenAI ({model})"

    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY.startswith("sk-ant-...") or len(ANTHROPIC_API_KEY) < 10:
            return "error", "Anthropic API key not configured — Phases 2 & 3 will not produce real results. Set ANTHROPIC_API_KEY in .env"
        return "ok", f"LLM provider: Anthropic ({model})"

    if LLM_PROVIDER == "ollama":
        try:
            import httpx
            r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
            if r.status_code == 200:
                available = [m["name"].split(":")[0] for m in r.json().get("models", [])]
                if model.split(":")[0] not in available:
                    return "warning", (
                        f"Ollama is running but model '{model}' not found. "
                        f"Available: {', '.join(available)}. Run: ollama pull {model}"
                    )
                return "ok", f"LLM provider: Ollama — {model} @ {OLLAMA_BASE_URL}"
        except Exception:
            pass
        return "error", f"Ollama not reachable at {OLLAMA_BASE_URL} — start Ollama and ensure model '{model}' is pulled"

    return "warning", f"Unknown LLM provider '{LLM_PROVIDER}' — check .env"


def _show_provider_banner() -> bool:
    """Show provider status. Returns True if LLM is usable."""
    status, msg = _provider_status()
    if status == "ok":
        st.success(f"✅ {msg}")
        return True
    elif status == "warning":
        st.warning(f"⚠️ {msg}")
        return False
    else:
        st.error(f"🔴 {msg}")
        return False


# ─────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────

st.title("📊 Phase Comparison")
st.markdown(
    "Run the same Purchase Requisition through all four phases "
    "and compare outputs side-by-side."
)

llm_ok = _show_provider_banner()
st.markdown("---")

pr = pr_selector_widget("Select a PR to analyse")

if pr and st.button("▶ Run All Phases", type="primary"):
    st.markdown("---")

    # ── Phase 1 ───────────────────────────────────────────────
    with st.spinner("Phase 1: Keyword detection..."):
        from sentinel_x.phase1_keyword.keyword_engine import KeywordEngine
        r1 = KeywordEngine().evaluate(pr)

    # ── Phase 2 ───────────────────────────────────────────────
    r2 = None
    p2_error = None
    if not llm_ok:
        p2_error = "LLM provider not configured — skipped"
    else:
        with st.spinner("Phase 2: LLM compliance filter..."):
            try:
                from sentinel_x.phase2_llm.compliance_filter import ComplianceFilter
                r2 = ComplianceFilter().evaluate(pr)
                if r2.confidence == 0.0 and "LLM unavailable" in r2.llm_reasoning:
                    p2_error = f"LLM call failed: {r2.llm_reasoning}"
                    r2 = None
            except Exception as exc:
                p2_error = str(exc)

    # ── Phase 3 ───────────────────────────────────────────────
    r3 = None
    p3_error = None
    if not llm_ok:
        p3_error = "LLM provider not configured — skipped"
    else:
        with st.spinner("Phase 3: Agentic reasoning (8 agents)... this takes ~30s"):
            try:
                from sentinel_x.phase3_agentic.graph.orchestrator import run_pr_through_graph
                r3 = run_pr_through_graph(pr.model_dump(), verbose=False)
            except Exception as exc:
                p3_error = str(exc)

    # ── Phase 4 ───────────────────────────────────────────────
    with st.spinner("Phase 4: Deterministic audit..."):
        from sentinel_x.phase4_audit.rule_engine    import AuditRuleEngine
        from sentinel_x.phase4_audit.explainability import format_decision_record
        r4 = AuditRuleEngine().evaluate(pr)

    # ── Results ───────────────────────────────────────────────
    st.markdown("## Results")
    col1, col2, col3, col4 = st.columns(4)

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
        if p2_error:
            st.error(f"Phase 2 failed:\n{p2_error}")
        else:
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
        st.markdown("### 🔗 Phase 3")
        st.markdown("*Agentic Reasoning*")
        if p3_error:
            st.error(f"Phase 3 failed:\n{p3_error}")
        else:
            verdict = r3.get("verdict", "UNKNOWN") if isinstance(r3, dict) else getattr(r3, "verdict", "UNKNOWN")
            conf    = r3.get("confidence_score", 0.0) if isinstance(r3, dict) else getattr(r3, "confidence_score", 0.0)
            if conf > 1.0:  # LLM sometimes returns percentage (0-100) instead of decimal (0-1)
                conf = conf / 100.0
            escalated = r3.get("escalate_to_human", False) if isinstance(r3, dict) else getattr(r3, "escalate_to_human", False)
            rec     = r3.get("recommendation", "") if isinstance(r3, dict) else getattr(r3, "recommendation", "")
            trace   = r3.get("trace_log", []) if isinstance(r3, dict) else getattr(r3, "trace_log", [])

            verdict_str = verdict.value if hasattr(verdict, "value") else str(verdict)
            verdict_card(
                verdict     = verdict_str,
                confidence  = conf,
                phase_label = "LangGraph Agents",
            )
            if escalated:
                st.warning("⬆️ Escalated to human review")
            st.caption(f"Agents executed: {len(trace)}")
            if rec:
                with st.expander("Recommendation"):
                    st.write(rec[:500])

    with col4:
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
