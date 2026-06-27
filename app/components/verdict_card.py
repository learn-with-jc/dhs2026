# app/components/verdict_card.py
"""Styled verdict display component."""

from __future__ import annotations
import streamlit as st

VERDICT_COLOURS = {
    "COMPLIANT":        ("#10B981", "✅"),
    "REVIEW_NEEDED":    ("#F59E0B", "⚠️"),
    "FINDING":          ("#F59E0B", "⚠️"),
    "NON_COMPLIANT":    ("#EF4444", "🚫"),
    "ESCALATE_TO_HUMAN": ("#8B5CF6", "👤"),
    "UNKNOWN":          ("#6B7280", "❓"),
}


def verdict_card(
    verdict:     str,
    confidence:  float = 0.0,
    phase_label: str   = "",
    extra:       str   = "",
) -> None:
    """Render a styled verdict card."""
    colour, emoji = VERDICT_COLOURS.get(verdict, VERDICT_COLOURS["UNKNOWN"])
    conf_bar      = "█" * int(confidence * 10) + "░" * (10 - int(confidence * 10))

    st.markdown(
        f"""
        <div style="
            border-left: 5px solid {colour};
            padding: 12px 16px;
            border-radius: 4px;
            background: #F9FAFB;
            margin-bottom: 12px;
        ">
            <div style="font-size:1.1em;font-weight:700;color:{colour}">
                {emoji} {verdict}
            </div>
            {"<div style='font-size:0.85em;color:#6B7280'>" + phase_label + "</div>" if phase_label else ""}
            {"<div style='font-size:0.8em;color:#374151;margin-top:4px'>" + f"Confidence: {conf_bar} {confidence:.0%}" + "</div>" if confidence > 0 else ""}
            {"<div style='font-size:0.8em;color:#374151;margin-top:4px'>" + extra + "</div>" if extra else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )