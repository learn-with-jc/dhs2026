# app/pages/03_audit_trail.py
"""
Sentinel-X | Page 3 — Audit Trail Explorer

Browse and search the structured audit logs produced
by Phase 4. Every decision is traceable to a rule.
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components.verdict_card import verdict_card

st.title("📋 Audit Trail Explorer")
st.markdown(
    "Browse structured audit decisions from Phase 4. "
    "Every finding maps to a named rule and policy reference."
)

from config.settings import AUDIT_LOG_DIR

audit_files = list(AUDIT_LOG_DIR.glob("*.json")) if AUDIT_LOG_DIR.exists() else []

if not audit_files:
    st.warning(
        "No audit logs found. Run Phase 4 first:\n\n"
        "```bash\npython -m sentinel_x.phase4_audit.run_phase4\n```"
    )
    st.stop()

# Load all audit records
records = []
for f in sorted(audit_files, key=lambda x: x.stem, reverse=True):
    try:
        records.append(json.loads(f.read_text()))
    except Exception:
        pass

# Filter controls
st.markdown("---")
col_f1, col_f2 = st.columns(2)
with col_f1:
    status_filter = st.multiselect(
        "Filter by Status",
        ["COMPLIANT", "FINDING", "NON_COMPLIANT"],
        default=["FINDING", "NON_COMPLIANT"],
    )
with col_f2:
    search_term = st.text_input("Search by PR ID or Vendor")

filtered = [
    r for r in records
    if (not status_filter or r.get("status") in status_filter)
    and (not search_term or search_term.lower() in (r.get("pr_id","") + r.get("vendor","")).lower())
]

st.caption(f"Showing {len(filtered)} of {len(records)} audit records")
st.markdown("---")

for record in filtered[:20]:
    with st.expander(
        f"{record.get('pr_id')} | {record.get('status')} | "
        f"{record.get('category','').upper()}"
    ):
        col1, col2 = st.columns([1, 2])
        with col1:
            verdict_card(record.get("status", "UNKNOWN"))
            st.markdown(f"**Category:** {record.get('category','')}")
            st.markdown(f"**Recipient:** {record.get('recipient_type','')}")
            st.markdown(f"**CPP:** {record.get('cost_per_person', 0):.2f}")
        with col2:
            checks = record.get("policy_checks", [])
            failed = [c for c in checks if not c.get("passed")]
            if failed:
                st.markdown("**Policy Violations:**")
                for c in failed:
                    severity_colour = (
                        "🔴" if c.get("severity") == "critical"
                        else "🟠" if c.get("severity") == "high"
                        else "🟡"
                    )
                    st.markdown(f"{severity_colour} **{c.get('rule_name')}**")
                    st.caption(c.get("finding",""))
            if record.get("actions"):
                st.markdown("**Actions:**")
                for a in record.get("actions", []):
                    st.markdown(f"→ {a}")
        if record.get("evidence_refs"):
            st.caption(f"Policy refs: {', '.join(record.get('evidence_refs', []))}")
        if record.get("audit_hash"):
            st.caption(f"Audit hash: `{record.get('audit_hash')}`")