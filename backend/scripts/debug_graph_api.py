import sys
import os
import logging
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugGraphAPI")

# Mock Auth Context to initialize Repo
class MockAuthContext:
    def __init__(self):
        from app.core.config import settings
        self.tenant_id = settings.TENANT_ID
        self.engagement_id = settings.ENGAGEMENT_ID
        self.user_id = "test-admin"
        self.roles = ["admin"]

from app.services.firestore_repo import FirestoreRepo
from app.services.graph_query_service import GraphQueryService

def debug_graph_api():
    print(f"\n🔎 Debugging Graph API Service Logic")
    
    # Init Service
    auth = MockAuthContext()
    repo = FirestoreRepo(auth)
    service = GraphQueryService(repo)
    
    # 1. Test Overview (Mode="overview")
    print("\n[Step 1] Testing get_overview(mode='overview')...")
    ov = service.get_overview(limit=50, mode="overview", include_docs=False)
    
    nodes = ov.get("nodes", [])
    edges = ov.get("links", []) # links key
    
    concept_count = len([n for n in nodes if n["group"] == "concept"])
    doc_count = len([n for n in nodes if n["group"] == "document"])
    
    print(f"   Total Nodes: {len(nodes)}")
    print(f"   Concepts: {concept_count}")
    print(f"   Docs: {doc_count} (Should be 0)")
    
    cooc_edges = [e for e in edges if e.get("type") == "cooc"]
    print(f"   Cooc Edges: {len(cooc_edges)}")
    
    if doc_count == 0:
        print("   ✅ Overview Doc Filter OK (No Docs)")
    else:
        print("   ⚠️ Overview Doc Filter Warning (Docs present)")

    if not nodes:
        print("   ❌ No nodes found. Stopping.")
        return

    # 2. Test Expand (Pick first concept)
    target_cid = None
    for n in nodes:
        if n["group"] == "concept":
            target_cid = n["id"]
            break
            
    if target_cid:
        print(f"\n[Step 2] Testing expand_neighborhood({target_cid})...")
        exp = service.expand_neighborhood(node_id=target_cid, node_type="concept", doc_limit=5)
        
        e_nodes = exp.get("nodes", [])
        e_edges = exp.get("links", [])
        
        e_docs = [n for n in e_nodes if n["group"] == "document"]
        print(f"   Expanded Total Nodes: {len(e_nodes)}")
        print(f"   Expanded Docs: {len(e_docs)} (Limit 5)")
        
        if len(e_docs) <= 5:
            print("   ✅ Expand Doc Limit OK")
        else:
            print(f"   ❌ Expand Doc Limit FAILED: {len(e_docs)}")
        
        # Check Title Injection
        if e_docs and "label" in e_docs[0] and e_docs[0]["label"] != e_docs[0]["id"]:
             print(f"   ✅ Title Injected: {e_docs[0]['label']}")
        elif e_docs:
             print(f"   ⚠️ Title Warning (Label == ID): {e_docs[0]['label']}")
             
    else:
        print("   ❌ No concept found to expand.")

if __name__ == "__main__":
    debug_graph_api()
