# sentinel_x/platform/llm_provider.py
"""
Sentinel-X | Provider-Agnostic LLM Swap Layer

The single gateway for all LLM access across every phase and agent.
Swap the provider in .env — nothing else changes.

Supported providers:
  - openai    : GPT-4o (default)
  - anthropic : Claude 3.5 Sonnet
  - ollama    : Mixtral (local)

# ╔══════════════════════════════════════════════════════════════╗
# ║  SNIPPET: PPT-SLIDE-13 | Phase 2 | Provider Swap Layer      ║
# ║  STORY:   One line in .env changes the entire model stack    ║
# ║  OUTPUT:  Same interface, any provider — architecture        ║
# ║           decision that future-proofs the system             ║
# ╚══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations
import logging
from functools import lru_cache
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

ProviderType = Literal["openai", "anthropic", "ollama"]


# ─────────────────────────────────────────────
# LLM FACTORY
# ─────────────────────────────────────────────

# ╔══════════════════════════════════════════════════════════════╗
# ║  SNIPPET: PPT-SLIDE-13 | Phase 2 | Provider Swap Layer      ║
# ╚══════════════════════════════════════════════════════════════╝

def get_llm(
    provider: ProviderType | None = None,
    model:    str | None = None,
    temperature: float | None = None,
    max_tokens:  int | None = None,
) -> BaseChatModel:
    """
    Return a LangChain-compatible chat model for the given provider.
    Falls back to settings if arguments not supplied.
    """
    from config.settings import (
        LLM_PROVIDER, MODELS,
        LLM_TEMPERATURE, LLM_MAX_TOKENS,
        OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL,
    )

    _provider    = provider    or LLM_PROVIDER
    _model       = model       or MODELS[_provider]
    _temperature = temperature if temperature is not None else LLM_TEMPERATURE
    _max_tokens  = max_tokens  or LLM_MAX_TOKENS

    logger.info(
        "Initialising LLM | provider=%s model=%s temp=%.1f",
        _provider, _model, _temperature,
    )

    # --- provider selection (context lines — greyed in PPT) ---
    if _provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=_model,
            temperature=_temperature,
            max_tokens=_max_tokens,
            api_key=OPENAI_API_KEY,
        )

    if _provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=_model,
            temperature=_temperature,
            max_tokens=_max_tokens,
            api_key=ANTHROPIC_API_KEY,
        )

    if _provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=_model,
            temperature=_temperature,
            base_url=OLLAMA_BASE_URL,
        )

    raise ValueError(
        f"Unknown provider '{_provider}'. "
        f"Choose from: openai | anthropic | ollama"
    )

# ┌─ THE LINE THAT MATTERS ────────────────────────────────────┐
# llm = get_llm(provider=settings.LLM_PROVIDER)               #◄
# └─────────────────────────────────────────────────────────────┘
# Change LLM_PROVIDER in .env. Nothing else in the codebase
# needs to know which model is running.

# 🛡️ GUARDRAIL: validate API key exists before first LLM call
def validate_provider_config(provider: ProviderType | None = None) -> None:
    from config.settings import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY
    _provider = provider or LLM_PROVIDER
    if _provider == "openai" and not OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Add it to your .env file."
        )
    if _provider == "anthropic" and not ANTHROPIC_API_KEY:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file."
        )
    logger.info("Provider config validated for: %s", _provider)

# SPEAKER NOTE (PPT-SLIDE-13):
#
# WHAT TO SAY (not read):
#   "Every agent, every phase, every prompt call goes through
#    this one function. Change one line in your .env file and
#    the entire system switches from GPT-4 to Claude to a local
#    Mixtral. We built this on day one because model benchmarking
#    was part of Phase 2 — and we didn't want to rewrite agents
#    every time we swapped a model."
#
# POINT AT:     get_llm() signature and the #◄ comment below it
# TRANSITION TO: "Now let's look at how documents get processed
#                 before any LLM ever sees them..."
# AVOID SAYING: "As you can see in line 7..."


# ─────────────────────────────────────────────
# EMBEDDING FACTORY
# ─────────────────────────────────────────────

@lru_cache(maxsize=2)
def get_embeddings(
    provider: ProviderType | None = None,
    model:    str | None = None,
) -> Embeddings:
    """
    Return a LangChain-compatible embeddings model.
    Cached — embeddings model is expensive to initialise.
    """
    from config.settings import (
        LLM_PROVIDER, EMBEDDING_MODEL, OPENAI_API_KEY, OLLAMA_BASE_URL
    )

    _provider = provider or LLM_PROVIDER
    _model    = model    or EMBEDDING_MODEL

    logger.info(
        "Initialising embeddings | provider=%s model=%s",
        _provider, _model,
    )

    if _provider in ("openai", "anthropic"):
        # Anthropic does not expose embeddings API — use OpenAI
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=_model,
            api_key=OPENAI_API_KEY,
        )

    if _provider == "ollama":
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(
            model=_model,
            base_url=OLLAMA_BASE_URL,
        )

    raise ValueError(f"Unknown provider '{_provider}'")