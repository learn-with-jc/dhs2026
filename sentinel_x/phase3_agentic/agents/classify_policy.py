# sentinel_x/phase3_agentic/agents/classify_policy.py
"""
Sentinel-X | Agent 2 — Classify Policy

Determines which policies are relevant to this PR.
Prevents retrieving from all policies indiscriminately —
retrieval is only as good as the search space it operates on.
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

AVAILABLE_POLICIES = {
    "POL-001": "Gifts and Hospitality — thresholds, prohibited items, approvals",
    "POL-002": "Sponsorships — GSMM/GTE registration, approval tiers",
    "POL-003": "Meals and Entertainment — per-head limits, total thresholds",
    "POL-004": "Gift Cards and Vouchers — prohibitions, Dowlis exception",
    "POL-005": "Public Sector Limits — country-specific caps, known officials",
}


class PolicyClassificationOutput(BaseModel):
    applicable_policy_ids: list[str] = Field(
        description="List of policy IDs that apply to this PR"
    )
    reasoning: str
    confidence: float


CLASSIFY_POLICY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a policy classification agent. Given a PR's \
intent summary, identify which compliance policies are applicable.

Available policies:
{available_policies}

Return JSON: {format_instructions}
Only include policies that are genuinely relevant."""),
    ("human", "PR Intent Summary:\n{intent_summary}"),
])


def classify_policy_node(state: SentinelState) -> dict:
    """LangGraph node: classify which policies apply to this PR."""
    t0     = time.time() * 1000
    intent = state["extracted_intent"]
    llm    = get_llm()
    parser = JsonOutputParser(pydantic_object=PolicyClassificationOutput)
    chain  = CLASSIFY_POLICY_PROMPT | llm | parser

    policy_list = "\n".join(
        f"  {pid}: {desc}" for pid, desc in AVAILABLE_POLICIES.items()
    )

    intent_summary = (
        f"Type: {intent.get('pr_type')} | "
        f"Items: {intent.get('incentive_items')} | "
        f"Recipients: {intent.get('recipient_signals')} | "
        f"Risk: {intent.get('risk_indicators')}"
    )

    try:
        raw    = chain.invoke({
            "available_policies":  policy_list,
            "intent_summary":      intent_summary,
            "format_instructions": parser.get_format_instructions(),
        })
        output = PolicyClassificationOutput(**raw)
        # 🛡️ GUARDRAIL: if public sector signals present, POL-005 is mandatory
        if any(
            "public" in sig.lower() or "government" in sig.lower()
            for sig in intent.get("recipient_signals", [])
        ):
            if "POL-005" not in output.applicable_policy_ids:
                output.applicable_policy_ids.append("POL-005")
                logger.info("POL-005 added — public sector signal detected")

    except Exception as exc:
        logger.error("classify_policy failed: %s", exc)
        output = PolicyClassificationOutput(
            applicable_policy_ids=list(AVAILABLE_POLICIES.keys()),
            reasoning="Classification failed — using all policies",
            confidence=0.3,
        )

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "classify_policy",
        timestamp      = datetime.utcnow(),
        input_summary  = intent_summary[:100],
        output_summary = f"policies={output.applicable_policy_ids}",
        confidence     = output.confidence,
        duration_ms    = elapsed,
    )

    return {
        "matched_policies": output.applicable_policy_ids,
        "trace_log":        [trace],
    }