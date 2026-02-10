import sys
import os
import logging
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugRetrieverV2")

from app.services.firestore_repo import FirestoreRepo
from app.rag.retriever import Retriever
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client # Direct DB access

# Mock Auth Context
class MockAuthContext:
    def __init__(self):
        self.user_id = "debug-admin"
        self.tenant_id = settings.TENANT_ID
        self.engagement_id = settings.ENGAGEMENT_ID
        self.roles = ["admin"]

def debug_retrieval_v2(query):
    print(f"\n🔎 Debugging Query: '{query}'")
    print(f"   Target Scope: Tenant={settings.TENANT_ID}, Engagement={settings.ENGAGEMENT_ID}")
    
    auth_ctx = MockAuthContext()
    repo = FirestoreRepo(auth_ctx)
    retriever = Retriever(repo)
    db = get_firestore_client()
    
    # 1. Embed Query
    vec = retriever._embed_query(query)

    # 2. Raw Search (No Filter)
    print("\n[Step 2] Raw Vector Search...")
    neighbors = retriever.idx_client.find_neighbors(
        deployed_index_id=os.getenv("VECTOR_DEPLOYED_INDEX_ID"),
        queries=[vec],
        num_neighbors=5
    )
    candidates = neighbors[0] if neighbors else []
    print(f"   -> Raw Candidates: {len(candidates)}")
    
    for i, c in enumerate(candidates):
        print(f"      #{i+1} ID: {c.id}")
        
        # Analyze Metadata for this candidate
        if "::" in c.id:
            doc_id, chunk_id = c.id.split("::")
            
            # Check Doc Meta Directly
            doc_ref = db.collection("documents").document(doc_id).get()
            if not doc_ref.exists:
                print(f"         ❌ Document {doc_id} NOT FOUND in Firestore!")
                continue
                
            doc_data = doc_ref.to_dict()
            print(f"         📄 Doc Metadata:")
            print(f"            - Tenant: {doc_data.get('tenant_id')}")
            print(f"            - Engagement: {doc_data.get('engagement_id')}")
            print(f"            - Active: {doc_data.get('active')}")
            print(f"            - Review Status: {doc_data.get('review_status')}")
            
            # Check Repo Access
            try:
                repo_doc = repo.get_document(doc_id)
                if repo_doc:
                    print(f"         ✅ Repo Access OK")
                else:
                    print(f"         ❌ Repo Access DENIED (Scope Mismatch?)")
            except Exception as e:
                print(f"         ❌ Repo Error: {e}")
        else:
            print(f"         ❌ Invalid ID Format")

if __name__ == "__main__":
    query = "코셈 상장일"
    debug_retrieval_v2(query)
