# app/components/pr_selector.py
"""PR selector widget — shared across all app pages."""

from __future__ import annotations
import json
from pathlib import Path

import streamlit as st

from sentinel_x.platform.data_models import PurchaseRequisition


@st.cache_data
def load_all_prs() -> list[PurchaseRequisition]:
    pr_file = Path(__file__).resolve().parents[2] / "data/raw/purchase_requisitions/sample_prs.json"
    raw     = json.loads(pr_file.read_text())
    return [PurchaseRequisition(**p) for p in raw]


def pr_selector_widget(
    label:         str = "Select Purchase Requisition",
    filter_label:  str | None = None,
) -> PurchaseRequisition | None:
    """
    Render a PR selector dropdown.
    Optionally filter by risk label.
    Returns the selected PurchaseRequisition.
    """
    prs = load_all_prs()

    if filter_label:
        prs = [p for p in prs if p.risk_label.value == filter_label]

    options = {
        f"{p.pr_id} | {p.vendor[:25]} | {p.currency}{p.total_amount:,.0f} | {p.risk_label.value}": p
        for p in prs
    }

    if not options:
        st.warning("No PRs available for this filter.")
        return None

    selected_key = st.selectbox(label, options=list(options.keys()))
    pr           = options[selected_key]

    with st.expander("PR Details", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**PR ID:** {pr.pr_id}")
            st.markdown(f"**Vendor:** {pr.vendor}")
            st.markdown(f"**Amount:** {pr.currency} {pr.total_amount:,.2f}")
            st.markdown(f"**Submitted by:** {pr.submitted_by}")
        with col2:
            st.markdown(f"**Category:** {pr.ground_truth_category.value}")
            st.markdown(f"**Risk Label:** {pr.risk_label.value}")
            st.markdown(f"**CPP:** {pr.cost_per_person:.2f}")
            st.markdown(f"**Public Sector:** {pr.recipient_context.includes_public_sector}")
        st.markdown(f"**Description:** {pr.description}")

    return pr