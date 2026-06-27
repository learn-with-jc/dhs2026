# sentinel_x/phase3_agentic/agents/verdict_gate.py
"""
Sentinel-X | Agent 6 — Verdict Gate

The routing decision point of the graph.
Determines the next step based on:
  - Current confidence score
  - Retry count vs MAX_RETRIES
  - Whether critique found gaps
  - Whether escalation is warranted

This agent doesn't call an LLM. It applies deterministic
routing logic. The verdict gate is where confidence becomes
action.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime

from sentinel_x.platform.data_models import TraceEvent
from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)


def verdict_gate_node(state: SentinelState) -> dict:
    """
    LangGraph node: determine routing from current state.
    Sets control flags read by the conditional edges.

    No LLM call — pure deterministic routing logic.
    """
    from config.settings import (
        CONFIDENCE_THRESHOLD, ESCALATION_THRESHOLD, MAX_RETRY_COUNT
    )

    t0           = time.time() * 1000
    confidence   = state["confidence_score"]
    retry_count  = state["retry_count"]
    needs_retry  = state["needs_retry"]

    # Routing decision tree
    if confidence < ESCALATION_THRESHOLD and retry_count >= MAX_RETRY_COUNT:
        # Too uncertain, retries exhausted → human
        escalate       = True
        needs_critique = False
        needs_retry_out = False
        routing_reason  = (
            f"Confidence {confidence:.2f} below escalation threshold "
            f"{ESCALATION_THRESHOLD} after {retry_count} retries"
        )

    elif needs_retry and retry_count < MAX_RETRY_COUNT:
        # Critique found gaps + retries available → loop back
        escalate        = False
        needs_critique  = False
        needs_retry_out = True
        routing_reason  = (
            f"Critique found gaps — retry {retry_count + 1} of {MAX_RETRY_COUNT}"
        )

    elif confidence < 0.70:
        # Medium confidence → needs critique
        escalate        = False
        needs_critique  = True
        needs_retry_out = False
        routing_reason  = (
            f"Confidence {confidence:.2f} below critique threshold 0.70"
        )

    else:
        # High confidence → proceed to evidence extraction
        escalate        = False
        needs_critique  = False
        needs_retry_out = False
        routing_reason  = f"Confidence {confidence:.2f} sufficient — proceeding"

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "verdict_gate",
        timestamp      = datetime.utcnow(),
        input_summary  = (
            f"conf={confidence:.2f} | retries={retry_count} | "
            f"needs_retry={needs_retry}"
        ),
        output_summary = routing_reason,
        confidence     = confidence,
        duration_ms    = elapsed,
    )

    new_retry_count = retry_count + 1 if needs_retry_out else retry_count

    logger.info(
        "verdict_gate | %s | retries=%d | escalate=%s | critique=%s",
        routing_reason[:60], new_retry_count, escalate, needs_critique,
    )

    return {
        "escalate_to_human": escalate,
        "needs_critique":    needs_critique,
        "needs_retry":       needs_retry_out,
        "retry_count":       new_retry_count,
        "trace_log":         [trace],
    }