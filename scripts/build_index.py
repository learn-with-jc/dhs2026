import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import POLICY_DIR, PRECEDENT_DIR, VECTOR_STORE_DIR
from prism.platform.document_processor import load_policy_document, chunk_policy_document, policy_chunks_to_documents, load_precedents
from prism.platform.vector_store import VectorStoreManager

store = VectorStoreManager(VECTOR_STORE_DIR)
docs = []
for f in POLICY_DIR.glob('*.md'):
    pol = load_policy_document(f)
    chunks = chunk_policy_document(pol)
    docs += policy_chunks_to_documents(chunks)
store.index_policies(docs)

prec_docs = load_precedents(PRECEDENT_DIR / 'precedent_store.jsonl')
store.index_precedents(prec_docs)
print('Vector store indexed.')
