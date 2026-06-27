# config/settings.py
"""
Sentinel-X | Central Configuration
All environment-driven settings with safe defaults.
Single place to change models, thresholds, and paths.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# PROJECT PATHS
# ─────────────────────────────────────────────
BASE_DIR          = Path(__file__).resolve().parent.parent
DATA_DIR          = BASE_DIR / "data"
RAW_DIR           = DATA_DIR / "raw"
PROCESSED_DIR     = DATA_DIR / "processed"
POLICY_DIR        = RAW_DIR  / "policies"
PR_DIR            = RAW_DIR  / "purchase_requisitions"
PRECEDENT_DIR     = RAW_DIR  / "precedents"
VECTOR_STORE_DIR  = PROCESSED_DIR / "vector_store"
AUDIT_LOG_DIR     = PROCESSED_DIR / "audit_logs"

# ─────────────────────────────────────────────
# LLM PROVIDER CONFIGURATION
# ─────────────────────────────────────────────
LLM_PROVIDER      = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Model names per provider
MODELS = {
    "openai":    os.getenv("OPENAI_MODEL",    "gpt-4o"),
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
    "ollama":    os.getenv("OLLAMA_MODEL",    "mixtral"),
}

LLM_TEMPERATURE   = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS    = int(os.getenv("LLM_MAX_TOKENS",    "2048"))

# ─────────────────────────────────────────────
# PHASE 3 — AGENTIC THRESHOLDS
# ─────────────────────────────────────────────
CONFIDENCE_THRESHOLD     = float(os.getenv("CONFIDENCE_THRESHOLD",     "0.85"))
CRITIQUE_THRESHOLD       = float(os.getenv("CRITIQUE_THRESHOLD",       "0.70"))
ESCALATION_THRESHOLD     = float(os.getenv("ESCALATION_THRESHOLD",     "0.50"))
MAX_RETRY_COUNT          = int(os.getenv("MAX_RETRY_COUNT",            "2"))

# ─────────────────────────────────────────────
# RETRIEVAL CONFIGURATION
# ─────────────────────────────────────────────
DENSE_TOP_K              = int(os.getenv("DENSE_TOP_K",                "20"))
SPARSE_TOP_K             = int(os.getenv("SPARSE_TOP_K",               "20"))
RERANK_TOP_K             = int(os.getenv("RERANK_TOP_K",               "5"))
RERANKER_MODEL           = os.getenv(
                               "RERANKER_MODEL",
                               "BAAI/bge-reranker-v2-m3"
                           )
EMBEDDING_MODEL          = os.getenv(
                               "EMBEDDING_MODEL",
                               "text-embedding-3-small"
                           )
CHUNK_SIZE               = int(os.getenv("CHUNK_SIZE",                 "512"))
CHUNK_OVERLAP            = int(os.getenv("CHUNK_OVERLAP",              "64"))

# ─────────────────────────────────────────────
# PHASE 4 — POLICY THRESHOLDS
# (Deterministic rule engine — not LLM driven)
# ─────────────────────────────────────────────
THRESHOLDS = {
    "employee": {
        "single_gift":          150.0,
        "annual_gift":          500.0,
        "meal_per_head":         75.0,
        "meal_total_prior_approval": 500.0,
    },
    "customer_private": {
        "single_gift":          150.0,
        "annual_gift":          500.0,
        "meal_per_head":        150.0,
        "meal_total_prior_approval": 500.0,
    },
    "customer_public": {
        "default": {
            "meal_per_head":     50.0,
            "single_gift":       20.0,
        },
        "US_Level1": {
            "meal_per_head":     50.0,
            "single_gift":       20.0,
        },
        "KR_Level2": {
            "meal_per_head":     50.0,
            "single_gift":       20.0,
            "total_hard_cap":   100.0,
        },
        "IN": {
            "meal_per_head":     25.0,
            "single_gift":       15.0,
        },
    },
}

SPONSORSHIP_THRESHOLDS = {
    "gsmm_required_above":       5_000.0,
    "gte_required_above":       25_000.0,
    "vp_approval_above":        25_000.0,
    "svp_legal_approval_above": 50_000.0,
}

# ─────────────────────────────────────────────
# APPROVED EXCEPTIONS
# ─────────────────────────────────────────────
APPROVED_EXCEPTION_VENDORS   = ["dowlis", "dowlis corp", "dowlis platform"]
APPROVED_EXCEPTION_CATALOG   = {
    "EXC-003": "Dowlis charitable donation vouchers",
    "EXC-007": "Mobility device with documented medical need",
}

# ─────────────────────────────────────────────
# TAXONOMY PRIORITY ORDER
# (Higher index = higher priority)
# ─────────────────────────────────────────────
TAXONOMY_PRIORITY = [
    "other",
    "travel",
    "meals",
    "gifts",
    "sponsorship",
    "gift_cards",
]

# ─────────────────────────────────────────────
# OBSERVABILITY
# ─────────────────────────────────────────────
LOG_LEVEL                = os.getenv("LOG_LEVEL", "INFO")
ENABLE_LANGSMITH         = os.getenv("ENABLE_LANGSMITH", "false").lower() == "true"
LANGSMITH_API_KEY        = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT        = os.getenv("LANGSMITH_PROJECT", "sentinel-x")