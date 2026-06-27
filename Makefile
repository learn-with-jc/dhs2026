# Sentinel-X | Makefile
# One-command setup and execution

.PHONY: setup index phase1 phase2 phase3 phase4 app test clean

setup:
	pip install -r requirements.txt
	cp -n .env.example .env || true
	@echo "✓ Setup complete. Edit .env with your API keys."

index:
	python -c "
from config.settings import POLICY_DIR, PRECEDENT_DIR, VECTOR_STORE_DIR
from sentinel_x.platform.document_processor import load_policy_document, chunk_policy_document, policy_chunks_to_documents, load_precedents
from sentinel_x.platform.vector_store import VectorStoreManager
from pathlib import Path

store = VectorStoreManager(VECTOR_STORE_DIR)
docs  = []
for f in POLICY_DIR.glob('*.md'):
    pol    = load_policy_document(f)
    chunks = chunk_policy_document(pol)
    docs  += policy_chunks_to_documents(chunks)
store.index_policies(docs)

prec_docs = load_precedents(PRECEDENT_DIR / 'precedent_store.jsonl')
store.index_precedents(prec_docs)
print('Vector store indexed.')
"

phase1:
	python -m sentinel_x.phase1_keyword.run_phase1

phase2:
	python -m sentinel_x.phase2_llm.run_phase2

phase3:
	python -m sentinel_x.phase3_agentic.run_phase3

phase4:
	python -m sentinel_x.phase4_audit.run_phase4

app:
	streamlit run app/main.py

test:
	pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf data/processed/vector_store data/processed/audit_logs
	@echo "✓ Cleaned."