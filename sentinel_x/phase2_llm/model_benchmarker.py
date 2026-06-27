# sentinel_x/phase2_llm/model_benchmarker.py
"""
Sentinel-X | Phase 2 — Model Benchmarker

During Phase 2 development we evaluated multiple LLM providers:
  - OpenAI GPT-4o
  - Anthropic Claude 3.5 Sonnet
  - Ollama Mixtral (local)

This module runs the same PRs through each configured
provider and produces a comparison report.

Use this to demonstrate the provider-agnostic swap layer
in action and to show the model selection process.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field

from sentinel_x.platform.data_models import PurchaseRequisition, RiskLabel
from sentinel_x.platform.llm_provider import get_llm, ProviderType
from sentinel_x.phase2_llm.compliance_filter import ComplianceFilter

logger = logging.getLogger(__name__)


@dataclass
class ModelBenchmarkResult:
    provider:           ProviderType
    model_name:         str
    pr_id:              str
    verdict:            str
    confidence:         float
    latency_ms:         float
    agrees_with_ground_truth: bool


@dataclass
class BenchmarkReport:
    results:    list[ModelBenchmarkResult] = field(default_factory=list)

    def accuracy_by_provider(self) -> dict[str, float]:
        by_provider: dict[str, list[bool]] = {}
        for r in self.results:
            by_provider.setdefault(r.provider, []).append(
                r.agrees_with_ground_truth
            )
        return {
            p: round(sum(v) / len(v), 3)
            for p, v in by_provider.items()
        }

    def avg_latency_by_provider(self) -> dict[str, float]:
        by_provider: dict[str, list[float]] = {}
        for r in self.results:
            by_provider.setdefault(r.provider, []).append(r.latency_ms)
        return {
            p: round(sum(v) / len(v), 1)
            for p, v in by_provider.items()
        }

    def print_report(self) -> None:
        accuracy = self.accuracy_by_provider()
        latency  = self.avg_latency_by_provider()
        print("\n" + "═" * 55)
        print("  MODEL BENCHMARK REPORT")
        print("═" * 55)
        print(f"  {'Provider':<20} {'Accuracy':>10} {'Avg Latency':>15}")
        print("  " + "─" * 48)
        for provider in accuracy:
            print(
                f"  {provider:<20} "
                f"{accuracy[provider]:>9.1%} "
                f"{latency.get(provider, 0):>12.0f}ms"
            )
        print("═" * 55 + "\n")


class ModelBenchmarker:
    """
    Run the same PR set through multiple LLM providers
    and compare accuracy vs latency vs cost.
    """

    def __init__(
        self,
        providers: list[ProviderType] | None = None,
    ) -> None:
        from config.settings import MODELS
        self.providers  = providers or ["openai"]
        self.model_map  = MODELS
        logger.info("ModelBenchmarker ready for: %s", self.providers)

    def benchmark(
        self,
        prs: list[PurchaseRequisition],
    ) -> BenchmarkReport:
        report = BenchmarkReport()

        for provider in self.providers:
            logger.info("Benchmarking provider: %s", provider)
            try:
                # Swap provider via the provider-agnostic layer
                # 🛡️ GUARDRAIL: skip unavailable providers gracefully
                filter_instance = self._build_filter_for_provider(provider)
            except Exception as exc:
                logger.warning(
                    "Provider %s unavailable: %s — skipping", provider, exc
                )
                continue

            for pr in prs:
                t0 = time.time() * 1000
                try:
                    result  = filter_instance.evaluate(pr)
                    elapsed = (time.time() * 1000) - t0
                    correct = self._check_ground_truth(pr, result.final_verdict)
                    report.results.append(ModelBenchmarkResult(
                        provider    = provider,
                        model_name  = self.model_map.get(provider, provider),
                        pr_id       = pr.pr_id,
                        verdict     = result.final_verdict.value,
                        confidence  = result.confidence,
                        latency_ms  = elapsed,
                        agrees_with_ground_truth = correct,
                    ))
                except Exception as exc:
                    logger.error(
                        "Benchmark error | %s | %s: %s",
                        provider, pr.pr_id, exc,
                    )

        return report

    def _build_filter_for_provider(
        self, provider: ProviderType
    ) -> ComplianceFilter:
        """Build a ComplianceFilter instance with a specific provider LLM."""
        import os
        os.environ["LLM_PROVIDER"] = provider
        return ComplianceFilter()

    @staticmethod
    def _check_ground_truth(
        pr: PurchaseRequisition,
        verdict: RiskLabel,
    ) -> bool:
        is_violation = pr.risk_label in (
            RiskLabel.REVIEW_NEEDED, RiskLabel.NON_COMPLIANT
        )
        was_flagged  = verdict != RiskLabel.COMPLIANT
        return is_violation == was_flagged