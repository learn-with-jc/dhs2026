cat > README.md << 'EOF'
# 🛡️ Sentinel-X
## From Keywords to Agents: Enterprise Compliance AI

> Presented at **DataHack Summit 2026**
> *Human × AI: The Rise of the Agentic Operating Layer*
>
> **Jatin Chaudhary** — Senior Manager, Cisco Systems | Adjunct Faculty, IIIT Bangalore

---

## What is Sentinel-X?

Sentinel-X is a practitioner's demonstration of how an enterprise AI system
evolves through four phases — from keyword matching to agentic reasoning —
solving Purchase Requisition compliance review at scale.

This is not a demo built for a conference.
It is a real architecture, abstracted and synthesised for sharing.

---

## The Four Phases

| Phase | Technique | What it solved | What it broke |
|-------|-----------|---------------|---------------|
| **Phase 1** | Keyword Detection | Volume | Context |
| **Phase 2** | Prompt Engineering | Interpretation | Consistency |
| **Phase 3** | Context + Loop Engineering | Reasoning | Reproducibility |
| **Phase 4** | Deterministic Rule Engine | Auditability | Adaptability |

---

## Architecture

PR Input
│
├── Phase 1: Keyword scan (no LLM)
├── Phase 2: LLM compliance filter + guardrails
├── Phase 3: LangGraph multi-agent reasoning
│ ├── extract_intent
│ ├── classify_policy
│ ├── retrieve_and_rerank (ChromaDB + BM25 + BAAI reranker)
│ ├── reason_compliance
│ ├── critique_reasoning ← loop engineering
│ ├── verdict_gate ← confidence routing
│ ├── extract_evidence
│ └── generate_recommendation
└── Phase 4: Deterministic audit engine

---

## Tech Stack

- **LangGraph** — Agent orchestration and state management
- **LangChain** — LLM abstractions and prompt management
- **OpenAI GPT-4o** — Primary LLM (provider-agnostic swap layer included)
- **ChromaDB** — Vector store for policy retrieval
- **BAAI/bge-reranker-v2-m3** — Cross-encoder reranking
- **BM25** — Sparse retrieval for exact threshold matching
- **Streamlit** — Interactive demo application
- **Pydantic v2** — Data models and validation

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/sentinel-x.git
cd sentinel-x

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -e .

# 4. Set up environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 5. Build vector index
make index

# 6. Run the phases
python -m sentinel_x.phase1_keyword.run_phase1   # no API key needed
python -m sentinel_x.phase2_llm.run_phase2        # needs OpenAI
python -m sentinel_x.phase4_audit.run_phase4      # no API key needed
python -m sentinel_x.phase3_agentic.run_phase3    # needs OpenAI

# 7. Launch the Streamlit app
streamlit run app/main.py


---

Repository Structure

sentinel-x/
├── config/                    # Central configuration
├── data/
│   └── raw/
│       ├── policies/          # 5 synthetic policy documents
│       ├── purchase_requisitions/  # 30 synthetic PRs
│       └── precedents/        # 20 historical decisions
├── sentinel_x/
│   ├── platform/              # LLM provider, vector store, reranker
│   ├── phase1_keyword/        # Keyword detection engine
│   ├── phase2_llm/            # LLM compliance filter + guardrails
│   ├── phase3_agentic/        # LangGraph multi-agent system
│   ├── phase4_audit/          # Deterministic rule engine
│   └── observability/         # Audit logging and metrics
├── app/                       # Streamlit demo application
├── notebooks/                 # Phase walkthroughs
└── tests/                     # Unit tests


---

Key Concepts Demonstrated

The Inversion Pattern — Finding compliant PRs to shrink the review pool
Hybrid Search — Dense + sparse + RRF fusion for policy retrieval
Loop Engineering — Self-correcting reasoning chains with confidence bounds
Critique Agent — Competence boundary detection, not retry logic
Deterministic Audit — When NOT to use AI is the expert move
Citation Grounding — No citations = no verdict (hallucination defence)

---

Synthetic Data

All data in this repository is fully synthetic.
No real Cisco data, customer data, or proprietary information is included.
Policy documents, purchase requisitions, and precedents are
purpose-built for this demonstration.


---

Session Details

Conference: DataHack Summit 2026
Theme: Human × AI: The Rise of the Agentic Operating Layer
Format: 1-hour hack session
Speaker: Jatin Chaudhary, Senior Manager — Cisco Systems


---

License

MIT License — free to use, adapt, and build upon.
Attribution appreciated.
