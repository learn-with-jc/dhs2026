# sentinel_x/phase3_agentic/agents/extract_evidence.py
"""
Sentinel-X | Agent 7 — Extract Evidence

When a violation or review flag is warranted, this agent
extracts the specific policy chunks that constitute
the evidence for the finding.

Evidence extraction separates the verdict from the proof.
The output of this agent is what the human reviewer sees —
concrete citations, not a summary.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from sentinel_x.platform.data_models import TraceEvent, RetrievedChunk
from sentinel_x.platform.llm_provider import get_llm
from sentinel_x.phase3_agentic.state import SentinelState

logger = logging.getLogger(__name__)


class EvidenceOutput(BaseModel):
    cited_chunk_ids:    list[str]
    violation_points:   list[str] = Field(
        description="Specific rule violations or concerns"
    )
    supporting_quotes:  list[str] = Field(
        description="Direct quotes from policy chunks"
    )
    evidence_summary:   str


EXTRACT_EVIDENCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an evidence extraction agent. Given a \
compliance reasoning and policy chunks, extract the specific \
evidence that supports the compliance finding.

Cite exact chunk IDs. Quote relevant policy text directly.
Do not paraphrase policy language — quote it exactly.
Return JSON: {format_instructions}"""),

    ("human", """Compliance Reasoning:
{reasoning}

Available Policy Chunks:
{chunks}

Extract the evidence that proves or supports the compliance verdict.
"""),
])


def extract_evidence_node(state: SentinelState) -> dict:
    """LangGraph node: extract evidence citations from policy chunks."""
    t0     = time.time() * 1000
    chunks = state["reranked_chunks"]

    chunk_text = "\n\n".join([
        f"[{c.chunk_id}] Policy {c.policy_id}:\n{c.content[:500]}"
        for c in chunks
    ])

    llm    = get_llm()
    parser = JsonOutputParser(pydantic_object=EvidenceOutput)
    chain  = EXTRACT_EVIDENCE_PROMPT | llm | parser

    try:
        raw    = chain.invoke({
            "reasoning":           state["initial_reasoning"],
            "chunks":              chunk_text,
            "format_instructions": parser.get_format_instructions(),
        })
        output = EvidenceOutput(**raw)

        # Mark cited chunks
        cited_set = set(output.cited_chunk_ids)
        evidence_chunks = [
            RetrievedChunk(
                **{**c.model_dump(), "is_cited": c.chunk_id in cited_set}
            )
            for c in chunks
        ]

    except Exception as exc:
        logger.error("extract_evidence failed: %s", exc)
        output         = EvidenceOutput(
            cited_chunk_ids=[], violation_points=[],
            supporting_quotes=[], evidence_summary=f"Extraction failed: {exc}",
        )
        evidence_chunks = chunks

    elapsed = (time.time() * 1000) - t0
    trace   = TraceEvent(
        agent_name     = "extract_evidence",
        timestamp      = datetime.utcnow(),
        input_summary  = f"Extracting from {len(chunks)} chunks",
        output_summary = (
            f"cited={len(output.cited_chunk_ids)} | "
            f"violations={len(output.violation_points)}"
        ),
        confidence     = state["confidence_score"],
        duration_ms    = elapsed,
    )

    return {
        "evidence":  evidence_chunks,
        "trace_log": [trace],
    }