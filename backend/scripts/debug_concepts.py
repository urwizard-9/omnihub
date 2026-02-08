import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.gcp_clients import get_firestore_client

db = get_firestore_client()

print("=== Checking graph_serving_concepts ===")
concepts = list(db.collection("graph_serving_concepts").limit(3).stream())

for c in concepts:
    d = c.to_dict()
    cid = d.get("concept_id") or c.id
    meta = d.get("meta", {})
    top_docs = d.get("top_docs", [])
    
    print(f"\nConcept ID: {cid}")
    print(f"  Name: {meta.get('name', 'Unknown')}")
    print(f"  top_docs count: {len(top_docs)}")
    
    if top_docs:
        print(f"  Sample top_doc: {top_docs[0]}")
    else:
        print("  ⚠️ NO TOP_DOCS!")

print("\n=== Done ===")
