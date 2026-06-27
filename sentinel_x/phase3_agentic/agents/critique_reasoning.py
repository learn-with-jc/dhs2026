# sentinel_x/phase3_agentic/agents/critique_reasoning.py
"""
Sentinel-X | Agent 5 — Critique Reasoning

The self-review agent. Challenges the initial reasoning.
Asks: what did the reasoning agent miss? Are there
conflicting policies? Are there edge cases not considered?

This is the 'loop engineering' moment — the agent that
knows the boundary of its own competence and triggers
a re-retrieval when it finds gaps.

Not retry logic. Competence boundary detection.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from sentinel_x.platform.data_models import TraceEvent
from sentinel_x.platform.llm_provider import get_llm
from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)


class CritiqueOutput(BaseModel):
    has_gaps:           bool  = Field(
        description="True if the reasoning has gaps or missing considerations"
    )
    missing_policies:   list[str]
    conflicting_rules:  list[str]
    edge_cases_missed:  list[str]
    critique_summary:   str
    revised_confidence: float
    recommend_retry:    bool  = Field(
        description="True if retrieval should be retried with refined query"
    )


CRITIQUE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior compliance reviewer critiquing \
an AI agent's initial compliance reasoning.

Your job is to find:
1. Missing policy considerations
2. Conflicting rules that weren't resolved
3. Edge cases (public sector, known officials, exceptions)
   that weren't addressed
4. Whether additional policy retrieval would help

Be rigorous. A missed violation is worse than a false flag.
Return JSON: {format_instructions}"""),

    ("human", """Initial Reasoning to Critique:
{initial_reasoning}

PR Context:
{pr_summary}

Retrieved Policy Chunks Used:
{chunks_used}

Question: What did this reasoning miss or get wrong?
"""),
])


def critique_reasoning_node(state: SentinelState) -> dict:
    """
    LangGraph node: critique the initial compliance reasoning.

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  SNIPPET: PPT-SLIDE-18 | Phase 3 | Critique Loop Trigger    ║
    # ║  STORY:   This is not retry logic. This is the agent knowing ║
    # ║           the boundary of its own competence.                ║
    # ║  OUTPUT:  has_gaps boolean + recommend_retry — the signals   ║
    # ║           that control whether we loop or proceed            ║
    # ╚══════════════════════════════════════════════════════════════╝
    """
    t0      = time.time() * 1000
    from sentinel_x.platform.data_models import PurchaseRequisition
    pr      = PurchaseRequisition(**state["pr_data"])
    chunks  = state["reranked_chunks"]

    pr_summary = (
        f"PR: {pr.pr_id} | {pr.vendor} | "
        f"{pr.currency}{pr.total_amount} | "
        f"Public sector: {pr.recipient_context.includes_public_sector} | "
        f"Known officials: {pr.recipient_context.known_public_officials}"
    )

    chunks_used = "\n".join([
        f"[{c.chunk_id}] {c.content[:200]}"
        for c in chunks[:3]
    ]) or "No chunks available"

    llm    = get_llm()
    parser = JsonOutputParser(pydantic_object=CritiqueOutput)
    chain  = CRITIQUE_PROMPT | llm | parser

    try:
        raw    = chain.invoke({
            "initial_reasoning":   state["initial_reasoning"],
            "pr_summary":          pr_summary,
            "chunks_used":         chunks_used,
            "format_instructions": parser.get_format_instructions(),
        })
        output = CritiqueOutput(**raw)

    except Exception as exc:
        logger.error("critique_reasoning failed: %s", exc)
        output = CritiqueOutput(
            has_gaps=False, missing_policies=[], conflicting_rules=[],
            edge_cases_missed=[], critique_summary=f"Critique failed: {exc}",
            revised_confidence=state["confidence_score"],
            recommend_retry=False,
        )

    # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
    should_retry = (                                                #◄
        output.recommend_retry
        and state["retry_count"] < 2  # MAX_RETRIES from settings
    )
    # └─────────────────────────────────────────────────────────────┘

    # 🛡️ GUARDRAIL: cap confidence if gaps found, never increase it
    new_confidence = min(
        output.revised_confidence,
        state["confidence_score"],
    ) if output.has_gaps else output.revised_confidence

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "critique_reasoning",
        timestamp      = datetime.utcnow(),
        input_summary  = f"Critiquing reasoning for {pr.pr_id}",
        output_summary = (
            f"has_gaps={output.has_gaps} | "
            f"retry={should_retry} | "
            f"conf={new_confidence:.2f}"
        ),
        confidence     = new_confidence,
        duration_ms    = elapsed,
        notes          = output.critique_summary[:150],
    )

    return {
        "critique_output":  output.critique_summary,
        "confidence_score": new_confidence,
        "needs_retry":      should_retry,
        "trace_log":        [trace],
    }

# SPEAKER NOTE (PPT-SLIDE-18):
#
# WHAT TO SAY (not read):
#   "This agent does one thing: it reads the initial reasoning
#    and asks 'what did we miss?' If it finds gaps, it sets
#    needs_retry to True and the graph loops back to retrieval
#    with a more informed query. The key line here is the
#    should_retry check — it respects the retry budget.
#    We cannot let this loop forever. Two retries maximum,
#    then we take the best answer we have or escalate.
#    That's not a limitation — that's production discipline."
#
# POINT AT:     should_retry = (output.recommend_retry and ...)
# TRANSITION TO: "The verdict_gate decides what happens next
#                 based on confidence and retry state..."
# AVOID SAYING: "As you can see in line 7..."