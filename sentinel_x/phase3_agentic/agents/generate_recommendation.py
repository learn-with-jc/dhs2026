# sentinel_x/phase3_agentic/agents/generate_recommendation.py
"""
Sentinel-X | Agent 8 — Generate Recommendation

Final node before output. Synthesises everything
into a human-readable compliance recommendation.

The output is what a compliance analyst reads.
It must be:
  - Clear (non-technical language)
  - Actionable (what to do next)
  - Evidence-grounded (cite specific policies)
  - Proportionate (severity matters)
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


class RecommendationOutput(BaseModel):
    final_verdict:      str
    summary:            str
    key_findings:       list[str]
    recommended_actions: list[str]
    policy_references:  list[str]
    analyst_notes:      str
    confidence:         float


RECOMMENDATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a compliance recommendation agent. \
Write a clear, actionable compliance recommendation for a \
human analyst to review.

Use plain language. Be specific. Reference exact policies.
The analyst is busy — lead with the verdict and key finding.
Return JSON: {format_instructions}"""),

    ("human", """Compliance Analysis:
PR: {pr_summary}
Verdict: {verdict}
Reasoning: {reasoning}
Evidence: {evidence_summary}
Critique Notes: {critique_notes}
"""),
])


def generate_recommendation_node(state: SentinelState) -> dict:
    """LangGraph node: generate final human-readable recommendation."""
    t0      = time.time() * 1000
    from sentinel_x.platform.data_models import PurchaseRequisition
    pr      = PurchaseRequisition(**state["pr_data"])

    evidence_cited = [c for c in state["evidence"] if c.is_cited]
    evidence_summary = (
        "\n".join([
            f"- [{c.chunk_id}] {c.content[:150]}"
            for c in evidence_cited[:3]
        ]) or "No specific evidence cited"
    )

    pr_summary = (
        f"{pr.pr_id} | {pr.vendor} | "
        f"{pr.currency}{pr.total_amount:,.2f} | "
        f"{pr.description[:100]}"
    )

    llm    = get_llm()
    parser = JsonOutputParser(pydantic_object=RecommendationOutput)
    chain  = RECOMMENDATION_PROMPT | llm | parser

    try:
        raw    = chain.invoke({
            "pr_summary":          pr_summary,
            "verdict":             state["verdict"],
            "reasoning":           state["initial_reasoning"][:500],
            "evidence_summary":    evidence_summary,
            "critique_notes":      state["critique_output"][:200] or "None",
            "format_instructions": parser.get_format_instructions(),
        })
        output = RecommendationOutput(**raw)

    except Exception as exc:
        logger.error("generate_recommendation failed: %s", exc)
        output = RecommendationOutput(
            final_verdict       = state["verdict"],
            summary             = f"Auto-generated summary. Review manually: {exc}",
            key_findings        = [],
            recommended_actions = ["Manual review required"],
            policy_references   = state["matched_policies"],
            analyst_notes       = "Recommendation generation failed",
            confidence          = state["confidence_score"],
        )

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "generate_recommendation",
        timestamp      = datetime.utcnow(),
        input_summary  = pr_summary[:80],
        output_summary = f"verdict={output.final_verdict} | {output.summary[:80]}",
        confidence     = output.confidence,
        duration_ms    = elapsed,
    )

    # Final confidence update
    return {
        "verdict":        output.final_verdict,
        "recommendation": (
            f"VERDICT: {output.final_verdict}\n\n"
            f"{output.summary}\n\n"
            f"KEY FINDINGS:\n" +
            "\n".join(f"  • {f}" for f in output.key_findings) +
            f"\n\nRECOMMENDED ACTIONS:\n" +
            "\n".join(f"  • {a}" for a in output.recommended_actions) +
            f"\n\nPOLICY REFERENCES: {', '.join(output.policy_references)}" +
            f"\n\nANALYST NOTES: {output.analyst_notes}"
        ),
        "confidence_score": output.confidence,
        "trace_log":        [trace],
    }