# sentinel_x/phase3_agentic/graph/orchestrator.py
"""
Sentinel-X | Phase 3 — LangGraph Orchestrator

Wires all agent nodes into a StateGraph.
This is the conductor — it defines the sequence,
the conditional edges, and the loop structure.

Graph structure:
  START
    → extract_intent
    → classify_policy
    → retrieve_and_rerank
    → reason_compliance
    → verdict_gate ──┬──► critique_reasoning ──┬──► retrieve_and_rerank (loop)
                     │                          └──► extract_evidence
                     ├──► extract_evidence
                     ├──► retrieve_and_rerank (retry loop)
                     └──► END (escalate)
  extract_evidence
    → generate_recommendation
    → END
"""

from __future__ import annotations
import logging
from functools import lru_cache

from langgraph.graph import StateGraph, START, END

from sentinel_x.phase3_agentic.state import SentinelState, initial_state
from sentinel_x.phase3_agentic.agents.extract_intent        import extract_intent_node
from sentinel_x.phase3_agentic.agents.classify_policy       import classify_policy_node
from sentinel_x.phase3_agentic.agents.retrieve_and_rerank   import retrieve_and_rerank_node
from sentinel_x.phase3_agentic.agents.reason_compliance     import reason_compliance_node
from sentinel_x.phase3_agentic.agents.critique_reasoning    import critique_reasoning_node
from sentinel_x.phase3_agentic.agents.verdict_gate          import verdict_gate_node
from sentinel_x.phase3_agentic.agents.extract_evidence      import extract_evidence_node
from sentinel_x.phase3_agentic.agents.generate_recommendation import generate_recommendation_node
from sentinel_x.phase3_agentic.graph.routing import (
    route_after_verdict_gate,
    route_after_critique,
    NODE_CRITIQUE,
    NODE_RETRIEVE,
    NODE_EXTRACT_EVIDENCE,
    NODE_RECOMMEND,
    NODE_END,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def build_graph() -> StateGraph:
    """
    Build and compile the Sentinel-X LangGraph StateGraph.
    Cached — graph is compiled once and reused.

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  SNIPPET: PPT-SLIDE-20 | Phase 3 | Graph Assembly           ║
    # ║  STORY:   Eight agents, one graph, wired by routing logic.   ║
    # ║           The add_conditional_edges call is where loop       ║
    # ║           engineering becomes concrete.                      ║
    # ║  OUTPUT:  The compiled graph — ready to run any PR           ║
    # ╚══════════════════════════════════════════════════════════════╝
    """
    workflow = StateGraph(SentinelState)

    # ── Register all nodes ─────────────────────────────────────
    workflow.add_node("extract_intent",          extract_intent_node)
    workflow.add_node("classify_policy",         classify_policy_node)
    workflow.add_node("retrieve_and_rerank",     retrieve_and_rerank_node)
    workflow.add_node("reason_compliance",       reason_compliance_node)
    workflow.add_node("critique_reasoning",      critique_reasoning_node)
    workflow.add_node("verdict_gate",            verdict_gate_node)
    workflow.add_node("extract_evidence",        extract_evidence_node)
    workflow.add_node("generate_recommendation", generate_recommendation_node)

    # ── Linear edges (always execute in sequence) ──────────────
    workflow.add_edge(START,                    "extract_intent")
    workflow.add_edge("extract_intent",          "classify_policy")
    workflow.add_edge("classify_policy",         "retrieve_and_rerank")
    workflow.add_edge("retrieve_and_rerank",     "reason_compliance")
    workflow.add_edge("reason_compliance",       "verdict_gate")
    workflow.add_edge("extract_evidence",        "generate_recommendation")
    workflow.add_edge("generate_recommendation", END)

    # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
    workflow.add_conditional_edges(                                 #◄
        "verdict_gate",
        route_after_verdict_gate,
        {
            NODE_CRITIQUE:         "critique_reasoning",
            NODE_RETRIEVE:         "retrieve_and_rerank",
            NODE_EXTRACT_EVIDENCE: "extract_evidence",
            NODE_END:              END,
        },
    )
    # └─────────────────────────────────────────────────────────────┘

    # ── Critique loop edge ─────────────────────────────────────
    workflow.add_conditional_edges(
        "critique_reasoning",
        route_after_critique,
        {
            NODE_RETRIEVE:         "retrieve_and_rerank",
            NODE_EXTRACT_EVIDENCE: "extract_evidence",
        },
    )

    compiled = workflow.compile()
    logger.info("Sentinel-X Phase 3 graph compiled successfully")
    return compiled

# SPEAKER NOTE (PPT-SLIDE-20):
#
# WHAT TO SAY (not read):
#   "This is the entire agent graph in about 20 lines.
#    Linear edges are the happy path. Conditional edges
#    are where the intelligence is. That add_conditional_edges
#    call on verdict_gate is what makes this a reasoning system
#    rather than a pipeline. The graph can loop back, escalate,
#    or proceed — based on what the agents discovered.
#    LangGraph handles the state threading, the loop detection,
#    and the execution. We just define the topology."
#
# POINT AT:     workflow.add_conditional_edges("verdict_gate", ...)
# TRANSITION TO: "Let's run a PR through this graph live..."
# AVOID SAYING: "As you can see in line 7..."


def run_pr_through_graph(
    pr_dict: dict,
    verbose: bool = False,
    callbacks: list | None = None,
) -> SentinelState:
    """
    Run a single PR through the compiled Sentinel-X graph.
    Returns the final state after all agents complete.
    """
    graph = build_graph()
    state = initial_state(pr_dict)

    logger.info(
        "Running PR %s through Phase 3 graph",
        pr_dict.get("pr_id", "unknown"),
    )

    _cb  = callbacks or []
    _cfg = {"recursion_limit": 20, "callbacks": _cb, "tags": [pr_dict.get("pr_id", ""), "phase3"]}

    if verbose:
        merged: dict = dict(state)
        for step in graph.stream(state, _cfg):
            node_name = list(step.keys())[0]
            node_out  = step[node_name]
            conf      = node_out.get("confidence_score", 0)
            logger.info("  ✓ Node: %-25s | conf=%.2f", node_name, conf)
            # trace_log uses operator.add reducer — must append, not replace
            if "trace_log" in node_out:
                merged["trace_log"] = merged["trace_log"] + node_out["trace_log"]
                node_out = {k: v for k, v in node_out.items() if k != "trace_log"}
            merged.update(node_out)
        return merged  # type: ignore[return-value]

    return graph.invoke(state, _cfg)