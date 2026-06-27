# sentinel_x/phase1_keyword/keyword_engine.py
"""
Sentinel-X | Phase 1 — Keyword-Based Detection Engine

The first generation system. Compliance analysts manually
curated a list of keywords in an Excel file. Python scanned
PR text fields and flagged matches.

Simple. Fast. Auditable. And fundamentally limited.
The failure mode this phase exposes: keywords have no context.
'dinner' flags a server configuration PR.
'gift' flags gift wrapping paper.
'sponsor' flags a sponsored cloud credit.

This phase exists in the repo to show WHERE WE STARTED,
not where we ended up.
"""

from __future__ import annotations
import logging
import time
from pathlib import Path

import pandas as pd

from sentinel_x.platform.data_models import (
    PurchaseRequisition, Phase1Result,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# KEYWORD CATALOGUE
# Simulates the analyst-maintained Excel file
# In production: loaded from xlsx at runtime
# ─────────────────────────────────────────────

DEFAULT_KEYWORD_CATALOGUE = {
    "meals": [
        "dinner", "lunch", "breakfast", "meal", "restaurant",
        "catering", "hospitality", "dining", "banquet", "gala",
        "food", "beverage", "drinks", "bar tab", "wine", "reception",
    ],
    "gifts": [
        "gift", "hamper", "present", "souvenir", "token",
        "watch", "jewellery", "jewelry", "luxury", "premium gift",
        "branded merchandise", "goodies",
    ],
    "sponsorship": [
        "sponsor", "sponsorship", "event ticket", "tickets",
        "hospitality box", "corporate box", "sports event",
        "conference pass", "delegate pass", "booth", "exhibition",
    ],
    "gift_cards": [
        "gift card", "gift voucher", "prepaid card", "voucher",
        "e-gift", "amazon card", "flipkart card", "visa card",
        "mastercard gift",
    ],
    "travel": [
        "resort", "retreat", "incentive travel", "offsite",
        "hotel stay", "accommodation",
    ],
}


def build_keyword_dataframe(
    catalogue: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """
    Build a flat DataFrame from the keyword catalogue.
    Simulates loading from the analyst-maintained Excel file.

    Columns: term, category, severity
    """
    cat = catalogue or DEFAULT_KEYWORD_CATALOGUE
    rows = []
    for category, terms in cat.items():
        for term in terms:
            rows.append({
                "term":     term.lower(),
                "category": category,
                "severity": _default_severity(category),
            })
    df = pd.DataFrame(rows)
    logger.info("Keyword catalogue built: %d terms", len(df))
    return df


def _default_severity(category: str) -> str:
    severity_map = {
        "gift_cards":  "high",
        "gifts":       "high",
        "sponsorship": "medium",
        "meals":       "medium",
        "travel":      "low",
    }
    return severity_map.get(category, "low")


# ─────────────────────────────────────────────
# KEYWORD ENGINE
# ─────────────────────────────────────────────

class KeywordEngine:
    """
    Phase 1 detection engine.
    Tokenises PR text and matches against keyword catalogue.
    """

    def __init__(
        self,
        keyword_df: pd.DataFrame | None = None,
    ) -> None:
        self.keyword_df = keyword_df or build_keyword_dataframe()

    # ╔══════════════════════════════════════════════════════════════╗
    # ║  SNIPPET: PPT-SLIDE-08 | Phase 1 | Keyword Lookup           ║
    # ║  STORY:   The entire compliance decision reduced to a        ║
    # ║           DataFrame lookup. Fast, brittle, context-blind.   ║
    # ║  OUTPUT:  matched_keywords list — what triggered the flag   ║
    # ╚══════════════════════════════════════════════════════════════╝

    def evaluate(self, pr: PurchaseRequisition) -> Phase1Result:
        """
        Evaluate a single PR against the keyword catalogue.
        Returns a Phase1Result with matched keywords and flag status.
        """
        start_ms = time.time() * 1000

        # Tokenise the full PR text
        tokens = self._tokenise(pr.full_text)

        # --- context: tokenisation (greyed in PPT) ---
        # Match tokens against every keyword in the catalogue

        # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
        matched = self.keyword_df[                                      #◄
            self.keyword_df["term"].isin(tokens)
        ]
        # └─────────────────────────────────────────────────────────────┘

        flagged          = len(matched) > 0
        matched_keywords = matched["term"].tolist()
        flag_reason      = ""

        if flagged:
            categories = matched["category"].unique().tolist()
            flag_reason = (
                f"Matched {len(matched_keywords)} keyword(s) "
                f"in categories: {', '.join(categories)}"
            )

        elapsed = (time.time() * 1000) - start_ms

        result = Phase1Result(
            pr_id              = pr.pr_id,
            matched_keywords   = matched_keywords,
            flagged            = flagged,
            flag_reason        = flag_reason,
            processing_time_ms = round(elapsed, 2),
        )

        logger.debug(
            "Phase1 | %s | flagged=%s | keywords=%s",
            pr.pr_id, flagged, matched_keywords,
        )
        return result

    def evaluate_batch(
        self,
        prs: list[PurchaseRequisition],
    ) -> list[Phase1Result]:
        """Evaluate a batch of PRs. Returns results in order."""
        return [self.evaluate(pr) for pr in prs]

    @staticmethod
    def _tokenise(text: str) -> set[str]:
        """
        Tokenise text into lowercase terms.
        Includes both single tokens and bigrams for
        multi-word keywords like 'gift card'.
        """
        import re
        clean  = re.sub(r"[^\w\s]", " ", text.lower())
        words  = clean.split()
        tokens = set(words)

        # Add bigrams
        for i in range(len(words) - 1):
            tokens.add(f"{words[i]} {words[i+1]}")

        return tokens

# SPEAKER NOTE (PPT-SLIDE-08):
#
# WHAT TO SAY (not read):
#   "This is the entire Phase 1 decision. The compliance team
#    maintained a spreadsheet of keywords. We tokenised the PR
#    text and checked for membership. If your PR description
#    contains 'dinner' — flagged. If it contains 'gift' — flagged.
#    It worked. We got immediate ROI. And then we looked at the
#    false positive rate and realised we had a problem."
#
# POINT AT:     the matched = keyword_df[...] block
# TRANSITION TO: "Let's look at what that false positive
#                 rate actually looked like..."
# AVOID SAYING: "As you can see in line 7..."