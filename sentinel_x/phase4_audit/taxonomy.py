# sentinel_x/phase4_audit/taxonomy.py
"""
Sentinel-X | Phase 4 — Taxonomy Resolver

Maps raw category signals (from LLM intent extraction and
commodity codes) to a canonical IncentiveCategory.

Priority order (from settings.TAXONOMY_PRIORITY):
  gift_cards > sponsorship > gifts > meals > travel > other

Higher-priority categories win when signals conflict.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass

from sentinel_x.platform.data_models import IncentiveCategory

logger = logging.getLogger(__name__)


# Keyword → IncentiveCategory mapping
_KEYWORD_MAP: dict[str, IncentiveCategory] = {
    "meals":          IncentiveCategory.MEALS,
    "meal":           IncentiveCategory.MEALS,
    "dining":         IncentiveCategory.MEALS,
    "food":           IncentiveCategory.MEALS,
    "restaurant":     IncentiveCategory.MEALS,
    "catering":       IncentiveCategory.MEALS,
    "entertainment":  IncentiveCategory.MEALS,
    "coffee":         IncentiveCategory.MEALS,
    "gifts":          IncentiveCategory.GIFTS,
    "gift":           IncentiveCategory.GIFTS,
    "hamper":         IncentiveCategory.GIFTS,
    "prize":          IncentiveCategory.GIFTS,
    "award":          IncentiveCategory.GIFTS,
    "non-monetary":   IncentiveCategory.GIFTS,
    "sponsorship":    IncentiveCategory.SPONSORSHIP,
    "sponsor":        IncentiveCategory.SPONSORSHIP,
    "conference":     IncentiveCategory.SPONSORSHIP,
    "event":          IncentiveCategory.SPONSORSHIP,
    "ticket":         IncentiveCategory.SPONSORSHIP,
    "hospitality":    IncentiveCategory.SPONSORSHIP,
    "gift_cards":     IncentiveCategory.GIFT_CARDS,
    "gift_card":      IncentiveCategory.GIFT_CARDS,
    "voucher":        IncentiveCategory.GIFT_CARDS,
    "prepaid":        IncentiveCategory.GIFT_CARDS,
    "digital_credit": IncentiveCategory.GIFT_CARDS,
    "travel":         IncentiveCategory.TRAVEL,
    "hotel":          IncentiveCategory.TRAVEL,
    "resort":         IncentiveCategory.TRAVEL,
    "flight":         IncentiveCategory.TRAVEL,
    "accommodation":  IncentiveCategory.TRAVEL,
    "retreat":        IncentiveCategory.TRAVEL,
    "other":          IncentiveCategory.OTHER,
}

# Priority rank: higher = wins when signals conflict
_PRIORITY_RANK: dict[str, int] = {
    "other":       0,
    "travel":      1,
    "meals":       2,
    "gifts":       3,
    "sponsorship": 4,
    "gift_cards":  5,
}


@dataclass
class TaxonomyResult:
    primary_category: IncentiveCategory
    confidence: float
    priority_winner: str  # "llm" | "static" | "default"


def resolve_taxonomy(
    llm_cats:    list[str],
    static_cats: list[str],
) -> TaxonomyResult:
    """
    Resolve the primary IncentiveCategory from LLM category signals
    and static commodity code signals.

    LLM signals carry 0.7 weight; static/commodity signals carry 0.3.
    When categories tie on score, the highest-priority category wins.
    """
    scores: dict[IncentiveCategory, float] = {}

    def _match(text: str) -> IncentiveCategory | None:
        text_lower = text.lower().strip().replace(" ", "_")
        if text_lower in _KEYWORD_MAP:
            return _KEYWORD_MAP[text_lower]
        for kw, cat in _KEYWORD_MAP.items():
            if kw in text_lower or text_lower in kw:
                return cat
        return None

    for cat_str in llm_cats:
        cat = _match(cat_str)
        if cat:
            scores[cat] = scores.get(cat, 0.0) + 0.7

    for static_str in static_cats:
        cat = _match(static_str)
        if cat:
            scores[cat] = scores.get(cat, 0.0) + 0.3

    if not scores:
        logger.info("No taxonomy signal resolved — defaulting to OTHER")
        return TaxonomyResult(
            primary_category=IncentiveCategory.OTHER,
            confidence=0.5,
            priority_winner="default",
        )

    # Tiebreak: highest-priority category wins
    best = max(
        scores.keys(),
        key=lambda c: (_PRIORITY_RANK.get(c.value, 0), scores[c]),
    )
    total = sum(scores.values())
    confidence = min(scores[best] / total, 1.0) if total > 0 else 0.5

    llm_matched = any(_match(c) == best for c in llm_cats)
    winner = "llm" if llm_matched else "static"

    logger.info(
        "Taxonomy: %s (conf=%.2f, winner=%s) from llm=%s static=%s",
        best.value, confidence, winner, llm_cats, static_cats,
    )
    return TaxonomyResult(
        primary_category=best,
        confidence=confidence,
        priority_winner=winner,
    )
