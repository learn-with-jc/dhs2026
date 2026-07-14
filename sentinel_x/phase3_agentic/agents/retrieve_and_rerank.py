# sentinel_x/phase3_agentic/agents/retrieve_and_rerank.py
"""
Sentinel-X | Agent 3 — Retrieve

Executes the 3-step retrieval pipeline:
  Step 1: Dense retrieval (ChromaDB)
  Step 2: Sparse retrieval (BM25)
  Step 3: RRF fusion → top-K by score

Filters retrieved chunks to only those from
matched policies (classified in previous node).
"""

from __future__ import annotations
import logging
import time
from datetime import datetime
from functools import lru_cache

from sentinel_x.platform.data_models import (
    PurchaseRequisition, TraceEvent,
)
from sentinel_x.platform.vector_store import (
    VectorStoreManager, BM25Retriever, hybrid_search,
)
from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_store_and_bm25() -> tuple[VectorStoreManager, BM25Retriever]:
    """
    Load vector store and BM25 index once per process.
    lru_cache ensures we don't reload on every agent call.
    """
    from config.settings import VECTOR_STORE_DIR
    store = VectorStoreManager(VECTOR_STORE_DIR)
    store.load_existing()
    bm25 = BM25Retriever(store.policy_corpus)
    return store, bm25


def retrieve_and_rerank_node(state: SentinelState) -> dict:
    """LangGraph node: hybrid search, return top-K by RRF score."""
    from config.settings import DENSE_TOP_K, SPARSE_TOP_K, RERANK_TOP_K

    t0             = time.time() * 1000
    pr             = PurchaseRequisition(**state["pr_data"])
    intent         = state["extracted_intent"]
    matched_pols   = state["matched_policies"]
    retry_count    = state["retry_count"]

    # Build retrieval query from intent + PR description
    query = (
        f"{pr.description} "
        f"{' '.join(intent.get('incentive_items', []))} "
        f"{' '.join(intent.get('risk_indicators', []))} "
        f"policy compliance threshold approval"
    )

    # On retry: enrich query with critique feedback
    if retry_count > 0 and state.get("critique_output"):
        query = f"{query} {state['critique_output'][:200]}"
        logger.info("Retry %d: enriched query with critique", retry_count)

    store, bm25 = _get_store_and_bm25()

    # Hybrid search
    fused_chunks = hybrid_search(
        query        = query,
        store        = store,
        bm25         = bm25,
        dense_top_k  = DENSE_TOP_K,
        sparse_top_k = SPARSE_TOP_K,
    )

    # Filter to matched policies only
    if matched_pols:
        filtered = [
            c for c in fused_chunks
            if c.policy_id in matched_pols
        ]
        # 🛡️ GUARDRAIL: if filter leaves too few chunks, relax it
        if len(filtered) < 3:
            logger.warning(
                "Policy filter too restrictive (%d chunks) — using all",
                len(filtered),
            )
            filtered = fused_chunks
    else:
        filtered = fused_chunks

    # Take top-K by RRF score
    reranked = sorted(filtered, key=lambda c: c.rerank_score, reverse=True)[:RERANK_TOP_K]

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "retrieve_and_rerank",
        timestamp      = datetime.utcnow(),
        input_summary  = f"query={query[:80]} | policies={matched_pols}",
        output_summary = f"retrieved={len(fused_chunks)} → top_k={len(reranked)}",
        confidence     = reranked[0].rerank_score if reranked else 0.0,
        duration_ms    = elapsed,
        notes          = f"retry={retry_count}",
    )

    return {
        "retrieved_chunks": fused_chunks,
        "reranked_chunks":  reranked,
        "trace_log":        [trace],
    }