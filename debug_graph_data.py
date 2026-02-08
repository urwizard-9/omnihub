
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.gcp_clients import get_firestore_client
from app.core.config import settings

def debug_graph_data():
    db = get_firestore_client()
    tenant_id = settings.TENANT_ID
    engagement_id = settings.ENGAGEMENT_ID
    
    print(f"Debug Scope: Tenant={tenant_id}, Engagement={engagement_id}")
    
    # 1. Get a random Doc from serving index (Try up to 20)
    docs_ref = (db.collection("graph_serving_docs")
                .limit(20)
                .stream())
    
    doc = None
    d_data = {}
    found_valid = False
    
    for d in docs_ref:
        data = d.to_dict()
        if data.get("top_concepts"):
            doc = d
            d_data = data
            found_valid = True
            break
        
    if not found_valid:
        print("❌ Scanned 20 docs, none had 'top_concepts'. Graph data seems largely missing.")
        return

    print(f"\n✅ Found Valid Doc: {doc.id} ({d_data.get('title')})")
    print(f"   - Top Concepts: {len(d_data.get('top_concepts', []))}")
    concept = d_data.get("top_concepts")[0]
    cid = concept.get("concept_id")
    cname = concept.get("name")
    print(f"\n✅ Inspecting Concept: {cid} ({cname})")
    
    # 3. Check Concept Serving Index
    c_ref = db.collection("graph_serving_concepts").document(cid).get()
    
    if not c_ref.exists:
        print(f"❌ Concept {cid} NOT found in graph_serving_concepts!")
        return
        
    c_data = c_ref.to_dict()
    top_docs = c_data.get("top_docs", [])
    print(f"   - Found Concept in Serving Index.")
    print(f"   - Top Docs Count: {len(top_docs)}")
    
    for i, td in enumerate(top_docs[:5]):
        print(f"     [{i}] {td.get('doc_id')} - {td.get('title')} (score: {td.get('score')})")
        
    if not top_docs:
        print("❌ output: Concept has NO top_docs. 3-Hop will fail.")
    else:
        print("✅ output: Concept has top_docs. 3-Hop *should* work.")

if __name__ == "__main__":
    debug_graph_data()
