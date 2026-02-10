import sys
import os
import logging
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugGraphServing")

from app.rag.steps.build_graph_serving_index import GraphServingIndexBuilder
from app.core.config import settings

def debug_serving_build():
    print(f"\n🔎 Debugging Graph Serving Index Builder")
    print(f"   Settings: Cap={settings.GRAPH_SERVING_CAP}, Statuses={settings.GRAPH_SERVING_ALLOWED_STATUSES}")
    
    builder = GraphServingIndexBuilder()
    
    # 1. Run Builder (It's fast for small set)
    # builder.run() # Full build might be slow if many docs
    
    # Let's try incremental on a specific doc
    db = firestore.Client(project=settings.PROJECT_ID)
    
    # Logic: Find a completed doc
    docs = db.collection("files").where(filter=firestore.FieldFilter("aiStatus", "==", "completed")).limit(1).stream()
    target_id = None
    for d in docs:
        target_id = d.id
        break
        
    if not target_id:
        print("❌ No completed file found.")
        return

    print(f"\n[Step 1] Running Process Single Doc: {target_id}")
    builder.process_single_document(target_id)
    
    # 2. Verify Output (Doc Centric)
    print("\n[Step 2] Verifying Graph Serving DOCS...")
    s_doc = db.collection("graph_serving_docs").document(target_id).get()
    if s_doc.exists:
        data = s_doc.to_dict()
        top_c = data.get("top_concepts", [])
        print(f"   ✅ Doc Entry Found. Title: {data.get('title')}")
        print(f"   Top Concepts Count: {len(top_c)} (Should be <= {settings.GRAPH_SERVING_CAP})")
        
        if len(top_c) > settings.GRAPH_SERVING_CAP:
             print(f"   ❌ Cap Exceeded!")
        else:
             print(f"   ✅ Cap OK.")
             
        # Check if concept has name
        if top_c and "name" in top_c[0]:
            print(f"   ✅ Concept Name Injected: {top_c[0]['name']}")
        else:
            print(f"   ⚠️ Concept Name Missing")
            
        # 3. Verify Output (Concept Centric)
        if top_c:
            cid = top_c[0]["concept_id"]
            print(f"\n[Step 3] Verifying Graph Serving CONCEPT: {cid}")
            s_con = db.collection("graph_serving_concepts").document(cid).get()
            if s_con.exists:
                c_data = s_con.to_dict()
                top_d = c_data.get("top_docs", [])
                print(f"   ✅ Concept Entry Found.")
                print(f"   Top Docs Count: {len(top_d)} (Should be <= {settings.GRAPH_SERVING_CAP})")
                
                # Check for Title Injection
                has_title = any("title" in d for d in top_d)
                if has_title:
                    print(f"   ✅ Title Injected in Top Docs.")
                    print(f"   Sample: {top_d[0]}")
                else:
                    print(f"   ❌ Title Missing in Top Docs.")
            else:
                print(f"   ⚠️ Concept Serving Entry Not Found (Maybe batch didn't run?)")
    else:
        print("❌ Serving Doc Entry Not Found")

if __name__ == "__main__":
    debug_serving_build()
