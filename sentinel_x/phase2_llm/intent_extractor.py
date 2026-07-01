# sentinel_x/phase2_llm/intent_extractor.py
"""
Sentinel-X | Phase 2 — Intent Extractor

Structured LLM call to extract the intent of a PR before the
inversion filter runs. Adds context the main prompt doesn't
have time to derive itself.
"""

from __future__ import annotations
import logging

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from sentinel_x.platform.data_models import PurchaseRequisition

logger = logging.getLogger(__name__)


class ExtractedIntent(BaseModel):
    pr_type: str = Field(
        description="standard_procurement | hospitality | incentive | mixed"
    )
    inferred_category: str = Field(
        description="meals | gifts | sponsorship | gift_cards | travel | other"
    )
    incentive_items: list[str] = Field(
        default_factory=list,
        description="Hospitality or incentive items identified in the PR",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Risk flags: public_sector, high_value, gift_card, known_vendor_risk",
    )


INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a compliance intent classifier.
Analyse a purchase requisition and extract its primary intent.

Categories (pick the single best fit):
- meals:        dining, food, restaurant, catering, coffee, entertainment
- gifts:        hampers, physical gifts, prizes, non-monetary awards
- sponsorship:  event sponsorship, conference tickets, hospitality packages
- gift_cards:   gift cards, vouchers, prepaid cards, digital credits
- travel:       hotel, resort, flights, accommodation, retreats
- other:        standard operational purchase with no hospitality component

Risk flags to detect (include all that apply):
- public_sector   — recipients include government or public officials
- high_value      — total amount > $500
- gift_card       — any gift card or voucher component
- known_vendor_risk — vendor associated with hospitality or incentive goods

{format_instructions}"""),
    ("human", """PR ID:       {pr_id}
Vendor:      {vendor}
Amount:      {currency} {total_amount}
Description: {description}
Items:       {item_details}
Commodity:   {commodity_code}"""),
])


class IntentExtractor:
    """
    Lightweight LLM call to classify PR intent before the main
    inversion filter. Lazy-initialises the chain so construction
    never fails even when no API key is configured.
    """

    def __init__(self) -> None:
        self._chain = None
        self._parser = JsonOutputParser(pydantic_object=ExtractedIntent)

    def _build_chain(self):
        from sentinel_x.platform.llm_provider import get_llm
        return INTENT_PROMPT | get_llm(temperature=0.0) | self._parser

    def extract(self, pr: PurchaseRequisition) -> ExtractedIntent:
        if self._chain is None:
            self._chain = self._build_chain()

        raw = self._chain.invoke({
            "pr_id":               pr.pr_id,
            "vendor":              pr.vendor,
            "currency":            pr.currency,
            "total_amount":        pr.total_amount,
            "description":         pr.description,
            "item_details":        " | ".join(i.description for i in pr.item_details),
            "commodity_code":      pr.commodity_code,
            "format_instructions": self._parser.get_format_instructions(),
        })
        result = ExtractedIntent(**raw)
        logger.info(
            "Intent: %s | category=%s | items=%d | flags=%s",
            pr.pr_id, result.inferred_category,
            len(result.incentive_items), result.flags,
        )
        return result
