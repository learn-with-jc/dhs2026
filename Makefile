# PRism | Makefile
# One-command setup and execution

.PHONY: setup index phase1 phase2 phase3 phase4 app test clean

setup:
	pip install -r requirements.txt
	cp -n .env.example .env || true
	@echo "✓ Setup complete. Edit .env with your API keys."

index:
	python scripts/build_index.py

phase1:
	python -m prism.phase1_keyword.run_phase1

phase2:
	python -m prism.phase2_llm.run_phase2

phase3:
	python -m prism.phase3_agentic.run_phase3

phase4:
	python -m prism.phase4_audit.run_phase4

app:
	streamlit run app/main.py

test:
	pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf data/processed/vector_store data/processed/audit_logs
	@echo "✓ Cleaned."