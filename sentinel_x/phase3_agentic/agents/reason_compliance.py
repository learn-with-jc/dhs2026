# sentinel_x/phase3_agentic/agents/reason_compliance.py
"""
Sentinel-X | Agent 4 — Reason Compliance

Takes the top reranked policy chunks and the PR intent,
forms an initial compliance judgment.

Key constraint: the agent MUST cite specific policy chunks
in its reasoning. If it cannot cite a chunk, it cannot
make a verdict. This is the anti-hallucination mechanism.

Citation grounding = the agent's hallucination defence.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from sentinel_x.platform.data_models import TraceEvent, PurchaseRequisition
from sentinel_x.platform.llm_provider import get_llm
from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)


class ReasoningOutput(BaseModel):
    initial_verdict:   str   = Field(
        description="COMPLIANT | REVIEW_NEEDED | NON_COMPLIANT"
    )
    reasoning:         str   = Field(
        description="Step by step compliance reasoning"
    )
    cited_chunk_ids:   list[str] = Field(
        description="chunk_ids actually used in this reasoning"
    )
    policy_gaps:       list[str] = Field(
        description="Policies or rules not found in retrieved chunks"
    )
    confidence:        float


REASON_COMPLIANCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a compliance reasoning agent. Using ONLY \
the provided policy chunks, reason about whether this PR is compliant.

CRITICAL RULES:
1. You MUST cite specific chunk IDs to support your verdict
2. If you cannot find a relevant policy chunk, list it in policy_gaps
3. Do NOT make up rules not present in the chunks
4. When in doubt, verdict = REVIEW_NEEDED

Return JSON: {format_instructions}"""),
    ("human", """PR Summary:
{pr_summary}

Intent Analysis:
{intent_summary}

Relevant Policy Chunks:
{policy_chunks}
"""),
])


def reason_compliance_node(state: SentinelState) -> dict:
    """LangGraph node: form initial compliance judgment."""
    t0      = time.time() * 1000
    intent  = state["extracted_intent"]
    chunks  = state["reranked_chunks"]

    # Format chunks for the prompt
    chunk_text = "\n\n".join([
        f"[{c.chunk_id}] (Policy: {c.policy_id})\n{c.content[:400]}"
        for c in chunks
    ]) or "No relevant policy chunks retrieved."

    pr_obj = PurchaseRequisition(**state["pr_data"])

    pr_summary = (
        f"PR: {pr_obj.pr_id} | Vendor: {pr_obj.vendor} | "
        f"Amount: {pr_obj.currency}{pr_obj.total_amount} | "
        f"Description: {pr_obj.description[:150]}"
    )

    intent_summary = (
        f"Type: {intent.get('pr_type')} | "
        f"Items: {intent.get('incentive_items')} | "
        f"Recipients: {intent.get('recipient_signals')}"
    )

    llm    = get_llm()
    parser = JsonOutputParser(pydantic_object=ReasoningOutput)
    chain  = REASON_COMPLIANCE_PROMPT | llm | parser

    try:
        raw    = chain.invoke({
            "pr_summary":          pr_summary,
            "intent_summary":      intent_summary,
            "policy_chunks":       chunk_text,
            "format_instructions": parser.get_format_instructions(),
        })
        output = ReasoningOutput(**raw)

        # 🛡️ GUARDRAIL: citation grounding check
        # If agent cites no chunks, confidence is unreliable
        if not output.cited_chunk_ids:
            logger.warning(
                "No citations in reasoning for %s — confidence penalised",
                pr_obj.pr_id,
            )
            output.confidence = min(output.confidence, 0.4)

    except Exception as exc:
        logger.error("reason_compliance failed: %s", exc)
        output = ReasoningOutput(
            initial_verdict  = "REVIEW_NEEDED",
            reasoning        = f"Reasoning failed: {exc}",
            cited_chunk_ids  = [],
            policy_gaps      = ["all"],
            confidence       = 0.0,
        )

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "reason_compliance",
        timestamp      = datetime.utcnow(),
        input_summary  = f"{pr_summary[:80]} | {len(chunks)} chunks",
        output_summary = f"verdict={output.initial_verdict} | conf={output.confidence:.2f}",
        confidence     = output.confidence,
        duration_ms    = elapsed,
        notes          = f"citations={len(output.cited_chunk_ids)} | gaps={output.policy_gaps}",
    )

    return {
        "initial_reasoning": output.reasoning,
        "confidence_score":  output.confidence,
        "verdict":           output.initial_verdict,
        "trace_log":         [trace],
    }