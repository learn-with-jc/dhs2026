# sentinel_x/platform/vector_store.py
"""
Sentinel-X | Vector Store + BM25 Retrieval

Wraps ChromaDB (dense) and BM25Okapi (sparse) into a unified
interface used by the retrieve_and_rerank agent.

Build the index first:
    make index

Then in agents:
    store = VectorStoreManager(VECTOR_STORE_DIR)
    store.load_existing()
    bm25  = BM25Retriever(store.policy_corpus)
    fused = hybrid_search(query, store, bm25, dense_top_k, sparse_top_k)
"""

from __future__ import annotations
import logging
from pathlib import Path

from sentinel_x.platform.data_models import RetrievedChunk

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    Persisted ChromaDB store for policy chunks and precedents.
    Dense retrieval uses cosine similarity over OpenAI embeddings.
    """

    POLICY_COLLECTION    = "sentinel_policies"
    PRECEDENT_COLLECTION = "sentinel_precedents"

    def __init__(self, persist_dir: Path | str) -> None:
        self.persist_dir     = Path(persist_dir)
        self._client         = None
        self._policy_col     = None
        self._precedent_col  = None
        self._policy_corpus: list[dict] = []

    # ── Internal helpers ───────────────────────────────────────

    def _client_(self):
        if self._client is None:
            import chromadb
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        return self._client

    @staticmethod
    def _embeddings():
        from sentinel_x.platform.llm_provider import get_embeddings
        return get_embeddings()

    # ── Public API ─────────────────────────────────────────────

    def load_existing(self) -> None:
        """Load persisted collections. Call once per process."""
        try:
            client = self._client_()
            self._policy_col = client.get_or_create_collection(
                name=self.POLICY_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._precedent_col = client.get_or_create_collection(
                name=self.PRECEDENT_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            count = self._policy_col.count()
            if count > 0:
                result = self._policy_col.get(include=["documents", "metadatas"])
                self._policy_corpus = [
                    {
                        "chunk_id":  m.get("chunk_id", f"chunk_{i}"),
                        "policy_id": m.get("policy_id", ""),
                        "content":   doc,
                        "metadata":  m,
                    }
                    for i, (doc, m) in enumerate(
                        zip(result["documents"], result["metadatas"])
                    )
                ]
                logger.info("Loaded %d policy chunks from vector store", count)
            else:
                logger.warning(
                    "Policy collection is empty — run 'make index' to build it"
                )
        except Exception as exc:
            logger.error("Failed to load vector store: %s", exc)

    def index_policies(self, docs: list) -> None:
        """Index LangChain Document objects into the policy collection."""
        embeddings = self._embeddings()
        client     = self._client_()

        try:
            client.delete_collection(self.POLICY_COLLECTION)
        except Exception:
            pass

        self._policy_col = client.create_collection(
            name=self.POLICY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

        texts     = [d.page_content for d in docs]
        metadatas = [d.metadata     for d in docs]
        ids       = [
            m.get("chunk_id", f"chunk_{i}")
            for i, m in enumerate(metadatas)
        ]

        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_ids   = ids[i : i + batch_size]
            batch_meta  = metadatas[i : i + batch_size]
            vectors     = embeddings.embed_documents(batch_texts)
            self._policy_col.add(
                ids=batch_ids,
                embeddings=vectors,
                documents=batch_texts,
                metadatas=batch_meta,
            )
            logger.info("Indexed batch %d–%d", i, i + len(batch_texts))

        logger.info("Indexed %d policy documents total", len(docs))

    def index_precedents(self, docs: list) -> None:
        """Index LangChain Document objects into the precedent collection."""
        embeddings = self._embeddings()
        client     = self._client_()

        try:
            client.delete_collection(self.PRECEDENT_COLLECTION)
        except Exception:
            pass

        self._precedent_col = client.create_collection(
            name=self.PRECEDENT_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

        texts     = [d.page_content for d in docs]
        metadatas = [d.metadata     for d in docs]
        ids       = [
            m.get("precedent_id", f"prec_{i}")
            for i, m in enumerate(metadatas)
        ]

        vectors = embeddings.embed_documents(texts)
        self._precedent_col.add(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("Indexed %d precedents", len(docs))

    @property
    def policy_corpus(self) -> list[dict]:
        """Raw corpus dicts used to build the BM25 index."""
        return self._policy_corpus

    def dense_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """Query ChromaDB with a query string. Returns RetrievedChunk list."""
        if not self._policy_col or self._policy_col.count() == 0:
            logger.warning("Dense search: policy collection empty")
            return []
        try:
            embeddings = self._embeddings()
            query_vec  = embeddings.embed_query(query)
            n_results  = min(top_k, self._policy_col.count())
            result     = self._policy_col.query(
                query_embeddings=[query_vec],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            chunks = []
            for doc, meta, dist in zip(
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            ):
                # ChromaDB cosine distance ∈ [0, 2]; convert to similarity [0, 1]
                score = max(0.0, 1.0 - dist / 2.0)
                chunks.append(RetrievedChunk(
                    chunk_id   = meta.get("chunk_id", ""),
                    policy_id  = meta.get("policy_id", ""),
                    content    = doc,
                    dense_score = score,
                ))
            return chunks
        except Exception as exc:
            logger.error("Dense search failed: %s", exc)
            return []


# ─────────────────────────────────────────────
# BM25 SPARSE RETRIEVER
# ─────────────────────────────────────────────

class BM25Retriever:
    """BM25Okapi sparse retriever over the policy corpus."""

    def __init__(self, corpus: list[dict]) -> None:
        self._corpus = corpus
        if corpus:
            from rank_bm25 import BM25Okapi
            tokenized   = [item["content"].lower().split() for item in corpus]
            self._bm25  = BM25Okapi(tokenized)
        else:
            self._bm25 = None
        logger.info("BM25 index built over %d documents", len(corpus))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self._bm25 or not self._corpus:
            return []
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            item = self._corpus[idx]
            results.append(RetrievedChunk(
                chunk_id     = item.get("chunk_id", ""),
                policy_id    = item.get("policy_id", ""),
                content      = item["content"],
                sparse_score = float(scores[idx]),
            ))
        return results


# ─────────────────────────────────────────────
# HYBRID SEARCH (RRF FUSION)
# ─────────────────────────────────────────────

def hybrid_search(
    query:       str,
    store:       VectorStoreManager,
    bm25:        BM25Retriever,
    dense_top_k: int = 20,
    sparse_top_k: int = 20,
    rrf_k:       int = 60,
) -> list[RetrievedChunk]:
    """
    Fuse dense and sparse results using Reciprocal Rank Fusion.

    RRF score = Σ 1 / (k + rank_i) across retrieval methods.
    Uses the initial rerank_score field to carry the fused score
    so the BGE reranker can override it in the next step.
    """
    dense_results  = store.dense_search(query, dense_top_k)
    sparse_results = bm25.search(query, sparse_top_k)

    # Merge chunks by chunk_id (dense takes precedence for content)
    chunk_map: dict[str, RetrievedChunk] = {}
    for chunk in dense_results:
        chunk_map[chunk.chunk_id] = chunk
    for chunk in sparse_results:
        if chunk.chunk_id not in chunk_map:
            chunk_map[chunk.chunk_id] = chunk
        else:
            chunk_map[chunk.chunk_id].sparse_score = chunk.sparse_score

    # RRF scoring
    rrf_scores: dict[str, float] = {}
    for rank, chunk in enumerate(dense_results, start=1):
        rrf_scores[chunk.chunk_id] = (
            rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
        )
    for rank, chunk in enumerate(sparse_results, start=1):
        rrf_scores[chunk.chunk_id] = (
            rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
        )

    sorted_ids = sorted(
        rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True
    )

    result = []
    for cid in sorted_ids:
        chunk = chunk_map[cid]
        chunk.rerank_score = rrf_scores[cid]
        result.append(chunk)

    logger.info(
        "Hybrid search: dense=%d sparse=%d fused=%d",
        len(dense_results), len(sparse_results), len(result),
    )
    return result
