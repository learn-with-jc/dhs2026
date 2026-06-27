# sentinel_x/observability/graph_visualizer.py
"""
Sentinel-X | Observability — LangGraph Visualizer

Generates a visual representation of the agent graph
execution trace. Used in the Streamlit app.

Produces Mermaid diagram syntax showing:
  - Which nodes executed
  - Which edges were traversed
  - Confidence at each node
  - Whether loops occurred
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

# All possible nodes in execution order
ALL_NODES = [
    "extract_intent",
    "classify_policy",
    "retrieve_and_rerank",
    "reason_compliance",
    "verdict_gate",
    "critique_reasoning",
    "extract_evidence",
    "generate_recommendation",
]

NODE_LABELS = {
    "extract_intent":          "Extract Intent",
    "classify_policy":         "Classify Policy",
    "retrieve_and_rerank":     "Retrieve + Rerank",
    "reason_compliance":       "Reason Compliance",
    "verdict_gate":            "Verdict Gate",
    "critique_reasoning":      "Critique",
    "extract_evidence":        "Extract Evidence",
    "generate_recommendation": "Recommend",
}


def build_execution_mermaid(
    trace_log: list[dict | Any],
    final_verdict: str = "",
    escalated: bool = False,
) -> str:
    """
    Build a Mermaid flowchart from a LangGraph trace log.
    Shows the actual execution path including any loops.
    """
    executed = []
    conf_map = {}

    for event in trace_log:
        if isinstance(event, dict):
            name = event.get("agent_name", "")
            conf = event.get("confidence", 0.0)
        else:
            name = getattr(event, "agent_name", "")
            conf = getattr(event, "confidence", 0.0)

        if name:
            executed.append(name)
            conf_map[name] = conf

    lines = ["flowchart TD"]

    # Node styling
    for node in ALL_NODES:
        label    = NODE_LABELS.get(node, node)
        conf_str = f"\nconf:{conf_map.get(node, 0):.2f}" if node in conf_map else ""
        if node not in executed:
            lines.append(f'    {node}["{label}"]:::skipped')
        elif node == "critique_reasoning":
            lines.append(f'    {node}["{label}{conf_str}"]:::critique')
        elif node == "verdict_gate":
            lines.append(f'    {node}{{"{label}{conf_str}"}}:::gate')
        else:
            lines.append(f'    {node}["{label}{conf_str}"]:::executed')

    lines.append("")

    # Edges — trace actual execution sequence
    for i in range(len(executed) - 1):
        src  = executed[i]
        dst  = executed[i + 1]
        loop = dst in executed[:i]
        if loop:
            lines.append(f"    {src} -->|retry| {dst}")
        else:
            lines.append(f"    {src} --> {dst}")

    # Final outcome node
    if escalated:
        lines.append('    generate_recommendation --> ESCALATED["👤 Escalated to Human"]:::escalated')
    else:
        colour = "green" if "COMPLIANT" in final_verdict else "red"
        lines.append(
            f'    generate_recommendation --> RESULT["{final_verdict}"]:::{colour}verdict'
        )

    # Style definitions
    lines += [
        "",
        "    classDef executed fill:#3B82F6,color:#fff,stroke:#1D4ED8",
        "    classDef skipped fill:#E5E7EB,color:#9CA3AF,stroke:#D1D5DB",
        "    classDef critique fill:#F59E0B,color:#fff,stroke:#D97706",
        "    classDef gate fill:#8B5CF6,color:#fff,stroke:#6D28D9",
        "    classDef escalated fill:#EF4444,color:#fff,stroke:#B91C1C",
        "    classDef greenverd fill:#10B981,color:#fff,stroke:#059669",
        "    classDef redverd fill:#EF4444,color:#fff,stroke:#B91C1C",
    ]

    return "\n".join(lines)