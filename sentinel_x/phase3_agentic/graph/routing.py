# sentinel_x/phase3_agentic/graph/routing.py
"""
Sentinel-X | Phase 3 — Conditional Edge Routing

All routing decisions for the LangGraph StateGraph.
Routing functions read state flags set by verdict_gate
and return the name of the next node.

Routing is deterministic — it reads boolean flags,
not LLM outputs. The LLM sets confidence; the router
acts on it.
"""

from __future__ import annotations
import logging

from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)

# Node name constants — avoids magic strings
NODE_CRITIQUE          = "critique_reasoning"
NODE_RETRIEVE          = "retrieve_and_rerank"
NODE_EXTRACT_EVIDENCE  = "extract_evidence"
NODE_RECOMMEND         = "generate_recommendation"
NODE_END               = "__end__"


def route_after_verdict_gate(state: SentinelState) -> str:
    """
    Routing function called after verdict_gate node.

    Decision tree:
      escalate_to_human  → END (human handoff)
      needs_critique     → critique_reasoning
      needs_retry        → retrieve_and_rerank (loop back)
      otherwise          → extract_evidence

      
    """
    if state.get("escalate_to_human"):
        logger.info(
            "Routing: ESCALATE_TO_HUMAN | conf=%.2f | retries=%d",
            state.get("confidence_score", 0),
            state.get("retry_count", 0),
        )
        # 🛡️ GUARDRAIL: human escalation always wins
        return NODE_END

    if state.get("needs_retry"):
        logger.info(
            "Routing: RETRY → retrieve_and_rerank | retry=%d",
            state.get("retry_count", 0),
        )
        return NODE_RETRIEVE

    if state.get("needs_critique"):
        logger.info(
            "Routing: CRITIQUE | conf=%.2f",
            state.get("confidence_score", 0),
        )
        return NODE_CRITIQUE

    logger.info(
        "Routing: PROCEED → extract_evidence | conf=%.2f",
        state.get("confidence_score", 0),
    )
    return NODE_EXTRACT_EVIDENCE


def route_after_critique(state: SentinelState) -> str:
    """
    Routing function called after critique_reasoning node.

    If critique set needs_retry → loop back to retrieval.
    Otherwise → extract_evidence.
    """
    # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
    if state.get("needs_retry"):                                    #◄
        return NODE_RETRIEVE
    return NODE_EXTRACT_EVIDENCE
    # └─────────────────────────────────────────────────────────────┘

