# sentinel_x/platform/document_processor.py
"""
Sentinel-X | Document Processor

Handles ingestion and chunking of policy documents
and purchase requisition attachments.

Key design decision: policy documents are NOT chunked naively.
Hierarchical chunking preserves cross-references and
conditional logic that flat chunking destroys.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import date

from langchain_core.documents import Document

from sentinel_x.platform.data_models import (
    PolicyDocument, PolicyChunk, IncentiveCategory,
    PurchaseRequisition,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# POLICY DOCUMENT LOADER
# ─────────────────────────────────────────────

def load_policy_document(filepath: Path) -> PolicyDocument:
    """
    Load a policy markdown file into a PolicyDocument model.
    Extracts metadata from the header block.
    """
    raw = filepath.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # Parse metadata from markdown header
    meta: dict = {}
    for line in lines[:10]:
        if line.startswith("**Version:**"):
            meta["version"] = line.split("**Version:**")[-1].strip()
        elif line.startswith("**Effective Date:**"):
            meta["effective_date"] = line.split("**Effective Date:**")[-1].strip()
        elif line.startswith("**Category:**"):
            meta["category"] = line.split("**Category:**")[-1].strip()

    policy_id   = filepath.stem.split("_")[0]
    policy_name = filepath.stem.replace("_", " ").replace(policy_id, "").strip()

    return PolicyDocument(
        policy_id      = policy_id,
        policy_name    = policy_name,
        version        = meta.get("version", "1.0"),
        effective_date = _parse_date(meta.get("effective_date", "2024-01-01")),
        category       = IncentiveCategory(meta.get("category", "other")),
        content        = raw,
    )


# ─────────────────────────────────────────────
# HIERARCHICAL CHUNKING
#
# Design rationale (PPT beat):
#   Policy documents contain cross-references, conditional
#   tables, and exception clauses. Chunking at paragraph level
#   breaks this context. Chunking at section level is large
#   but preserves the reasoning unit.
#   Solution: small chunks for retrieval, section chunks
#   for reasoning — hierarchical, not flat.
# ─────────────────────────────────────────────

def chunk_policy_document(
    doc: PolicyDocument,
    small_chunk_size:  int = 512,
    small_chunk_overlap: int = 64,
) -> list[PolicyChunk]:
    """
    Produce two levels of chunks from a policy document:

    Level 1 — Section chunks (## heading boundaries)
        Used as the reasoning context: large enough to
        preserve conditional logic and cross-references.

    Level 2 — Small chunks (sliding window within each section)
        Used for dense retrieval: granular enough to surface
        specific threshold values and rule references.

    Each small chunk carries a parent_section reference
    so the orchestrator can fetch the full section context
    when the small chunk is retrieved.
    """
    sections = _split_by_heading(doc.content)
    all_chunks: list[PolicyChunk] = []

    for section_idx, (heading, section_text) in enumerate(sections):
        # Level 1: one chunk per section
        section_chunk_id = f"{doc.policy_id}-S{section_idx:02d}"
        all_chunks.append(
            PolicyChunk(
                chunk_id       = section_chunk_id,
                policy_id      = doc.policy_id,
                policy_name    = doc.policy_name,
                section        = heading,
                content        = section_text,
                category       = doc.category,
                version        = doc.version,
                effective_date = doc.effective_date,
                keywords       = _extract_keywords(section_text),
            )
        )

        # Level 2: sliding window within each section
        small_chunks = _sliding_window(
            text       = section_text,
            chunk_size = small_chunk_size,
            overlap    = small_chunk_overlap,
        )

        for sub_idx, small_text in enumerate(small_chunks):
            # Skip if near-duplicate of section chunk (short section)
            if len(small_text.strip()) < 100:
                continue
            all_chunks.append(
                PolicyChunk(
                    chunk_id       = f"{section_chunk_id}-c{sub_idx:02d}",
                    policy_id      = doc.policy_id,
                    policy_name    = doc.policy_name,
                    section        = heading,
                    content        = small_text,
                    category       = doc.category,
                    version        = doc.version,
                    effective_date = doc.effective_date,
                    keywords       = _extract_keywords(small_text),
                )
            )

    logger.info(
        "Chunked policy %s → %d chunks", doc.policy_id, len(all_chunks)
    )
    return all_chunks


def policy_chunks_to_documents(
    chunks: list[PolicyChunk],
) -> list[Document]:
    """
    Convert PolicyChunk objects to LangChain Document objects
    for ingestion into ChromaDB.
    """
    return [
        Document(
            page_content = chunk.content,
            metadata     = {
                "chunk_id":       chunk.chunk_id,
                "policy_id":      chunk.policy_id,
                "policy_name":    chunk.policy_name,
                "section":        chunk.section,
                "category":       chunk.category.value,
                "version":        chunk.version,
                "effective_date": str(chunk.effective_date),
                "keywords":       ",".join(chunk.keywords),
            },
        )
        for chunk in chunks
    ]


# ─────────────────────────────────────────────
# PR ATTACHMENT PROCESSOR
# ─────────────────────────────────────────────

def process_pr_attachments(pr: PurchaseRequisition) -> list[Document]:
    """
    Convert simulated PR attachment content into Documents
    for retrieval and analysis.

    In production: this is where PDF parsing, OCR, and
    image processing would occur. For the demo, we use
    the simulated_content field directly.
    """
    docs = []
    for attachment in pr.attachments:
        docs.append(
            Document(
                page_content = attachment.simulated_content,
                metadata     = {
                    "source":    "pr_attachment",
                    "pr_id":     pr.pr_id,
                    "filename":  attachment.filename,
                    "file_type": attachment.file_type,
                },
            )
        )
    return docs


# ─────────────────────────────────────────────
# PRECEDENT LOADER
# ─────────────────────────────────────────────

def load_precedents(filepath: Path) -> list[Document]:
    """
    Load the precedent store JSONL file into LangChain Documents.
    Each precedent becomes a searchable document with rich metadata.
    """
    docs = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            content = (
                f"Case: {record['pr_summary']}\n"
                f"Decision: {record['decision']}\n"
                f"Rationale: {record['rationale']}\n"
                f"Policies: {', '.join(record['policy_refs'])}"
            )
            docs.append(
                Document(
                    page_content = content,
                    metadata     = {
                        "source":         "precedent",
                        "precedent_id":   record["precedent_id"],
                        "decision":       record["decision"],
                        "category":       record["category"],
                        "recipient_type": record["recipient_type"],
                        "amount":         record["amount"],
                        "policy_refs":    ",".join(record["policy_refs"]),
                    },
                )
            )
    logger.info("Loaded %d precedents from %s", len(docs), filepath)
    return docs


# ─────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────

def _split_by_heading(text: str) -> list[tuple[str, str]]:
    """Split markdown by ## headings. Returns (heading, content) tuples."""
    import re
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [("document", text)]

    sections = []
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start   = match.start()
        end     = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections.append((heading, content))

    return sections


def _sliding_window(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Simple character-level sliding window chunker."""
    chunks = []
    start  = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _extract_keywords(text: str) -> list[str]:
    """
    Lightweight keyword extraction for metadata enrichment.
    Extracts USD amounts, policy article numbers, and key terms.
    """
    import re
    keywords = set()

    # USD amounts
    for match in re.finditer(r"USD\s*[\d,]+", text):
        keywords.add(match.group().replace(" ", "").upper())

    # Policy references
    for match in re.finditer(r"POL-\d+", text):
        keywords.add(match.group())

    # Exception references
    for match in re.finditer(r"EXC-\d+", text):
        keywords.add(match.group())

    # Key compliance terms
    compliance_terms = [
        "gsmm", "gte", "vp approval", "svp", "legal review",
        "prohibited", "mandatory", "threshold", "prior approval",
        "public sector", "government", "gift card", "sponsorship",
    ]
    text_lower = text.lower()
    for term in compliance_terms:
        if term in text_lower:
            keywords.add(term.replace(" ", "_"))

    return sorted(keywords)


def _parse_date(date_str: str) -> date:
    """Parse YYYY-MM-DD date string safely."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return date(2024, 1, 1)