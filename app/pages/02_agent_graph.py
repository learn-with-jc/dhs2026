# app/pages/02_agent_graph.py
"""
Sentinel-X | Page 2 — Agent Graph Visualizer

Shows the LangGraph execution trace as a Mermaid diagram.
Select a REVIEW_NEEDED PR and watch the agents work.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components.pr_selector  import pr_selector_widget
from app.components.verdict_card import verdict_card

st.title("🔗 Agent Graph — Live Execution Trace")
st.markdown(
    "Watch Phase 3 agents execute on a PR. "
    "The graph shows which nodes ran, confidence at each step, "
    "and whether the critique loop was triggered."
)

st.info(
    "ℹ️ Phase 3 runs on PRs flagged as REVIEW_NEEDED by Phase 2. "
    "Select a non-compliant or review PR for the most interesting trace."
)

pr = pr_selector_widget("Select a PR for agent analysis")

if pr and st.button("▶ Run Agent Graph", type="primary"):

    with st.spinner("Running Phase 3 agent graph... (this takes 15-30 seconds)"):
        from sentinel_x.phase3_agentic.graph.orchestrator import run_pr_through_graph
        final_state = run_pr_through_graph(pr.model_dump(), verbose=True)

    trace_log = final_state.get("trace_log", [])
    verdict   = final_state.get("verdict", "UNKNOWN")
    conf      = final_state.get("confidence_score", 0.0)
    escalated = final_state.get("escalate_to_human", False)

    # Verdict header
    st.markdown("---")
    col_v, col_c, col_e = st.columns(3)
    with col_v:
        verdict_card(verdict, conf, "Phase 3 Agentic")
    with col_c:
        st.metric("Confidence", f"{conf:.0%}")
        st.metric("Retries", str(final_state.get("retry_count", 0)))
    with col_e:
        st.metric("Escalated", "Yes 👤" if escalated else "No ✓")
        st.metric("Agents Run", str(len(trace_log)))

    # Mermaid diagram
    st.markdown("---")
    st.markdown("### Agent Execution Graph")
    from sentinel_x.observability.graph_visualizer import build_execution_mermaid
    mermaid_src = build_execution_mermaid(trace_log, verdict, escalated)
    st.markdown(f"```mermaid\n{mermaid_src}\n```")

    # Agent trace table
    st.markdown("---")
    st.markdown("### Agent Trace Log")

    trace_data = []
    for event in trace_log:
        if isinstance(event, dict):
            trace_data.append({
                "Agent":       event.get("agent_name", ""),
                "Confidence":  f"{event.get('confidence', 0):.2f}",
                "Duration ms": f"{event.get('duration_ms', 0):.0f}",
                "Output":      event.get("output_summary", "")[:80],
                "Notes":       event.get("notes", "")[:60],
            })
        else:
            trace_data.append({
                "Agent":       event.agent_name,
                "Confidence":  f"{event.confidence:.2f}",
                "Duration ms": f"{event.duration_ms:.0f}",
                "Output":      event.output_summary[:80],
                "Notes":       event.notes[:60],
            })

    if trace_data:
        import pandas as pd
        st.dataframe(pd.DataFrame(trace_data), use_container_width=True)

    # Recommendation
    rec = final_state.get("recommendation", "")
    if rec:
        st.markdown("---")
        st.markdown("### 📝 Recommendation")
        st.text(rec)