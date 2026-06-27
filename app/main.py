# app/main.py
"""
Sentinel-X | Streamlit Demo Application

Entry point for the multi-page Streamlit app.
Run with: streamlit run app/main.py

Pages:
  01 Phase Comparison    — same PR through all 4 phases
  02 Agent Graph         — live LangGraph execution trace
  03 Audit Trail         — structured decision log explorer
  04 Metrics Dashboard   — FP/FN rates across phases
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

st.set_page_config(
    page_title = "Sentinel-X | Compliance AI",
    page_icon  = "🛡️",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

st.title("🛡️ Sentinel-X")
st.subheader("Enterprise Compliance AI — DataHack Summit 2026")

st.markdown("""
**Sentinel-X** demonstrates an evolving AI system for Purchase Requisition
compliance review — from keyword matching to agentic reasoning.

---

### Navigate the Demo

| Page | What it shows |
|------|--------------|
| 📊 **Phase Comparison** | Same PR processed through all 4 phases side-by-side |
| 🔗 **Agent Graph**      | Live LangGraph execution trace with node highlights |
| 📋 **Audit Trail**      | Structured decision log with policy citations |
| 📈 **Metrics Dashboard**| False positive rate and analyst workload across phases |

---

### The Four Phases