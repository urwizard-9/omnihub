import sys
import os
import logging
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugEdgeRanker")

from app.rag.steps.edge_ranker import EdgeRanker
from app.core.config import settings

def debug_edge_ranker(doc_id):
    print(f"\n🔎 Debugging EdgeRanker for Doc ID: {doc_id}")
    
    ranker = EdgeRanker()
    
    # 1. Test load_concept_df
    print("\n[Step 1] Testing load_concept_df...")
    # Fetch some concept IDs from edges first
    edges_ref = (ranker.db.collection("edges_doc_concept")
                 .where(filter=firestore.FieldFilter("doc_id", "==", doc_id))
                 .limit(5)
                 .stream())
    
    concept_ids = [e.to_dict().get("concept_id") for e in edges_ref]
    if not concept_ids:
        print("❌ No edges found for this doc. Cannot test DF.")
        return

    # Mock Tenant/Engagement from settings or fetch from doc profile
    # Let's fetch from doc profile to be accurate
    prof = ranker.db.collection("profiles").document(doc_id).get().to_dict()
    tenant_id = prof.get("tenant_id")
    engagement_id = prof.get("engagement_id")
    
    print(f"   Context: Tenant={tenant_id}, Engagement={engagement_id}")
    
    df_map = ranker.load_concept_df(concept_ids, tenant_id, engagement_id)
    print(f"   DF Map Result: {df_map}")
    
    # Check if DF > 1 exists (it should if data is populated)
    if any(v > 1 for v in df_map.values()):
        print("✅ DF values > 1 found. Real stats are being used.")
    else:
        print("⚠️ All DF values are 1. Check if 'concepts' collection has doc_count.")

    # 2. Test process_single_document (Dry Run logic)
    print("\n[Step 2] Running process_single_document...")
    ranker.process_single_document(doc_id)
    
    # 3. Verify Result in Firestore
    print("\n[Step 3] Verifying Output...")
    doc_ref = ranker.db.collection("documents").document(doc_id).get()
    if doc_ref.exists:
        data = doc_ref.to_dict()
        top_concepts = data.get("top_concepts", [])
        print(f"   Top Concepts Count: {len(top_concepts)}")
        
        if len(top_concepts) > 0:
            print(f"   Top 1: {top_concepts[0]}")
            
        if len(top_concepts) <= 15:
            print("✅ Cap check passed (<= 15)")
        else:
            print(f"❌ Cap check FAILED (> 15): {len(top_concepts)}")
            
        # Check if score is diverse
        scores = [c.get("score") for c in top_concepts]
        print(f"   Scores: {scores}")
            
    else:
        print("❌ Document not found after processing")

if __name__ == "__main__":
    # Use a known doc ID or fetch one
    # Let's fetch one from 'files' that is completed
    db = firestore.Client(project=settings.PROJECT_ID)
    docs = db.collection("files").where(filter=firestore.FieldFilter("aiStatus", "==", "completed")).limit(1).stream()
    target_id = None
    for d in docs:
        target_id = d.id
        break
        
    if target_id:
        debug_edge_ranker(target_id)
    else:
        print("❌ No completed file found to test.")
