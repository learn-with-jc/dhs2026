# sentinel_x/phase3_agentic/state.py
"""
Sentinel-X | Phase 3 — LangGraph State Schema

The state object is the working memory of the entire
agent graph. Every agent reads from it and writes to it.
No agent communicates with another agent directly —
all communication is through state.

Design principles:
  - Typed: every field has a type, validated at runtime
  - Append-only for logs: trace_log grows, never replaces
  - Confidence is first-class: every agent writes its confidence
  - Escalation is explicit: a boolean flag, not an inference

# ╔══════════════════════════════════════════════════════════════╗
# ║  SNIPPET: PPT-SLIDE-15 | Phase 3 | State Schema             ║
# ║  STORY:   Agents don't talk to each other. They talk to      ║
# ║           shared state. This is the working memory of the    ║
# ║           entire reasoning pipeline.                         ║
# ║  OUTPUT:  The TypedDict — every field is a decision          ║
# ╚══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations
from typing import Any
from typing_extensions import TypedDict, Annotated
import operator

from sentinel_x.platform.data_models import (
    RetrievedChunk, TraceEvent, RiskLabel,
)


# ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
class SentinelState(TypedDict):                                 #◄
# └─────────────────────────────────────────────────────────────┘
    # ── Input ─────────────────────────────────────────────────
    pr_data:            dict[str, Any]   # Raw PR as dict

    # ── Agent outputs (written sequentially) ──────────────────
    extracted_intent:   dict[str, Any]   # extract_intent output
    matched_policies:   list[str]        # classify_policy output
    retrieved_chunks:   list[RetrievedChunk]  # retrieve_and_rerank
    reranked_chunks:    list[RetrievedChunk]  # post-BAAI chunks
    initial_reasoning:  str              # reason_compliance output
    critique_output:    str              # critique_reasoning output

    # ── Control flow signals ───────────────────────────────────
    confidence_score:   float            # 0.0 – 1.0
    retry_count:        int              # Loop convergence guard
    needs_critique:     bool             # Route to critique?
    needs_retry:        bool             # Loop back to retrieval?
    escalate_to_human:  bool             # Human handoff flag

    # ── Final outputs ─────────────────────────────────────────
    verdict:            str              # COMPLIANT/REVIEW_NEEDED/NON_COMPLIANT
    evidence:           list[RetrievedChunk]  # Cited policy chunks
    recommendation:     str              # Human-readable output

    # ── Observability (append-only) ───────────────────────────
    # Annotated with operator.add means LangGraph automatically
    # appends new trace events rather than replacing the list
    trace_log: Annotated[list[TraceEvent], operator.add]


def initial_state(pr_data: dict[str, Any]) -> SentinelState:
    """
    Create a fresh SentinelState for a new PR evaluation.
    All fields initialised to safe defaults.
    """
    return SentinelState(
        pr_data            = pr_data,
        extracted_intent   = {},
        matched_policies   = [],
        retrieved_chunks   = [],
        reranked_chunks    = [],
        initial_reasoning  = "",
        critique_output    = "",
        confidence_score   = 0.0,
        retry_count        = 0,
        needs_critique     = False,
        needs_retry        = False,
        escalate_to_human  = False,
        verdict            = RiskLabel.REVIEW_NEEDED.value,
        evidence           = [],
        recommendation     = "",
        trace_log          = [],
    )

# SPEAKER NOTE (PPT-SLIDE-15):
#
# WHAT TO SAY (not read):
#   "This TypedDict is the contract between all eight agents.
#    None of them call each other. None of them share memory
#    directly. They all read from this state object and write
#    their output back to it. The trace_log field at the bottom
#    is append-only — every agent adds its entry, nobody
#    overwrites the history. That's how we get a complete
#    reasoning trace for every PR. Auditability isn't bolted on
#    — it's in the data structure."
#
# POINT AT:     class SentinelState(TypedDict): and trace_log
# TRANSITION TO: "Let's walk through each agent node..."
# AVOID SAYING: "As you can see in line 7..."