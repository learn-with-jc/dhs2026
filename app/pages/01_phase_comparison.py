# app/pages/01_phase_comparison.py
"""
Sentinel-X | Page 1 — Phase Comparison

Runs the same PR through all 4 phases and shows
outputs side by side. The evolution made visible.

Caching: previously evaluated (pr_id, phase) pairs are loaded
from SQLite instead of re-running the LLM pipeline.

Tracing: LangSmith cloud when configured; local SQLite otherwise.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components.pr_selector  import pr_selector_widget
from app.components.verdict_card import verdict_card


# ─────────────────────────────────────────────
# Session-level setup  (once per browser session)
# ─────────────────────────────────────────────

def _get_callbacks() -> list:
    if "sx_callbacks" not in st.session_state:
        from sentinel_x.platform.observability import setup_tracing
        st.session_state.sx_callbacks = setup_tracing()
    return st.session_state.sx_callbacks


def _get_cache():
    if "sx_cache" not in st.session_state:
        from sentinel_x.platform.observability import PhaseCache
        st.session_state.sx_cache = PhaseCache()
    return st.session_state.sx_cache


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


def _tracing_badge() -> None:
    """Show which tracing backend is active."""
    from config.settings import ENABLE_LANGSMITH, LANGSMITH_API_KEY, LANGSMITH_PROJECT
    if ENABLE_LANGSMITH and LANGSMITH_API_KEY and len(LANGSMITH_API_KEY) > 20:
        st.caption(f"🔭 Tracing → LangSmith · project: {LANGSMITH_PROJECT}")
    else:
        from sentinel_x.platform.observability import DB_PATH
        st.caption(f"🗄️ Tracing → local SQLite · {DB_PATH.name}")


def _cache_badge(cache) -> None:
    """Show cache statistics."""
    stats = cache.stats()
    total = sum(stats.values())
    if total:
        detail = "  ".join(f"P{k[-1]}:{v}" for k, v in sorted(stats.items()))
        st.caption(f"📦 Cache: {total} stored entries ({detail})")


# ─────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────

st.title("📊 Phase Comparison")
st.markdown(
    "Run the same Purchase Requisition through all four phases "
    "and compare outputs side-by-side."
)

llm_ok    = _show_provider_banner()
callbacks = _get_callbacks()
cache     = _get_cache()

with st.expander("ℹ️ Observability", expanded=False):
    _tracing_badge()
    _cache_badge(cache)

st.markdown("---")

pr = pr_selector_widget("Select a PR to analyse")

col_run, col_clear = st.columns([3, 1])
with col_run:
    run_clicked = st.button("▶ Run All Phases", type="primary")
with col_clear:
    clear_clicked = st.button("🗑 Clear Cache", help="Force re-evaluation for this PR")

if pr and clear_clicked:
    cache.invalidate(pr.pr_id)
    st.toast(f"Cache cleared for {pr.pr_id}", icon="🗑")

if pr and run_clicked:
    st.markdown("---")
    pr_data = pr.model_dump(mode="json")

    # ── Phase 1 ───────────────────────────────────────────────────
    r1_cached = False
    cached1 = cache.get(pr.pr_id, 1, pr_data)
    if cached1:
        from sentinel_x.platform.data_models import Phase1Result
        r1 = Phase1Result.model_validate(cached1)
        r1_cached = True
    else:
        with st.spinner("Phase 1: Keyword detection..."):
            from sentinel_x.phase1_keyword.keyword_engine import KeywordEngine
            r1 = KeywordEngine().evaluate(pr)
        cache.set(pr.pr_id, 1, pr_data, r1.model_dump(mode="json"))

    # ── Phase 2 ───────────────────────────────────────────────────
    r2, p2_error, r2_cached = None, None, False
    if not llm_ok:
        p2_error = "LLM provider not configured — skipped"
    else:
        cached2 = cache.get(pr.pr_id, 2, pr_data)
        if cached2:
            from sentinel_x.platform.data_models import Phase2Result
            r2 = Phase2Result.model_validate(cached2)
            r2_cached = True
        else:
            with st.spinner("Phase 2: LLM compliance filter..."):
                try:
                    from sentinel_x.phase2_llm.compliance_filter import ComplianceFilter
                    r2 = ComplianceFilter().evaluate(pr, callbacks=callbacks)
                    if r2.confidence == 0.0 and "LLM unavailable" in r2.llm_reasoning:
                        p2_error = f"LLM call failed: {r2.llm_reasoning}"
                        r2 = None
                    else:
                        cache.set(pr.pr_id, 2, pr_data, r2.model_dump(mode="json"))
                except Exception as exc:
                    p2_error = str(exc)

    # ── Phase 3 ───────────────────────────────────────────────────
    r3, p3_error, r3_cached = None, None, False
    if not llm_ok:
        p3_error = "LLM provider not configured — skipped"
    else:
        cached3 = cache.get(pr.pr_id, 3, pr_data)
        if cached3:
            r3 = cached3          # plain dict — display code uses .get()
            r3_cached = True
        else:
            with st.spinner("Phase 3: Agentic reasoning (8 agents)... this takes ~30s"):
                try:
                    from sentinel_x.phase3_agentic.graph.orchestrator import run_pr_through_graph
                    r3_raw = run_pr_through_graph(pr.model_dump(), verbose=False, callbacks=callbacks)

                    # Normalise confidence (LLM sometimes returns 0–100 scale)
                    _conf = r3_raw.get("confidence_score", 0.0) if isinstance(r3_raw, dict) else 0.0
                    if _conf > 1.0:
                        _conf /= 100.0

                    r3 = {
                        "verdict":          r3_raw.get("verdict", "REVIEW_NEEDED") if isinstance(r3_raw, dict) else "REVIEW_NEEDED",
                        "confidence_score": _conf,
                        "escalate_to_human": r3_raw.get("escalate_to_human", False) if isinstance(r3_raw, dict) else False,
                        "recommendation":   r3_raw.get("recommendation", "") if isinstance(r3_raw, dict) else "",
                        "trace_log":        [
                            t.model_dump(mode="json") if hasattr(t, "model_dump") else t
                            for t in (r3_raw.get("trace_log", []) if isinstance(r3_raw, dict) else [])
                        ],
                    }
                    cache.set(pr.pr_id, 3, pr_data, r3)
                except Exception as exc:
                    p3_error = str(exc)

    # ── Phase 4 ───────────────────────────────────────────────────
    r4_cached = False
    cached4 = cache.get(pr.pr_id, 4, pr_data)
    if cached4:
        from sentinel_x.platform.data_models import DecisionRecord
        r4 = DecisionRecord.model_validate(cached4)
        r4_cached = True
    else:
        with st.spinner("Phase 4: Deterministic audit..."):
            from sentinel_x.phase4_audit.rule_engine    import AuditRuleEngine
            r4 = AuditRuleEngine().evaluate(pr)
        cache.set(pr.pr_id, 4, pr_data, r4.model_dump(mode="json"))

    # ── Results ───────────────────────────────────────────────────
    st.markdown("## Results")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("### 🔤 Phase 1")
        st.markdown("*Keyword Detection*")
        if r1_cached:
            st.caption("📦 from cache")
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
        if r2_cached:
            st.caption("📦 from cache")
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
        if r3_cached:
            st.caption("📦 from cache")
        if p3_error:
            st.error(f"Phase 3 failed:\n{p3_error}")
        else:
            verdict    = r3.get("verdict", "UNKNOWN")
            conf       = r3.get("confidence_score", 0.0)
            escalated  = r3.get("escalate_to_human", False)
            rec        = r3.get("recommendation", "")
            trace      = r3.get("trace_log", [])

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
        if r4_cached:
            st.caption("📦 from cache")
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
