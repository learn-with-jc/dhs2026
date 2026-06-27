# sentinel_x/platform/reranker.py
"""
Sentinel-X | BAAI/bge-reranker-v2-m3 Cross-Encoder Reranker

Step 4 of the retrieval pipeline.
Takes the top-N fused results and re-scores them using
a cross-encoder that jointly encodes the query AND the
document — far more accurate than bi-encoder similarity.

Why this matters:
  Retrieval rank answers: "which chunks look like the query?"
  Reranker rank answers:  "which chunks actually answer the query?"
  In compliance, the difference is between finding a policy
  section that mentions 'gifts' and finding the one that
  defines the exact threshold for the gift type in this PR.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from sentinel_x.platform.data_models import RetrievedChunk

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class BGEReranker:
    """
    BAAI/bge-reranker-v2-m3 cross-encoder wrapper.
    Loaded once and reused across all agent calls.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        logger.info("Loading reranker: %s", model_name)
        try:
            from sentence_transformers import CrossEncoder
            self.model      = CrossEncoder(model_name)
            self.model_name = model_name
            self._available = True
            logger.info("Reranker loaded successfully")
        except Exception as exc:
            logger.warning(
                "Reranker unavailable (%s). "
                "Falling back to RRF scores only.",
                exc,
            )
            self.model      = None
            self._available = False

    def rerank(
        self,
        query:  str,
        chunks: list[RetrievedChunk],
        top_k:  int = 5,
    ) -> list[RetrievedChunk]:
        """
        Re-score chunks against the query using cross-encoder.
        Returns top_k chunks sorted by rerank_score descending.

        # ╔══════════════════════════════════════════════════════════════╗
        # ║  SNIPPET: PPT-SLIDE-17 | Phase 3 | Reranker                 ║
        # ║  STORY:   Retrieval finds candidates. Reranker finds         ║
        # ║           the answer. They are not the same job.             ║
        # ║  OUTPUT:  5 chunks that actually answer the compliance       ║
        # ║           question, not just chunks that match keywords      ║
        # ╚══════════════════════════════════════════════════════════════╝
        """
        if not self._available or not chunks:
            # Graceful fallback: return top_k by existing RRF score
            return sorted(
                chunks,
                key     = lambda c: c.rerank_score,
                reverse = True,
            )[:top_k]

        # Build (query, passage) pairs for cross-encoder
        pairs = [(query, chunk.content) for chunk in chunks]

        # Score all pairs in one batch
        scores = self.model.predict(pairs)

        # ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
        reranked = sorted(                                              #◄
            zip(chunks, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        # └─────────────────────────────────────────────────────────────┘

        result = []
        for chunk, score in reranked[:top_k]:
            chunk.rerank_score = float(score)
            result.append(chunk)

        logger.info(
            "Reranked %d chunks → top %d | top score: %.4f",
            len(chunks), top_k, result[0].rerank_score if result else 0,
        )
        return result

# SPEAKER NOTE (PPT-SLIDE-17):
#
# WHAT TO SAY (not read):
#   "After fusion we have 30 candidate chunks. The reranker
#    reads each one alongside the full query — jointly — and
#    gives a score that reflects actual relevance to the
#    compliance question, not just surface similarity.
#    We go from 30 candidates to 5 chunks that the reasoning
#    agent will actually use. The quality of what the agent
#    reasons over is determined here. Garbage in, garbage out
#    applies to RAG just as much as it applies to data."
#
# POINT AT:     the reranked = sorted(...) block
# TRANSITION TO: "Now those 5 chunks go into the reasoning
#                 agent. Let's watch what happens..."
# AVOID SAYING: "As you can see in line 7..."