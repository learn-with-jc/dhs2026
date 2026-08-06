# prism/phase3_agentic/graph/orchestrator.py
"""
PRism | Phase 3 — LangGraph Orchestrator

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

from prism.phase3_agentic.state import PrismState, initial_state
from prism.phase3_agentic.agents.extract_intent        import extract_intent_node
from prism.phase3_agentic.agents.classify_policy       import classify_policy_node
from prism.phase3_agentic.agents.retrieve_and_rerank   import retrieve_and_rerank_node
from prism.phase3_agentic.agents.reason_compliance     import reason_compliance_node
from prism.phase3_agentic.agents.critique_reasoning    import critique_reasoning_node
from prism.phase3_agentic.agents.verdict_gate          import verdict_gate_node
from prism.phase3_agentic.agents.extract_evidence      import extract_evidence_node
from prism.phase3_agentic.agents.generate_recommendation import generate_recommendation_node
from prism.phase3_agentic.graph.routing import (
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
    Build and compile the PRism LangGraph StateGraph.
    Cached — graph is compiled once and reused.
    """
    workflow = StateGraph(PrismState)

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
    logger.info("PRism Phase 3 graph compiled successfully")
    return compiled


def run_pr_through_graph(
    pr_dict: dict,
    verbose: bool = False,
    callbacks: list | None = None,
) -> PrismState:
    """
    Run a single PR through the compiled PRism graph.
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


def normalize_phase3_result(raw: dict | PrismState) -> dict:
    """
    Trim a raw graph state down to the display/cache-relevant fields.

    Used both by the CLI runner and the Streamlit app so that a Phase 3
    result cached by one is readable by the other (same shape, same
    confidence normalisation).
    """
    is_dict = isinstance(raw, dict)
    conf = raw.get("confidence_score", 0.0) if is_dict else 0.0
    if conf > 1.0:
        conf /= 100.0
    return {
        "verdict":          raw.get("verdict", "REVIEW_NEEDED") if is_dict else "REVIEW_NEEDED",
        "confidence_score": conf,
        "escalate_to_human": raw.get("escalate_to_human", False) if is_dict else False,
        "recommendation":   raw.get("recommendation", "") if is_dict else "",
        "retry_count":      raw.get("retry_count", 0) if is_dict else 0,
        "trace_log": [
            t.model_dump(mode="json") if hasattr(t, "model_dump") else t
            for t in (raw.get("trace_log", []) if is_dict else [])
        ],
    }