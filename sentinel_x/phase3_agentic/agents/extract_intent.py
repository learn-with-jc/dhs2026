# sentinel_x/phase3_agentic/agents/extract_intent.py
"""
Sentinel-X | Agent 1 — Extract Intent

First node in the graph. Reads the raw PR and extracts:
  - PR type and vendor characterisation
  - Incentive-related items
  - Recipient signals
  - Estimated spend category

Feeds structured intent into all downstream agents.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from sentinel_x.platform.data_models import (
    PurchaseRequisition, TraceEvent,
)
from sentinel_x.platform.llm_provider import get_llm
from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)


class IntentOutput(BaseModel):
    pr_type:           str
    vendor_category:   str
    incentive_items:   list[str]
    recipient_signals: list[str]
    spend_category:    str
    risk_indicators:   list[str]
    confidence:        float


EXTRACT_INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are the intent extraction agent in a compliance \
reasoning pipeline. Extract structured information from the PR.
Return JSON matching: {format_instructions}"""),
    ("human", """PR Data:
Vendor: {vendor}
Amount: {currency} {total_amount}
Description: {description}
Items: {items}
Commodity: {commodity_code}
Attachments: {attachments}
Recipients: {recipients}"""),
])


def extract_intent_node(state: SentinelState) -> dict:
    """
    LangGraph node: extract intent from raw PR data.
    Returns state updates only (LangGraph merges them).
    """
    t0  = time.time() * 1000
    pr  = PurchaseRequisition(**state["pr_data"])
    llm = get_llm()
    parser = JsonOutputParser(pydantic_object=IntentOutput)
    chain  = EXTRACT_INTENT_PROMPT | llm | parser

    try:
        raw = chain.invoke({
            "vendor":        pr.vendor,
            "currency":      pr.currency,
            "total_amount":  pr.total_amount,
            "description":   pr.description,
            "items":         " | ".join(i.description for i in pr.item_details),
            "commodity_code": pr.commodity_code,
            "attachments":   " | ".join(a.simulated_content for a in pr.attachments),
            "recipients":    pr.recipient_context.model_dump_json(),
            "format_instructions": parser.get_format_instructions(),
        })
        output = IntentOutput(**raw)
    except Exception as exc:
        logger.error("extract_intent failed: %s", exc)
        output = IntentOutput(
            pr_type="unknown", vendor_category="unknown",
            incentive_items=[], recipient_signals=[],
            spend_category="other", risk_indicators=[],
            confidence=0.0,
        )

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "extract_intent",
        timestamp      = datetime.utcnow(),
        input_summary  = f"PR {pr.pr_id} | {pr.vendor} | {pr.currency}{pr.total_amount}",
        output_summary = f"type={output.pr_type} | items={output.incentive_items[:2]}",
        confidence     = output.confidence,
        duration_ms    = elapsed,
    )

    return {
        "extracted_intent": output.model_dump(),
        "trace_log":        [trace],
    }