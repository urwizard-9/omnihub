import sys
import os
import logging
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugRetriever")

from app.services.firestore_repo import FirestoreRepo
from app.rag.retriever import Retriever
from app.core.config import settings

# Mock Auth Context
class MockAuthContext:
    def __init__(self):
        self.user_id = "debug-admin"
        self.tenant_id = settings.TENANT_ID
        self.engagement_id = settings.ENGAGEMENT_ID
        self.roles = ["admin"]

def debug_retrieval(query):
    print(f"\n🔎 Debugging Query: '{query}'")
    print(f"   Target Scope: Tenant={settings.TENANT_ID}, Engagement={settings.ENGAGEMENT_ID}")
    
    auth_ctx = MockAuthContext()
    repo = FirestoreRepo(auth_ctx)
    retriever = Retriever(repo)
    
    # 1. Embed Query
    try:
        vec = retriever._embed_query(query)
        print(f"✅ Query Embedding Generated. Length: {len(vec)}")
    except Exception as e:
        print(f"❌ Embedding Failed: {e}")
        return

    # 2. Raw Search (No Filter)
    print("\n[Step 2] Raw Vector Search (No Filter)...")
    try:
        neighbors = retriever.idx_client.find_neighbors(
            deployed_index_id=retriever.deployed_index_id if hasattr(retriever, 'deployed_index_id') else os.getenv("VECTOR_DEPLOYED_INDEX_ID"),
            queries=[vec],
            num_neighbors=10
        )
        candidates = neighbors[0] if neighbors else []
        print(f"   -> Raw Candidates Found: {len(candidates)}")
        
        for i, c in enumerate(candidates):
            print(f"      #{i+1} ID: {c.id}, Distance: {c.distance}")
            
    except Exception as e:
        print(f"❌ Raw Search Failed: {e}")
        return

    # 3. Full Retrieve (With Filter & Post-Processing)
    print("\n[Step 3] Full Retrieve Logic...")
    try:
        # Pass empty scope, rely on global settings in retriever or env
        results = retriever.retrieve(query)
        print(f"   -> Final Results: {len(results)}")
        
        for i, r in enumerate(results):
            print(f"      #{i+1} Doc: {r.doc_id}, Chunk: {r.chunk_id}")
            print(f"         Snippet: {r.snippet[:50]}...")
            
    except Exception as e:
        print(f"❌ Full Retrieve Failed: {e}")

if __name__ == "__main__":
    query = "코셈 상장일"
    debug_retrieval(query)
