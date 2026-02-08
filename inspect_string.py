
import os
import sys
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.gcp_clients import get_firestore_client
from app.core.config import settings

def inspect():
    db = get_firestore_client()
    docs_ref = (db.collection("graph_serving_docs")
                .limit(20)
                .stream())
    
    cid = None
    for d in docs_ref:
        data = d.to_dict()
        top_c = data.get("top_concepts")
        if top_c:
            cid = top_c[0].get("concept_id")
            break
            
    if not cid:
        print("No concept found")
        return

    ref = db.collection("graph_serving_concepts").document(cid).get()
    if ref.exists:
        rd = ref.to_dict()
        e = rd.get('engagement_id')
        print(f"Engagement: {repr(e)}")
        print(f"Length: {len(e)}")
        print(f"Chars: {[ord(c) for c in e]}")
        
        target = "my-engagement-001"
        print(f"Target: {repr(target)}")
        print(f"Target Chars: {[ord(c) for c in target]}")
        print(f"Equal? {e == target}")

if __name__ == "__main__":
    inspect()
